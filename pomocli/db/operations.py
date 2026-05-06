import json
import sqlite3
from typing import Optional, List, Dict, Any, cast
from .connection import get_connection
from ..time_util import utc_now_sql, retention_cutoff_utc, get_display_tz


def format_session_public_id(session_id: int, start_time_utc: str) -> str:
    """Build short session ID as YY + zero-padded session PK."""
    yy = start_time_utc[2:4] if start_time_utc and len(start_time_utc) >= 4 else "00"
    return f"{yy}{session_id:04d}"

def get_or_create_task(task_name: str, project_name: Optional[str] = None, estimated_minutes: Optional[int] = None) -> int:
    """Get an existing task ID or create a new one."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if task exists
    cursor.execute(
        "SELECT id FROM tasks WHERE task_name = ? AND (project_name = ? OR (project_name IS NULL AND ? IS NULL))",
        (task_name, project_name, project_name)
    )
    result = cursor.fetchone()
    
    if result:
        task_id = result['id']
        # Update last_accessed
        cursor.execute("UPDATE tasks SET last_accessed = ? WHERE id = ?", (utc_now_sql(), task_id))
    else:
        cursor.execute(
            "INSERT INTO tasks (project_name, task_name, estimated_minutes, last_accessed) VALUES (?, ?, ?, ?)",
            (project_name, task_name, estimated_minutes, utc_now_sql())
        )
        task_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return int(task_id)

def create_session(
    task_id: Optional[int],
    git_repo: Optional[str] = None,
    git_branch: Optional[str] = None,
    *,
    timer_mode: str = "countdown",
) -> int:
    """Create a new session and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO sessions (task_id, start_time, git_repo, git_branch, timer_mode) VALUES (?, ?, ?, ?, ?)",
        (task_id, utc_now_sql(), git_repo, git_branch, timer_mode),
    )
    session_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    if session_id is None:
        raise RuntimeError("Failed to create session row")
    return cast(int, session_id)

def update_session(session_id: int, status: str, duration_logged: int, end_time: bool = False):
    """Update an existing session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "UPDATE sessions SET status = ?, duration_logged = ?"
    params = [status, duration_logged]
    
    if end_time:
        query += ", end_time = ?"
        params.append(utc_now_sql())
        
    query += " WHERE id = ?"
    params.append(session_id)
    
    cursor.execute(query, tuple(params))
    conn.commit()
    conn.close()

def log_distraction(session_id: int, description: Optional[str] = None):
    """Log a distraction for a session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO distractions (session_id, timestamp, description) VALUES (?, ?, ?)",
        (session_id, utc_now_sql(), description)
    )
    
    conn.commit()
    conn.close()

def add_tags(session_id: int, tags: List[str]):
    """Add tags to a session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    for tag in tags:
        cursor.execute(
            "INSERT INTO tags (session_id, tag_name) VALUES (?, ?)",
            (session_id, tag)
        )
        
    conn.commit()
    conn.close()

def get_session_task_info(session_id: int) -> dict:
    """Get task and git info for a given session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.task_name, t.project_name, s.git_repo, s.git_branch
        FROM sessions s
        JOIN tasks t ON s.task_id = t.id
        WHERE s.id = ?
    """, (session_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "task_name": row["task_name"],
            "project_name": row["project_name"],
            "git_repo": row["git_repo"],
            "git_branch": row["git_branch"],
        }
    return {}

def get_recent_tasks(limit: int = 10, days: int | None = None, timezone_config: str = "auto") -> List[sqlite3.Row]:
    """Get recently accessed tasks for auto-completion."""
    conn = get_connection()
    cursor = conn.cursor()

    if days is not None:
        tz = get_display_tz(timezone_config)
        cutoff = retention_cutoff_utc(days, tz)
        cursor.execute(
            "SELECT * FROM tasks WHERE last_accessed >= ? ORDER BY last_accessed DESC LIMIT ?",
            (cutoff, limit,),
        )
    else:
        cursor.execute(
            "SELECT * FROM tasks ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    tasks = cursor.fetchall()
    conn.close()
    return tasks


def get_recent_projects(limit: int = 10, days: int | None = None, timezone_config: str = "auto") -> List[str]:
    """Get recently used project names."""
    conn = get_connection()
    cursor = conn.cursor()

    if days is not None:
        tz = get_display_tz(timezone_config)
        cutoff = retention_cutoff_utc(days, tz)
        cursor.execute(
            "SELECT DISTINCT project_name FROM tasks WHERE project_name IS NOT NULL AND last_accessed >= ? ORDER BY last_accessed DESC LIMIT ?",
            (cutoff, limit,),
        )
    else:
        cursor.execute(
            "SELECT DISTINCT project_name FROM tasks WHERE project_name IS NOT NULL ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [row["project_name"] for row in rows]

def get_recent_tag_names(limit: int = 30) -> List[str]:
    """Get recently used tag names."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT DISTINCT t.tag_name 
        FROM tags t
        JOIN sessions s ON t.session_id = s.id
        ORDER BY s.start_time DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["tag_name"] for row in rows]


def task_name_exists(task_name: str) -> bool:
    """Return True if any task exists with this name (case-insensitive)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM tasks WHERE task_name = ? COLLATE NOCASE LIMIT 1",
        (task_name,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def project_name_exists(project_name: str) -> bool:
    """Return True if any project exists with this name (case-insensitive)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM tasks
        WHERE project_name IS NOT NULL
          AND project_name = ? COLLATE NOCASE
        LIMIT 1
        """,
        (project_name,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_canonical_project_name(name: str) -> Optional[str]:
    """Return the most-recently-used existing project name matching ``name`` case-insensitively."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT project_name
        FROM tasks
        WHERE project_name IS NOT NULL
          AND project_name = ? COLLATE NOCASE
        ORDER BY last_accessed DESC
        LIMIT 1
        """,
        (name,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["project_name"] if row else None


def get_canonical_task_name(name: str) -> Optional[str]:
    """Return the most-recently-used existing task name matching ``name`` case-insensitively."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT task_name
        FROM tasks
        WHERE task_name = ? COLLATE NOCASE
        ORDER BY last_accessed DESC
        LIMIT 1
        """,
        (name,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["task_name"] if row else None


def log_session_event(
    session_id: int,
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a lifecycle event for a running or completed session."""
    conn = get_connection()
    cursor = conn.cursor()
    payload = json.dumps(details) if details else None
    cursor.execute(
        "INSERT INTO session_events (session_id, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
        (session_id, event_type, utc_now_sql(), payload),
    )
    conn.commit()
    conn.close()


def get_session_events(session_id: int) -> List[sqlite3.Row]:
    """Fetch ordered lifecycle events for a given session."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM session_events
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_distraction_timestamps_for_session(session_id: int) -> List[str]:
    """Return distraction timestamps (UTC SQL strings) ordered by time."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT timestamp
        FROM distractions
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
        """,
        (session_id,),
    )
    rows = [str(r["timestamp"]) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_sessions(limit: int) -> List[sqlite3.Row]:
    """
    Last ``limit`` sessions by ``start_time`` descending, with task and distraction
    aggregates (same shape as ``get_sessions_in_range`` rows, plus ``timer_mode``).
    """
    if limit < 1:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            s.id,
            SUBSTR(s.start_time, 3, 2) || printf('%04d', s.id) AS public_id,
            s.start_time,
            s.end_time,
            s.duration_logged,
            s.status,
            s.timer_mode,
            t.task_name,
            t.project_name,
            COUNT(d.id) AS distraction_count,
            GROUP_CONCAT(
                CASE
                    WHEN d.description IS NOT NULL AND TRIM(d.description) != '' THEN d.description
                END,
                ' | '
            ) AS distraction_notes
        FROM sessions s
        LEFT JOIN tasks t ON s.task_id = t.id
        LEFT JOIN distractions d ON d.session_id = s.id
        GROUP BY s.id
        ORDER BY s.start_time DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_session_listing_row(session_id: int) -> Optional[sqlite3.Row]:
    """One session with task and distraction aggregates (same columns as ``get_recent_sessions``)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            s.id,
            SUBSTR(s.start_time, 3, 2) || printf('%04d', s.id) AS public_id,
            s.start_time,
            s.end_time,
            s.duration_logged,
            s.status,
            s.timer_mode,
            t.task_name,
            t.project_name,
            COUNT(d.id) AS distraction_count,
            GROUP_CONCAT(
                CASE
                    WHEN d.description IS NOT NULL AND TRIM(d.description) != '' THEN d.description
                END,
                ' | '
            ) AS distraction_notes
        FROM sessions s
        LEFT JOIN tasks t ON s.task_id = t.id
        LEFT JOIN distractions d ON d.session_id = s.id
        WHERE s.id = ?
        GROUP BY s.id
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_session_distractions(session_id: int) -> List[sqlite3.Row]:
    """Distraction rows for a session, oldest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, timestamp, description
        FROM distractions
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_session_by_id(session_id: int) -> Optional[sqlite3.Row]:
    """Fetch a single session row by its primary key."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def resolve_session_identifier(identifier: str) -> Optional[int]:
    """
    Resolve either a short public ID (YY+session_pk) or a raw numeric PK.
    Returns the session PK if resolvable.
    """
    token = identifier.strip()
    if not token.isdigit():
        return None

    # Prefer short-ID resolution for identifiers shaped like YYxxxx.
    if len(token) >= 6:
        candidate_pk = int(token[2:])
        candidate = get_session_by_id(candidate_pk)
        if candidate:
            expected = format_session_public_id(candidate_pk, candidate["start_time"])
            if expected == token:
                return candidate_pk

    # Fallback to direct primary key lookup.
    candidate_pk = int(token)
    candidate = get_session_by_id(candidate_pk)
    if candidate:
        return candidate_pk
    return None


def edit_session(
    session_id: int,
    *,
    status: Optional[str] = None,
    duration_logged_seconds: Optional[int] = None,
) -> bool:
    """Edit mutable fields for an existing past session."""
    assignments: list[str] = []
    params: list[Any] = []

    if status is not None:
        assignments.append("status = ?")
        params.append(status)
    if duration_logged_seconds is not None:
        if duration_logged_seconds < 0:
            raise ValueError("duration_logged_seconds must be non-negative")
        assignments.append("duration_logged = ?")
        params.append(duration_logged_seconds)
    if not assignments:
        return False

    params.append(session_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE sessions SET {', '.join(assignments)} WHERE id = ?",
        tuple(params),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def repair_session(session_id: int) -> bool:
    """Mark a stuck ``running``/``paused`` row as ``stopped`` and set ``end_time`` if missing.

    Used when the daemon died without persisting (e.g. ``kill -9``). If
    ``duration_logged`` is 0, sets it to the non-negative whole-second span from
    ``start_time`` to the session end instant (existing ``end_time`` or ``now``).
    Non-zero ``duration_logged`` is left unchanged. Returns True if a row was updated.
    """
    conn = get_connection()
    cursor = conn.cursor()
    now_sql = utc_now_sql()
    cursor.execute(
        """
        UPDATE sessions
        SET status = 'stopped',
            end_time = COALESCE(end_time, ?),
            duration_logged = CASE
                WHEN IFNULL(duration_logged, 0) = 0 THEN MAX(
                    0,
                    CAST(
                        ROUND(
                            (
                                julianday(COALESCE(end_time, ?))
                                - julianday(start_time)
                            ) * 86400.0
                        ) AS INTEGER
                    )
                )
                ELSE duration_logged
            END
        WHERE id = ?
          AND status IN ('running', 'paused')
        """,
        (now_sql, now_sql, session_id),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def cancel_session(session_id: int) -> bool:
    """Mark a past session as killed (cancelled)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE sessions
        SET status = 'killed',
            end_time = COALESCE(end_time, ?)
        WHERE id = ?
        """,
        (utc_now_sql(), session_id),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def delete_session_cascade(session_id: int) -> bool:
    """Delete a session and all dependent records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tags WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM distractions WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_sessions_in_range(
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
) -> List[sqlite3.Row]:
    """Get sessions with task and distraction summaries, optionally filtered by UTC interval."""
    conn = get_connection()
    cursor = conn.cursor()
    where_clause = "1=1"
    params: tuple[Any, ...] = ()
    if start_utc and end_utc:
        where_clause = "s.start_time >= ? AND s.start_time < ?"
        params = (start_utc, end_utc)
    cursor.execute(
        """
        SELECT
            s.id,
            SUBSTR(s.start_time, 3, 2) || printf('%04d', s.id) AS public_id,
            s.start_time,
            s.end_time,
            s.duration_logged,
            s.status,
            t.task_name,
            t.project_name,
            COUNT(d.id) AS distraction_count,
            GROUP_CONCAT(
                CASE
                    WHEN d.description IS NOT NULL AND TRIM(d.description) != '' THEN d.description
                END,
                ' | '
            ) AS distraction_notes
        FROM sessions s
        LEFT JOIN tasks t ON s.task_id = t.id
        LEFT JOIN distractions d ON d.session_id = s.id
        WHERE {where_clause}
        GROUP BY s.id
        ORDER BY s.start_time DESC
        """.format(where_clause=where_clause),
        params,
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
