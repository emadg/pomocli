#!/usr/bin/env python3
"""
Normalize project and task name casing in the pomocli SQLite DB and merge resulting duplicates.

Per-token rules and the stopword list match `pomocli.utils.text.normalize_display_name`:
  - All-caps acronyms (>=2 chars) and mixed-case tokens (NuCLEAR, iOS) are preserved.
  - Connective stopwords (a, the, of, ...) stay lowercase unless first.
  - Plain lowercase tokens get title-cased.

Within a case-insensitive group, the canonical spelling is taken from the row with the
greatest ``last_accessed`` and then run through ``normalize_display_name`` (so already-
acronym/mixed-case spellings are preserved verbatim, while plain spellings get cleaned).

Default mode is dry-run. Pass ``--apply`` to write changes. Honors ``POMOCLI_DB_PATH``
and an explicit ``--db PATH`` overrides it.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from pomocli.db import connection as db_connection
from pomocli.db.connection import init_db, get_connection
from pomocli.utils.text import normalize_display_name


def _project_groups(rows) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["project_name"] is None:
            continue
        groups[r["project_name"].lower()].append(r)
    return groups


def _task_groups(rows) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r["task_name"].lower()].append(r)
    return groups


def _canonical(rows, field: str) -> str:
    """Pick the most-recently-used spelling and normalize it."""
    best = max(rows, key=lambda r: r["last_accessed"] or "")
    return normalize_display_name(best[field])


def _rename_projects(conn, *, apply: bool) -> int:
    rows = conn.execute(
        "SELECT id, project_name, last_accessed FROM tasks WHERE project_name IS NOT NULL"
    ).fetchall()
    renames = 0
    for _key, group in _project_groups(rows).items():
        canonical = _canonical(group, "project_name")
        variants = {r["project_name"] for r in group if r["project_name"] != canonical}
        for variant in variants:
            count = sum(1 for r in group if r["project_name"] == variant)
            print(f"  project: {variant!r} -> {canonical!r}  ({count} row{'s' if count != 1 else ''})")
            renames += count
            if apply:
                conn.execute(
                    "UPDATE tasks SET project_name = ? WHERE project_name = ?",
                    (canonical, variant),
                )
    return renames


def _rename_tasks(conn, *, apply: bool) -> int:
    rows = conn.execute(
        "SELECT id, task_name, last_accessed FROM tasks"
    ).fetchall()
    renames = 0
    for _key, group in _task_groups(rows).items():
        canonical = _canonical(group, "task_name")
        variants = {r["task_name"] for r in group if r["task_name"] != canonical}
        for variant in variants:
            count = sum(1 for r in group if r["task_name"] == variant)
            print(f"  task:    {variant!r} -> {canonical!r}  ({count} row{'s' if count != 1 else ''})")
            renames += count
            if apply:
                conn.execute(
                    "UPDATE tasks SET task_name = ? WHERE task_name = ?",
                    (canonical, variant),
                )
    return renames


def _merge_duplicates(conn, *, apply: bool) -> int:
    rows = conn.execute(
        "SELECT id, project_name, task_name, last_accessed FROM tasks"
    ).fetchall()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["project_name"] or "", r["task_name"])].append(r)
    merges = 0
    for (proj, task), group in groups.items():
        if len(group) < 2:
            continue
        survivor = max(group, key=lambda r: r["last_accessed"] or "")
        for r in group:
            if r["id"] == survivor["id"]:
                continue
            print(
                f"  merge:   task#{r['id']} -> task#{survivor['id']}  "
                f"({proj or '<no project>'} / {task})"
            )
            merges += 1
            if apply:
                conn.execute(
                    "UPDATE sessions SET task_id = ? WHERE task_id = ?",
                    (survivor["id"], r["id"]),
                )
                conn.execute("DELETE FROM tasks WHERE id = ?", (r["id"],))
    return merges


def main(*, apply: bool = False, db_path: Optional[Path] = None) -> int:
    if db_path is not None:
        db_connection.DB_PATH = Path(db_path)
    init_db()
    conn = get_connection()
    try:
        mode = "apply" if apply else "dry-run"
        print(f"normalize_names ({mode}) on {db_connection.DB_PATH}")
        print("Projects:")
        p = _rename_projects(conn, apply=apply)
        print("Tasks:")
        t = _rename_tasks(conn, apply=apply)
        print("Merges:")
        m = _merge_duplicates(conn, apply=apply)
        if apply:
            conn.commit()
        else:
            conn.rollback()
        print(f"Summary: {p} project rename(s), {t} task rename(s), {m} row merge(s).")
        if not apply:
            print("(dry-run — pass --apply to write changes)")
        return p + t + m
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--db", type=Path, default=None, help="Path to pomocli SQLite DB")
    args = parser.parse_args()
    main(apply=args.apply, db_path=args.db)


if __name__ == "__main__":
    _cli()
