import pytest
import sqlite3
import json
from pomocli.db.operations import (
    get_recent_tag_names,
    add_tags,
    create_session,
    get_or_create_task,
    task_name_exists,
    project_name_exists,
    log_session_event,
    get_session_events,
    get_sessions_in_range,
    log_distraction,
    update_session,
)
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


def test_task_and_project_exists_helpers(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    get_or_create_task("Write docs", "Pomocli")

    assert task_name_exists("write docs")
    assert project_name_exists("pomocli")
    assert not task_name_exists("missing task")
    assert not project_name_exists("missing project")


def test_session_events_persist_and_order(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Evented task")
    session_id = create_session(task_id)

    log_session_event(session_id, "start", {"duration_minutes": 25})
    log_session_event(session_id, "pause", {"source": "manual"})
    log_session_event(session_id, "resume")

    events = get_session_events(session_id)
    event_types = [row["event_type"] for row in events]
    assert event_types == ["start", "pause", "resume"]
    assert json.loads(events[0]["details"])["duration_minutes"] == 25
    assert json.loads(events[1]["details"])["source"] == "manual"
    assert events[2]["details"] is None


def test_get_sessions_in_range_includes_distraction_summary(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Write tests", "Pomocli")
    session_id = create_session(task_id)
    update_session(session_id, "completed", duration_logged=1500, end_time=True)
    log_distraction(session_id, "Slack ping")
    log_distraction(session_id, "Email")

    rows = get_sessions_in_range("1970-01-01 00:00:00", "2999-01-01 00:00:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["task_name"] == "Write tests"
    assert row["project_name"] == "Pomocli"
    assert row["status"] == "completed"
    assert row["distraction_count"] == 2
    assert "Slack ping" in (row["distraction_notes"] or "")
