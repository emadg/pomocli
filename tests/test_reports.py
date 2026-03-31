from io import StringIO

from rich.console import Console

from pomocli.db.connection import init_db
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
    assert "Focus rate:" in out
