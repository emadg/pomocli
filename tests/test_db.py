import pytest
import sqlite3
from pomocli.db.operations import get_recent_tag_names, add_tags, create_session, get_or_create_task
from pomocli.db.connection import init_db, get_connection

def test_get_recent_tag_names(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()
    
    task_id = get_or_create_task("Test Task")
    session_id1 = create_session(task_id)
    add_tags(session_id1, ["python", "cli"])
    
    session_id2 = create_session(task_id)
    add_tags(session_id2, ["python", "rust"])
    
    tags = get_recent_tag_names(limit=10)
    assert "python" in tags
    assert "cli" in tags
    assert "rust" in tags
    assert len(tags) == 3
