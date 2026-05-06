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
    get_recent_sessions,
    get_session_listing_row,
    get_session_distractions,
    log_distraction,
    update_session,
    format_session_public_id,
    resolve_session_identifier,
    delete_session_cascade,
    get_session_by_id,
    repair_session,
    get_canonical_project_name,
    get_canonical_task_name,
    get_recent_repos_for_project,
    get_recent_branches_for_project_repo,
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
    assert row["public_id"] == format_session_public_id(session_id, row["start_time"])


def test_resolve_session_identifier_short_and_pk(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Resolver task")
    session_id = create_session(task_id)
    row = get_session_by_id(session_id)
    assert row is not None
    public_id = format_session_public_id(session_id, row["start_time"])

    assert resolve_session_identifier(public_id) == session_id
    assert resolve_session_identifier(str(session_id)) == session_id
    assert resolve_session_identifier("not-an-id") is None


def test_get_recent_sessions_and_listing_row_and_distractions(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Inspect task", "Proj")
    s1 = create_session(task_id)
    s2 = create_session(task_id)
    log_distraction(s2, "ping")
    update_session(s1, "completed", 60 * 25, end_time=True)
    update_session(s2, "completed", 60 * 5, end_time=True)

    recent = get_recent_sessions(2)
    assert len(recent) == 2
    assert {int(r["id"]) for r in recent} == {s1, s2}
    s2_row = next(r for r in recent if int(r["id"]) == s2)
    assert int(s2_row["distraction_count"]) == 1

    row = get_session_listing_row(s2)
    assert row is not None
    assert row["task_name"] == "Inspect task"
    assert "ping" in (row["distraction_notes"] or "")

    drows = get_session_distractions(s2)
    assert len(drows) == 1
    assert "ping" in (drows[0]["description"] or "")


def test_delete_session_cascade_removes_related_rows(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Delete task")
    session_id = create_session(task_id)
    add_tags(session_id, ["cleanup"])
    log_distraction(session_id, "Message")
    log_session_event(session_id, "start")

    assert delete_session_cascade(session_id)
    assert get_session_by_id(session_id) is None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM tags WHERE session_id = ?", (session_id,))
    tags_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM distractions WHERE session_id = ?", (session_id,))
    distractions_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM session_events WHERE session_id = ?", (session_id,))
    events_count = cur.fetchone()["c"]
    conn.close()

    assert tags_count == 0
    assert distractions_count == 0
    assert events_count == 0


def test_repair_session_closes_running_and_paused(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Repair me")
    sid_run = create_session(task_id)
    sid_pause = create_session(task_id)

    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET status = 'paused', end_time = NULL WHERE id = ?",
        (sid_pause,),
    )
    conn.execute(
        "UPDATE sessions SET start_time = '2020-06-15 10:00:00', duration_logged = 0 "
        "WHERE id IN (?, ?)",
        (sid_run, sid_pause),
    )
    conn.commit()
    conn.close()

    assert repair_session(sid_run)
    assert repair_session(sid_pause)

    row_a = get_session_by_id(sid_run)
    row_b = get_session_by_id(sid_pause)
    assert row_a["status"] == "stopped"
    assert row_b["status"] == "stopped"
    assert row_a["end_time"] is not None
    assert row_b["end_time"] is not None
    assert row_a["duration_logged"] > 3600
    assert row_b["duration_logged"] > 3600

    assert not repair_session(sid_run)


def test_repair_session_preserves_nonzero_duration_logged(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Keep duration")
    sid = create_session(task_id)
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET duration_logged = 555, start_time = '2020-06-15 10:00:00' "
        "WHERE id = ?",
        (sid,),
    )
    conn.commit()
    conn.close()

    assert repair_session(sid)
    assert get_session_by_id(sid)["duration_logged"] == 555


def test_repair_session_zero_duration_uses_existing_end_time(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Span me")
    sid = create_session(task_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE sessions SET
            start_time = '2020-06-15 10:00:00',
            end_time = '2020-06-15 10:30:00',
            duration_logged = 0,
            status = 'running'
        WHERE id = ?
        """,
        (sid,),
    )
    conn.commit()
    conn.close()

    assert repair_session(sid)
    row = get_session_by_id(sid)
    assert row["status"] == "stopped"
    assert row["end_time"] == "2020-06-15 10:30:00"
    assert row["duration_logged"] == 30 * 60


def test_repair_session_noop_on_completed(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Done")
    sid = create_session(task_id)
    update_session(sid, "completed", 60, end_time=True)
    assert not repair_session(sid)


def _bump_task_last_accessed(task_id: int, ts: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE tasks SET last_accessed = ? WHERE id = ?", (ts, task_id))
    conn.commit()
    conn.close()


def test_get_canonical_project_name_basic(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    get_or_create_task("Whatever", "NuCLEAR")

    assert get_canonical_project_name("nuclear") == "NuCLEAR"
    assert get_canonical_project_name("NUCLEAR") == "NuCLEAR"
    assert get_canonical_project_name("NuCLEAR") == "NuCLEAR"
    assert get_canonical_project_name("missing") is None


def test_get_canonical_project_name_picks_most_recent_variant(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    older = get_or_create_task("a", "nuclear")
    newer = get_or_create_task("b", "NuCLEAR")
    _bump_task_last_accessed(older, "2024-01-01 00:00:00")
    _bump_task_last_accessed(newer, "2026-01-01 00:00:00")

    assert get_canonical_project_name("nuclear") == "NuCLEAR"


def test_get_canonical_task_name_basic(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    get_or_create_task("Refactor Auth", "Pomocli")

    assert get_canonical_task_name("refactor auth") == "Refactor Auth"
    assert get_canonical_task_name("REFACTOR AUTH") == "Refactor Auth"
    assert get_canonical_task_name("nope") is None


def test_get_canonical_task_name_picks_most_recent_variant(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    older = get_or_create_task("write Docs", "p1")
    newer = get_or_create_task("Write Docs", "p2")
    _bump_task_last_accessed(older, "2024-01-01 00:00:00")
    _bump_task_last_accessed(newer, "2026-01-01 00:00:00")

    assert get_canonical_task_name("write docs") == "Write Docs"


def _set_session_start_time(session_id: int, ts: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE sessions SET start_time = ? WHERE id = ?", (ts, session_id))
    conn.commit()
    conn.close()


def _seed_session(task_name: str, project: str, repo: str | None, branch: str | None,
                   start_time: str) -> int:
    task_id = get_or_create_task(task_name, project)
    sid = create_session(task_id, repo, branch)
    _set_session_start_time(sid, start_time)
    return sid


def test_get_recent_repos_for_project_orders_by_recency_and_scopes_by_project(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    _seed_session("a", "Pomocli", "alpha", "main", "2026-04-01 00:00:00")
    _seed_session("b", "Pomocli", "beta",  "main", "2026-04-10 00:00:00")
    _seed_session("c", "Pomocli", "alpha", "feat", "2026-04-20 00:00:00")  # alpha bumps
    _seed_session("d", "OtherProj", "gamma", "main", "2026-04-25 00:00:00")  # excluded
    _seed_session("e", "Pomocli", None,    None,   "2026-04-30 00:00:00")  # null repo excluded

    repos = get_recent_repos_for_project("Pomocli", limit=10)
    assert repos == ["alpha", "beta"]


def test_get_recent_repos_for_project_case_insensitive_match(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    _seed_session("a", "NuCLEAR", "alpha", "main", "2026-04-01 00:00:00")

    assert get_recent_repos_for_project("nuclear", limit=10) == ["alpha"]


def test_get_recent_repos_for_project_days_cutoff(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    # Old row (>1y ago) and very recent row; cutoff "last 14 days" excludes old.
    _seed_session("a", "P", "old_repo", "main", "2020-01-01 00:00:00")
    from pomocli.time_util import utc_now_sql
    _seed_session("b", "P", "new_repo", "main", utc_now_sql())

    repos = get_recent_repos_for_project("P", limit=10, days=14)
    assert "new_repo" in repos
    assert "old_repo" not in repos


def test_get_recent_branches_for_project_repo(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    _seed_session("a", "P", "alpha", "main", "2026-04-01 00:00:00")
    _seed_session("b", "P", "alpha", "feat-x", "2026-04-10 00:00:00")
    _seed_session("c", "P", "alpha", "main", "2026-04-20 00:00:00")  # bump main
    _seed_session("d", "P", "beta",  "release", "2026-04-25 00:00:00")  # different repo

    branches = get_recent_branches_for_project_repo("P", "alpha", limit=10)
    assert branches == ["main", "feat-x"]


def test_get_recent_repos_for_project_empty(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    assert get_recent_repos_for_project("Pomocli", limit=10) == []
    assert get_recent_branches_for_project_repo("Pomocli", "alpha", limit=10) == []

