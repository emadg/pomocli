#!/usr/bin/env python3
"""
Seed a test SQLite database with realistic data for development, demos, and verification.

Covers: tasks (projects, estimates, last_accessed), sessions (all statuses, both
timer_mode values, git), tags, distractions, session_events (for pause/resume and
metrics demos).

Run with: POMOCLI_DB_PATH=test_pomocli.db python scripts/seed_test_db.py
Then e.g.: POMOCLI_DB_PATH=test_pomocli.db pomo report today
"""

from __future__ import annotations

import json
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
    timer_mode: str = "countdown",
) -> int:
    end_sql = _utc(end) if end is not None else None
    cursor.execute(
        """
        INSERT INTO sessions (
            task_id, start_time, end_time, duration_logged, status,
            git_repo, git_branch, timer_mode
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            _utc(start),
            end_sql,
            duration_secs,
            status,
            git_repo,
            git_branch,
            timer_mode,
        ),
    )
    return int(cursor.lastrowid)


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


def _insert_distractions_at_minutes(
    cursor: sqlite3.Cursor,
    session_id: int,
    start: datetime,
    items: list[tuple[int, str | None]],
) -> None:
    """Insert distractions at fixed minute offsets from session start."""
    for minutes_from_start, desc in items:
        ts = start + timedelta(minutes=minutes_from_start)
        cursor.execute(
            "INSERT INTO distractions (session_id, timestamp, description) VALUES (?, ?, ?)",
            (session_id, _utc(ts), desc),
        )


def _insert_session_events(
    cursor: sqlite3.Cursor,
    session_id: int,
    start: datetime,
    specs: list[tuple[str, int, dict | None]],
) -> None:
    """
    Insert lifecycle events at minute offsets from session start.

    Each spec: (event_type, minutes_from_start, details_dict_or_none)
    """
    for event_type, minutes_from_start, details in specs:
        ts = start + timedelta(minutes=minutes_from_start)
        payload = json.dumps(details) if details else None
        cursor.execute(
            """
            INSERT INTO session_events (session_id, event_type, timestamp, details)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, event_type, _utc(ts), payload),
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
        ("Stopwatch deep work", "pomocli", 90, 0),
        ("Metrics demo long block", "pomocli", 120, 0),
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

    # --- Feature showcase: fixed wall times, session_events, elapsed, attention-quality math
    showcase_start = (now - timedelta(hours=11)).replace(minute=0, second=0, microsecond=0)

    # Doc-style session 1: 60m wall, 15m pause (30–45), distraction at 45m → 10m recovery cap → 35m effective
    s1_start = showcase_start
    s1_end = s1_start + timedelta(minutes=60)
    sid1 = _insert_session(
        cursor,
        task_id=tid("Metrics demo long block"),
        start=s1_start,
        end=s1_end,
        duration_secs=35 * 60,
        status="completed",
        git_repo="emad/pomocli",
        git_branch="main",
        timer_mode="countdown",
    )
    _insert_tags(cursor, sid1, ["demo-metrics", "focus"])
    _insert_session_events(
        cursor,
        sid1,
        s1_start,
        [
            ("start", 0, {"duration_minutes": 60}),
            ("pause", 30, {"source": "manual"}),
            ("resume", 45, None),
            ("complete", 60, None),
        ],
    )
    _insert_distractions_at_minutes(cursor, sid1, s1_start, [(45, "Doc example distraction")])

    # Doc-style session 2: 45m wall, distraction at 40m → 5m remaining → 5m recovery → 40m effective
    s2_start = showcase_start + timedelta(hours=2)
    s2_end = s2_start + timedelta(minutes=45)
    sid2 = _insert_session(
        cursor,
        task_id=tid("Metrics demo long block"),
        start=s2_start,
        end=s2_end,
        duration_secs=40 * 60,
        status="stopped",
        git_repo="emad/pomocli",
        git_branch="main",
        timer_mode="countdown",
    )
    _insert_tags(cursor, sid2, ["demo-metrics"])
    _insert_session_events(
        cursor,
        sid2,
        s2_start,
        [
            ("start", 0, {"duration_minutes": 45}),
            ("stop", 45, None),
        ],
    )
    _insert_distractions_at_minutes(cursor, sid2, s2_start, [(40, "Late distraction (5m left)")])

    # Elapsed (stopwatch) completed — 52m wall, one distraction mid-session
    es_start = showcase_start + timedelta(hours=5)
    es_end = es_start + timedelta(minutes=52)
    sid_e = _insert_session(
        cursor,
        task_id=tid("Stopwatch deep work"),
        start=es_start,
        end=es_end,
        duration_secs=52 * 60,
        status="completed",
        git_repo="emad/pomocli",
        git_branch="feature/stopwatch",
        timer_mode="elapsed",
    )
    _insert_tags(cursor, sid_e, ["stopwatch", "deep-work"])
    _insert_session_events(
        cursor,
        sid_e,
        es_start,
        [
            ("start", 0, {"mode": "elapsed"}),
            ("pause", 20, {"source": "idle"}),
            ("resume", 25, None),
            ("complete", 52, None),
        ],
    )
    _insert_distractions_at_minutes(cursor, sid_e, es_start, [(30, "Slack")])

    # Elapsed stopped (user hit Stop, not Complete)
    es2_start = showcase_start + timedelta(hours=7)
    es2_end = es2_start + timedelta(minutes=33)
    sid_e2 = _insert_session(
        cursor,
        task_id=tid("Stopwatch deep work"),
        start=es2_start,
        end=es2_end,
        duration_secs=int(33 * 60 * 0.95),
        status="stopped",
        git_repo="emad/pomocli",
        git_branch="main",
        timer_mode="elapsed",
    )
    _insert_tags(cursor, sid_e2, ["stopwatch"])
    _insert_session_events(
        cursor,
        sid_e2,
        es2_start,
        [
            ("start", 0, {"mode": "elapsed"}),
            ("stop", 33, None),
        ],
    )

    # Focus block score demo: 26m wall (qualifying), 1 pause + 1 distraction → 0.8 contribution
    s3_start = showcase_start + timedelta(hours=9)
    s3_end = s3_start + timedelta(minutes=26)
    sid3 = _insert_session(
        cursor,
        task_id=tid("Add reporting"),
        start=s3_start,
        end=s3_end,
        duration_secs=22 * 60,
        status="completed",
        git_repo="emad/pomocli",
        git_branch="main",
        timer_mode="countdown",
    )
    _insert_tags(cursor, sid3, ["demo-metrics"])
    _insert_session_events(
        cursor,
        sid3,
        s3_start,
        [
            ("start", 0, {"duration_minutes": 26}),
            ("pause", 10, {"source": "manual"}),
            ("resume", 12, None),
            ("complete", 26, None),
        ],
    )
    _insert_distractions_at_minutes(cursor, sid3, s3_start, [(18, "Email")])

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
            timer_mode="countdown",
        )
        _insert_tags(cursor, sid, spec["tags"])
        if spec.get("distractions"):
            _insert_distractions(cursor, sid, start, end, list(spec["distractions"]))
        # Light event stream on some completed countdown sessions (metrics / timelines)
        if status == "completed" and end is not None and random.random() < 0.5:
            mid = mins // 3
            _insert_session_events(
                cursor,
                sid,
                start,
                [
                    ("start", 0, {"duration_minutes": mins}),
                    ("pause", max(1, mid), {"source": "manual"}),
                    ("resume", max(2, mid + 3), None),
                    ("complete", mins, None),
                ],
            )

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
            timer_mode = random.choices(
                ["countdown", "elapsed"],
                weights=[0.88, 0.12],
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
                timer_mode=timer_mode,
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
            if (
                status == "completed"
                and end is not None
                and timer_mode == "countdown"
                and random.random() < 0.22
            ):
                b = max(1, duration_mins // 4)
                _insert_session_events(
                    cursor,
                    sid,
                    start,
                    [
                        ("start", 0, {"duration_minutes": duration_mins}),
                        ("pause", b, {"source": "screen_lock"}),  # screen_lock source — Mac slept mid-session
                        ("resume", min(b + 5, duration_mins - 1), None),
                        ("complete", duration_mins, None),
                    ],
                )
            elif (
                status == "completed"
                and end is not None
                and timer_mode == "elapsed"
                and random.random() < 0.35
            ):
                _insert_session_events(
                    cursor,
                    sid,
                    start,
                    [
                        ("start", 0, {"mode": "elapsed"}),
                        ("complete", duration_mins, None),
                    ],
                )

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
            timer_mode = random.choices(["countdown", "elapsed"], weights=[0.9, 0.1])[0]

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
                timer_mode=timer_mode,
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
    print("Includes: countdown + elapsed sessions, session_events (pauses / complete),")
    print("  curated rows for focus-block + attention-quality metrics (tag: demo-metrics).")
    print()
    print("Try (set POMOCLI_DB_PATH as above):")
    print("  pomo report today")
    print("  pomo report week")
    print("  pomo session list")
    print("  pomo start   # interactive recent tasks / projects from this DB")


if __name__ == "__main__":
    generate_data()
