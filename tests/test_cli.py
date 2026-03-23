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

    # Test subcommand -h works
    result = runner.invoke(app, ["start", "-h"])
    assert result.exit_code == 0
    assert "Start a new pomodoro session" in result.stdout

    # Test shorthand command exists
    result = runner.invoke(app, ["ss", "--help"])
    assert result.exit_code == 0
    assert "Start a new pomodoro session" in result.stdout

def test_cli_dash_help():
    result = runner.invoke(app, ["dash", "--help"])
    assert result.exit_code == 0
    assert "--detail" in result.stdout
    assert "minimal, normal, full" in result.stdout
