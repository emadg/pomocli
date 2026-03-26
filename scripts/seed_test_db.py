#!/usr/bin/env python3
"""
Seed a test SQLite database with realistic data for development, demos, and verification.

Covers: tasks (projects, estimates, last_accessed), sessions (completed / stopped / killed,
git repo+branch, durations), tags, distractions.

Run with: POMOCLI_DB_PATH=test_pomocli.db python scripts/seed_test_db.py
Then e.g.: POMOCLI_DB_PATH=test_pomocli.db pomo report today
"""

from __future__ import annotations

import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pomocli.db.connection import init_db, DB_PATH

SQLITE_FMT = "%Y-%m-%d %H:%M:%S"


def _utc(dt: datetime) -> str:
    """Format an aware UTC datetime for SQLite."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(SQLITE_FMT)


def _insert_session(
    cursor: sqlite3.Cursor,
    *,
    task_id: int,
    start: datetime,
    end: datetime | None,
    duration_secs: int,
    status: str,
    git_repo: str | None,
    git_branch: str | None,
) -> int:
    end_sql = _utc(end) if end is not None else None
    cursor.execute(
        """
        INSERT INTO sessions (task_id, start_time, end_time, duration_logged, status, git_repo, git_branch)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, _utc(start), end_sql, duration_secs, status, git_repo, git_branch),
    )
    return cursor.lastrowid


def _insert_tags(cursor: sqlite3.Cursor, session_id: int, names: list[str]) -> None:
    for name in names:
        cursor.execute(
            "INSERT INTO tags (session_id, tag_name) VALUES (?, ?)",
            (session_id, name),
        )


def _insert_distractions(
    cursor: sqlite3.Cursor,
    session_id: int,
    start: datetime,
    end: datetime | None,
    descriptions: list[str | None],
) -> None:
    if end is None:
        return
    span_mins = max(1, int((end - start).total_seconds() // 60))
    for desc in descriptions:
        off = random.randint(1, max(1, span_mins - 1))
        ts = start + timedelta(minutes=off)
        cursor.execute(
            "INSERT INTO distractions (session_id, timestamp, description) VALUES (?, ?, ?)",
            (session_id, _utc(ts), desc),
        )


def generate_data() -> None:
    print(f"Seeding test database at: {DB_PATH}")
    if os.environ.get("POMOCLI_DB_PATH") is None:
        print(
            "Tip: set POMOCLI_DB_PATH=./demo.db (or any path) to seed an isolated file "
            "instead of the default ~/.config/pomocli database.",
            file=sys.stderr,
        )

    if DB_PATH.exists():
        DB_PATH.unlink()

    init_db()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)

    # --- Curated tasks: projects, estimates, staggered last_accessed (for interactive / --last demos)
    task_specs: list[tuple[str, str | None, int | None, int]] = [
        ("Write README", "pomocli", 60, 0),
        ("Add reporting", "pomocli", 240, 0),
        ("Refactor timer", "pomocli", 180, 1),
        ("Fix auth bug", "backend-api", 120, 2),
        ("Design database", "backend-api", 90, 3),
        ("Setup CI/CD", "pomocli", 60, 4),
        ("Deep work: landing page", "website", None, 5),
        ("Code review", None, 30, 6),
        ("Update dependencies", "pomocli", 45, 7),
        ("Admin / email", None, None, 8),
    ]

    task_ids: dict[str, int] = {}
    for name, project, est, days_ago in task_specs:
        last_accessed = now - timedelta(days=days_ago, hours=random.randint(0, 8))
        cursor.execute(
            """
            INSERT INTO tasks (project_name, task_name, estimated_minutes, last_accessed)
            VALUES (?, ?, ?, ?)
            """,
            (project, name, est, _utc(last_accessed)),
        )
        task_ids[name] = cursor.lastrowid

    def tid(name: str) -> int:
        return task_ids[name]

    repos = {
        "pomocli": ("emad/pomocli", "main"),
        "backend-api": ("emad/backend", "feature/auth"),
        "website": ("emad/website", "dev"),
    }

    # --- Spotlight: recent UTC window (usually falls in "today" for most local timezones)
    spotlight: list[dict] = [
        {
            "task": "Add reporting",
            "hours_ago": 9,
            "mins": 25,
            "status": "completed",
            "tags": ["focus", "deep-work"],
            "project": "pomocli",
            "distractions": ["Slack ping", "Quick email"],
        },
        {
            "task": "Write README",
            "hours_ago": 7,
            "mins": 25,
            "status": "completed",
            "tags": ["planning"],
            "project": "pomocli",
            "distractions": [],
        },
        {
            "task": "Fix auth bug",
            "hours_ago": 5,
            "mins": 50,
            "status": "stopped",
            "tags": ["bugfix", "focus"],
            "project": "backend-api",
            "distractions": ["Coworker"],
        },
        {
            "task": "Deep work: landing page",
            "hours_ago": 3,
            "mins": 25,
            "status": "completed",
            "tags": ["deep-work"],
            "project": "website",
            "distractions": ["Phone call", None],
        },
        {
            "task": "Refactor timer",
            "hours_ago": 1,
            "mins": 25,
            "status": "killed",
            "tags": ["focus"],
            "project": "pomocli",
            "distractions": [],
        },
        {
            "task": "Code review",
            "hours_ago": 0,
            "mins": 20,
            "status": "completed",
            "tags": ["review"],
            "project": None,
            "git": (None, None),
            "distractions": [],
        },
    ]

    for spec in spotlight:
        h_ago = spec["hours_ago"]
        mins = spec["mins"]
        start = now - timedelta(hours=h_ago, minutes=random.randint(0, 25))
        status = spec["status"]
        if status == "killed":
            end = None
            duration_secs = mins * 60 // 2
        elif status == "stopped":
            end = start + timedelta(minutes=mins)
            duration_secs = int((mins * 60) * 0.6)
        else:
            end = start + timedelta(minutes=mins)
            duration_secs = mins * 60

        proj = spec.get("project")
        if "git" in spec:
            gr, gb = spec["git"]
        elif proj and proj in repos:
            gr, gb = repos[proj]
        else:
            gr, gb = None, None

        sid = _insert_session(
            cursor,
            task_id=tid(spec["task"]),
            start=start,
            end=end,
            duration_secs=duration_secs,
            status=status,
            git_repo=gr,
            git_branch=gb,
        )
        _insert_tags(cursor, sid, spec["tags"])
        if spec.get("distractions"):
            _insert_distractions(cursor, sid, start, end, list(spec["distractions"]))

    # --- Last 7 local-calendar-friendly density: multiple sessions per UTC day for trend charts
    for day_offset in range(7):
        day_anchor = now.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(
            days=day_offset
        )
        num = random.randint(2, 5)
        for _ in range(num):
            task_name = random.choice(list(task_ids.keys()))
            hour = random.randint(8, 18)
            minute = random.randint(0, 59)
            start = day_anchor.replace(hour=hour, minute=minute, tzinfo=timezone.utc)
            duration_mins = random.choice([15, 25, 25, 50, 60])
            status = random.choices(
                ["completed", "stopped", "killed"],
                weights=[0.82, 0.12, 0.06],
            )[0]
            if status == "killed":
                end = None
                duration_secs = duration_mins * 60 // 2
            elif status == "stopped":
                end = start + timedelta(minutes=duration_mins)
                duration_secs = int(duration_mins * 60 * random.uniform(0.4, 0.85))
            else:
                end = start + timedelta(minutes=duration_mins)
                duration_secs = duration_mins * 60

            proj = next((p for n, p, _, _ in task_specs if n == task_name), None)
            if proj and proj in repos and random.random() > 0.25:
                gr, gb = repos[proj]
            else:
                gr, gb = None, None

            sid = _insert_session(
                cursor,
                task_id=tid(task_name),
                start=start,
                end=end,
                duration_secs=duration_secs,
                status=status,
                git_repo=gr,
                git_branch=gb,
            )
            if random.random() > 0.35:
                pool = ["focus", "deep-work", "bugfix", "planning", "review", "admin"]
                k = random.randint(1, 3)
                _insert_tags(cursor, sid, random.sample(pool, k))
            if random.random() > 0.55 and end is not None and duration_mins >= 2:
                nd = random.randint(1, 3)
                descs = random.choices(
                    ["Slack message", "Email", "Phone call", "Coworker", None],
                    k=nd,
                )
                _insert_distractions(cursor, sid, start, end, descs)

    # --- Background: days 8–90 (lighter random fill)
    for day_offset in range(8, 91):
        num_sessions = random.randint(0, 4)
        current_date = now - timedelta(days=day_offset)

        for _ in range(num_sessions):
            task_name = random.choice(list(task_ids.keys()))
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            start = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)

            duration_mins = random.choice([15, 25, 25, 25, 50, 60])
            status = random.choices(
                ["completed", "stopped", "killed"],
                weights=[0.8, 0.15, 0.05],
            )[0]

            if status == "killed":
                end = None
                duration_secs = duration_mins * 60 // 2
            elif status == "stopped":
                end = start + timedelta(minutes=duration_mins)
                duration_secs = int(duration_mins * 60 * random.uniform(0.45, 0.9))
            else:
                end = start + timedelta(minutes=duration_mins)
                duration_secs = duration_mins * 60

            proj = next((p for n, p, _, _ in task_specs if n == task_name), None)
            if proj and proj in repos and random.random() > 0.3:
                gr, gb = repos[proj]
            else:
                gr, gb = None, None

            sid = _insert_session(
                cursor,
                task_id=tid(task_name),
                start=start,
                end=end,
                duration_secs=duration_secs,
                status=status,
                git_repo=gr,
                git_branch=gb,
            )

            if random.random() > 0.5:
                pool = ["focus", "deep-work", "bugfix", "planning", "review", "admin"]
                _insert_tags(
                    cursor, sid, random.sample(pool, random.randint(1, 3))
                )

            if random.random() > 0.72 and end is not None and duration_mins >= 2:
                distract_time = start + timedelta(
                    minutes=random.randint(1, max(1, duration_mins - 1))
                )
                cursor.execute(
                    "INSERT INTO distractions (session_id, timestamp, description) VALUES (?, ?, ?)",
                    (
                        sid,
                        _utc(distract_time),
                        random.choice(["Slack message", "Email", "Phone call", "Coworker", None]),
                    ),
                )

    conn.commit()
    conn.close()

    print("Test database seeded successfully!")
    print()
    print("Try (set POMOCLI_DB_PATH as above):")
    print("  pomo report today")
    print("  pomo report week")
    print("  pomo report month")
    print("  pomo report quarter")
    print("  pomo start   # interactive recent tasks / projects from this DB")


if __name__ == "__main__":
    generate_data()
