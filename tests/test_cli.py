import pytest
import types
from datetime import timezone
from typer.testing import CliRunner
from pomocli.cli.main import app
from pomocli.cli import main

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "A lightweight, feature-rich CLI Pomodoro timer" in result.stdout

def test_cli_status_when_daemon_down(mocker):
    # Mock the client to return an error (daemon down)
    mocker.patch('pomocli.daemon.client.DaemonClient.status', return_value={"status": "error", "message": "Daemon is not running"})
    
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Not running" in result.stdout

def test_cli_status_running(mocker):
    # Mock the client to return a running state
    mock_status = {
        "status": "ok",
        "data": {
            "state": "running",
            "time_left": 1500,
            "duration": 1500,
            "session_id": 1
        }
    }
    mocker.patch('pomocli.daemon.client.DaemonClient.status', return_value=mock_status)
    
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Running" in result.stdout
    assert "25:00" in result.stdout

def test_cli_pause(mocker):
    mocker.patch('pomocli.daemon.client.DaemonClient.pause', return_value={"status": "ok"})
    
    result = runner.invoke(app, ["pause"])
    assert result.exit_code == 0
    assert "Session paused." in result.stdout

def test_cli_shorthand_and_help():
    # Test -h works
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "A lightweight, feature-rich CLI Pomodoro timer" in result.stdout

    # Shorthand commands should appear in main help
    for alias in ("ss", "pp", "rr", "sp", "dd", "stt", "ssn"):
        assert alias in result.stdout, f"shorthand '{alias}' missing from help"

    # Test subcommand -h works
    result = runner.invoke(app, ["start", "-h"])
    assert result.exit_code == 0
    assert "Start a new pomodoro session" in result.stdout

    # Test shorthand command exists
    result = runner.invoke(app, ["ss", "--help"])
    assert result.exit_code == 0
    assert "Shorthand for start" in result.stdout

def test_cli_dash_help():
    result = runner.invoke(app, ["dash", "--help"])
    assert result.exit_code == 0
    assert "--detail" in result.stdout
    assert "minimal, normal, full" in result.stdout

def test_cli_stop_confirm_yes(mocker):
    mocker.patch('pomocli.cli.main._is_interactive', return_value=True)
    mocker.patch('pomocli.daemon.client.DaemonClient.stop', return_value={"status": "ok"})
    result = runner.invoke(app, ["stop"], input="y\n")
    assert result.exit_code == 0
    assert "Session stopped and saved." in result.stdout

def test_cli_stop_confirm_no(mocker):
    mocker.patch('pomocli.cli.main._is_interactive', return_value=True)
    result = runner.invoke(app, ["stop"], input="N\n")
    assert result.exit_code == 0
    assert "Session not stopped." in result.stdout

def test_cli_stop_skip_confirm(mocker):
    mocker.patch('pomocli.daemon.client.DaemonClient.stop', return_value={"status": "ok"})
    result = runner.invoke(app, ["stop", "--yes"])
    assert result.exit_code == 0
    assert "Session stopped and saved." in result.stdout

def test_cli_report_month(mocker):
    # Just mock the generate_report to avoid DB dependency in CLI test
    mocker.patch('pomocli.cli.main.generate_report')
    result = runner.invoke(app, ["report", "month"])
    assert result.exit_code == 0

def test_cli_report_quarter(mocker):
    mocker.patch('pomocli.cli.main.generate_report')
    result = runner.invoke(app, ["report", "quarter"])
    assert result.exit_code == 0


def test_complete_tasks_dedupes_and_filters(mocker):
    mocker.patch("pomocli.cli.main.get_recent_tasks", return_value=[
        {"task_name": "Write docs"},
        {"task_name": "write tests"},
        {"task_name": "Write docs"},
    ])
    main._cached_task_names.cache_clear()
    values = list(main.complete_tasks("write"))
    assert values == ["Write docs", "write tests"]


def test_interactive_mode_ctrl_c_exits_cleanly(mocker, monkeypatch):
    class _BrokenPrompt:
        def ask(self):
            raise KeyboardInterrupt

    fake_questionary = types.SimpleNamespace(
        autocomplete=lambda *args, **kwargs: _BrokenPrompt()
    )
    monkeypatch.setitem(__import__("sys").modules, "questionary", fake_questionary)
    mocker.patch("pomocli.cli.main._is_interactive", return_value=True)

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Cancelled." in result.stdout


def test_cli_list_command(mocker):
    mocker.patch("pomocli.cli.main.load_config", return_value={"timezone": "auto"})
    mocker.patch("pomocli.cli.main.get_display_tz", return_value=timezone.utc)
    mocker.patch(
        "pomocli.cli.main.report_time_bounds",
        return_value=("2026-01-01 00:00:00", "2026-01-02 00:00:00"),
    )
    mocker.patch(
        "pomocli.cli.main.get_sessions_in_range",
        return_value=[
            {
                "id": 7,
                "public_id": "260007",
                "start_time": "2026-01-01 08:00:00",
                "project_name": "Pomocli",
                "task_name": "Write docs",
                "status": "completed",
                "duration_logged": 1500,
                "distraction_count": 1,
                "distraction_notes": "Slack ping",
            },
            {
                "id": 8,
                "public_id": "260008",
                "start_time": "2026-01-01 09:00:00",
                "project_name": None,
                "task_name": "Review PR",
                "status": "stopped",
                "duration_logged": 600,
                "distraction_count": 0,
                "distraction_notes": None,
            },
        ],
    )

    result = runner.invoke(app, ["session", "list"])
    assert result.exit_code == 0
    assert "Today's Sessions" in result.stdout
    assert "Focus rate:" in result.stdout
    assert "50% (1/2 completed)" in result.stdout
    assert "260007" in result.stdout


def test_cli_session_list_shorthand(mocker):
    mocker.patch("pomocli.cli.main.load_config", return_value={"timezone": "auto"})
    mocker.patch("pomocli.cli.main.get_display_tz", return_value=timezone.utc)
    mocker.patch(
        "pomocli.cli.main.report_time_bounds",
        return_value=("2026-01-01 00:00:00", "2026-01-02 00:00:00"),
    )
    mocker.patch(
        "pomocli.cli.main.get_sessions_in_range",
        return_value=[
            {
                "id": 7,
                "public_id": "260007",
                "start_time": "2026-01-01 08:00:00",
                "project_name": "Pomocli",
                "task_name": "Write docs",
                "status": "completed",
                "duration_logged": 1500,
                "distraction_count": 1,
                "distraction_notes": "Slack ping",
            }
        ],
    )

    result = runner.invoke(app, ["ssn", "list"])
    assert result.exit_code == 0
    assert "Today's Sessions" in result.stdout


def test_cli_session_edit(mocker):
    mocker.patch("pomocli.cli.main.resolve_session_identifier", return_value=7)
    mocker.patch(
        "pomocli.cli.main.get_session_by_id",
        return_value={"start_time": "2026-01-01 08:00:00"},
    )
    mocker.patch("pomocli.cli.main.format_session_public_id", return_value="260007")
    edited = mocker.patch("pomocli.cli.main.edit_session", return_value=True)

    result = runner.invoke(app, ["session", "edit", "260007", "--status", "completed", "-d", "30"])
    assert result.exit_code == 0
    edited.assert_called_once_with(7, status="completed", duration_logged_seconds=1800)
    assert "Updated session 260007" in result.stdout


def test_cli_session_cancel(mocker):
    mocker.patch("pomocli.cli.main.resolve_session_identifier", return_value=7)
    mocker.patch(
        "pomocli.cli.main.get_session_by_id",
        return_value={"start_time": "2026-01-01 08:00:00"},
    )
    mocker.patch("pomocli.cli.main.format_session_public_id", return_value="260007")
    cancelled = mocker.patch("pomocli.cli.main.cancel_session", return_value=True)

    result = runner.invoke(app, ["session", "cancel", "260007"])
    assert result.exit_code == 0
    cancelled.assert_called_once_with(7)
    assert "Cancelled session 260007" in result.stdout


def test_cli_session_delete_yes(mocker):
    mocker.patch("pomocli.cli.main.resolve_session_identifier", return_value=7)
    mocker.patch(
        "pomocli.cli.main.get_session_by_id",
        return_value={"start_time": "2026-01-01 08:00:00"},
    )
    mocker.patch("pomocli.cli.main.format_session_public_id", return_value="260007")
    deleted = mocker.patch("pomocli.cli.main.delete_session_cascade", return_value=True)

    result = runner.invoke(app, ["session", "delete", "260007", "--yes"])
    assert result.exit_code == 0
    deleted.assert_called_once_with(7)
    assert "Deleted session 260007" in result.stdout
