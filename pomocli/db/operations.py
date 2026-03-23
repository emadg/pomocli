import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from .connection import get_connection

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
        cursor.execute("UPDATE tasks SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
    else:
        cursor.execute(
            "INSERT INTO tasks (project_name, task_name, estimated_minutes) VALUES (?, ?, ?)",
            (project_name, task_name, estimated_minutes)
        )
        task_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return task_id

def create_session(task_id: Optional[int], git_repo: Optional[str] = None, git_branch: Optional[str] = None) -> int:
    """Create a new session and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO sessions (task_id, start_time, git_repo, git_branch) VALUES (?, CURRENT_TIMESTAMP, ?, ?)",
        (task_id, git_repo, git_branch)
    )
    session_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return session_id

def update_session(session_id: int, status: str, duration_logged: int, end_time: bool = False):
    """Update an existing session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "UPDATE sessions SET status = ?, duration_logged = ?"
    params = [status, duration_logged]
    
    if end_time:
        query += ", end_time = CURRENT_TIMESTAMP"
        
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
        "INSERT INTO distractions (session_id, description) VALUES (?, ?)",
        (session_id, description)
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

def get_recent_tasks(limit: int = 10, days: int | None = None) -> List[sqlite3.Row]:
    """Get recently accessed tasks for auto-completion."""
    conn = get_connection()
    cursor = conn.cursor()

    if days is not None:
        cursor.execute(
            f"SELECT * FROM tasks WHERE last_accessed >= datetime('now', '-{int(days)} days') ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    else:
        cursor.execute(
            "SELECT * FROM tasks ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    tasks = cursor.fetchall()
    conn.close()
    return tasks


def get_recent_projects(limit: int = 10, days: int | None = None) -> List[str]:
    """Get recently used project names."""
    conn = get_connection()
    cursor = conn.cursor()

    if days is not None:
        cursor.execute(
            f"SELECT DISTINCT project_name FROM tasks WHERE project_name IS NOT NULL AND last_accessed >= datetime('now', '-{int(days)} days') ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
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
    """Get recently used project names."""
    conn = get_connection()
    cursor = conn.cursor()

    if days is not None:
        cursor.execute(
            f"SELECT DISTINCT project_name FROM tasks WHERE project_name IS NOT NULL AND last_accessed >= datetime('now', '-{int(days)} days') ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    else:
        cursor.execute(
            "SELECT DISTINCT project_name FROM tasks WHERE project_name IS NOT NULL ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [row["project_name"] for row in rows]
