import pytest
from typer.testing import CliRunner
from pomocli.cli.main import app

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "A lightweight, feature-rich CLI Pomodoro application." in result.stdout

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
    assert "A lightweight, feature-rich CLI Pomodoro application" in result.stdout

    # Shorthand commands should appear in main help
    for alias in ("ss", "pp", "rr", "sp", "dd", "stt"):
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
