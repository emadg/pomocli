import json
import sqlite3
from typing import Optional, List, Dict, Any, cast
from .connection import get_connection
from ..time_util import utc_now_sql, retention_cutoff_utc, get_display_tz

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

def create_session(task_id: Optional[int], git_repo: Optional[str] = None, git_branch: Optional[str] = None) -> int:
    """Create a new session and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO sessions (task_id, start_time, git_repo, git_branch) VALUES (?, ?, ?, ?)",
        (task_id, utc_now_sql(), git_repo, git_branch)
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
