from io import StringIO

from rich.console import Console

from pomocli.db.connection import init_db, get_connection
from pomocli.db.operations import (
    add_tags,
    create_session,
    get_or_create_task,
    log_distraction,
    update_session,
)
from pomocli.ui import reports


def test_generate_report_includes_session_details_and_hm_totals(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Write docs", "Pomocli")
    session_id = create_session(task_id)
    update_session(session_id, "completed", duration_logged=3900, end_time=True)
    add_tags(session_id, ["docs"])
    log_distraction(session_id, "Slack ping")

    buffer = StringIO()
    mocker.patch.object(reports, "console", Console(file=buffer, force_terminal=False, width=200))
    reports.generate_report("all", timezone_config="auto")
    out = buffer.getvalue()

    assert "Pomodoro Report (All)" in out
    assert "Session Details (All)" in out
    assert "Total Time Logged:" in out
    assert "1h 5m" in out
    assert "Focus rate:" not in out
    assert "Total logged:" in out
    assert "Focus block success:" in out
    assert "Attention quality:" in out


def test_generate_report_daily_trend_fbs_atq_two_days(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Day split", "Pomocli")
    s1 = create_session(task_id)
    s2 = create_session(task_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE sessions SET start_time=?, end_time=?, status=?, duration_logged=?
        WHERE id=?
        """,
        ("2025-06-01 10:00:00", "2025-06-01 10:35:00", "completed", 1500, s1),
    )
    cur.execute(
        """
        UPDATE sessions SET start_time=?, end_time=?, status=?, duration_logged=?
        WHERE id=?
        """,
        ("2025-06-02 10:00:00", "2025-06-02 10:35:00", "completed", 1500, s2),
    )
    conn.commit()
    conn.close()

    buffer = StringIO()
    mocker.patch.object(reports, "console", Console(file=buffer, force_terminal=False, width=200))
    reports.generate_report("all", timezone_config="UTC")
    out = buffer.getvalue()

    assert "Focus rate:" not in out
    assert "Daily Trend" in out
    assert "2025-06-01" in out
    assert "2025-06-02" in out
    assert out.count("FBS") >= 2
    assert out.count("ATQ") >= 2


def test_generate_report_overnight_session_counts_on_start_day_only(mocker, tmp_path):
    """Session spanning local midnight is fully attributed to the start calendar day."""
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    task_id = get_or_create_task("Overnight", "Pomocli")
    sid = create_session(task_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE sessions SET start_time=?, end_time=?, status=?, duration_logged=?
        WHERE id=?
        """,
        ("2025-03-10 23:45:00", "2025-03-11 01:00:00", "completed", 90 * 60, sid),
    )
    conn.commit()
    conn.close()

    buffer = StringIO()
    mocker.patch.object(reports, "console", Console(file=buffer, force_terminal=False, width=200))
    reports.generate_report("all", timezone_config="UTC")
    out = buffer.getvalue()

    assert "Daily Trend" in out
    assert "2025-03-10" in out
    tail = out.split("Daily Trend", 1)[1]
    assert "2025-03-11" not in tail
    assert "1h 30m" in tail
