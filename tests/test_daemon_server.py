import json
import socket
import threading

from pomocli.daemon.server import DaemonServer
from pomocli.daemon.timer import TimerMode, TimerState


def _send(server: DaemonServer, command: str, args: dict | None = None) -> dict:
    left, right = socket.socketpair()
    try:
        payload = json.dumps({"command": command, "args": args or {}}).encode("utf-8")
        right.sendall(payload)
        thread = threading.Thread(target=server.handle_client, args=(left,))
        thread.start()
        response = json.loads(right.recv(4096).decode("utf-8"))
        thread.join(timeout=1.0)
        return response
    finally:
        try:
            left.close()
        except Exception:
            pass
        right.close()


def test_manual_lifecycle_commands_emit_events(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch.object(server.timer, "start")
    mocker.patch.object(server.timer, "pause")
    mocker.patch.object(server.timer, "resume")
    mocker.patch.object(server.timer, "stop")
    mocker.patch("pomocli.daemon.server.update_session")

    _send(server, "start", {"duration": 25, "session_id": 9})

    server.timer.session_id = 9
    server.timer.state = TimerState.RUNNING
    _send(server, "pause")

    server.timer.session_id = 9
    server.timer.state = TimerState.PAUSED
    _send(server, "resume")

    server.timer.session_id = 9
    server.timer.state = TimerState.RUNNING
    server.timer.duration = 1500
    server.timer.time_left = 1000
    server.timer.focus_duration = 1500
    _send(server, "stop")

    server.timer.session_id = 9
    server.timer.state = TimerState.RUNNING
    server.timer.duration = 1500
    server.timer.time_left = 1200
    server.timer.focus_duration = 1500
    _send(server, "kill")

    assert log_event.call_args_list[0].args[:2] == (9, "start")
    assert log_event.call_args_list[1].args[:2] == (9, "pause")
    assert log_event.call_args_list[2].args[:2] == (9, "resume")
    assert log_event.call_args_list[3].args[:2] == (9, "stop")
    assert log_event.call_args_list[4].args[:2] == (9, "kill")


def test_extend_and_idle_emit_events(mocker):
    server = DaemonServer()
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch("pomocli.daemon.server.load_config", return_value={"distraction_extend_minutes": 2})
    add_time = mocker.patch.object(server.timer, "add_time")
    pause = mocker.patch.object(server.timer, "pause")

    server.timer.session_id = 12
    server.timer.state = TimerState.RUNNING
    response = _send(server, "extend")
    assert response["status"] == "ok"
    add_time.assert_called_once_with(2, counts_as_focus=True)
    assert log_event.call_args_list[0].args[:2] == (12, "extend")

    server.timer.session_id = 12
    server.timer.state = TimerState.RUNNING
    server._on_idle()
    pause.assert_called_once()
    assert log_event.call_args_list[1].args[:2] == (12, "idle")
    assert log_event.call_args_list[2].args[:2] == (12, "pause")


def test_extend_elapsed_mode_returns_error(mocker):
    server = DaemonServer()
    server.timer.session_id = 3
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.ELAPSED
    add_time = mocker.patch.object(server.timer, "add_time")
    response = _send(server, "extend")
    assert response["status"] == "error"
    assert "elapsed" in response["message"].lower()
    add_time.assert_not_called()


def test_distract_elapsed_does_not_extend_timer(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.load_config", return_value={"distraction_extend_minutes": 5})
    mocker.patch("pomocli.daemon.server.play_sound")
    log_distraction = mocker.patch("pomocli.daemon.server.log_distraction")
    add_time = mocker.patch.object(server.timer, "add_time")

    server.timer.session_id = 7
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.ELAPSED

    response = _send(server, "distract", {"description": "slack"})
    assert response["status"] == "ok"
    log_distraction.assert_called_once_with(7, "slack")
    add_time.assert_not_called()


def test_start_elapsed_invokes_start_elapsed(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    start_elapsed = mocker.patch.object(server.timer, "start_elapsed")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    _send(server, "start", {"session_id": 99, "timer_mode": "elapsed"})
    start_elapsed.assert_called_once_with(99)
    assert log_event.call_args[0][:2] == (99, "start")
    assert log_event.call_args[0][2].get("mode") == "elapsed"


def test_stop_elapsed_uses_logged_seconds(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    mocker.patch("pomocli.daemon.server.log_session_event")
    update = mocker.patch("pomocli.daemon.server.update_session")
    logged = mocker.patch.object(
        server.timer, "logged_focus_seconds", return_value=333
    )
    mocker.patch.object(server.timer, "stop")

    server.timer.session_id = 5
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.ELAPSED
    _send(server, "stop")
    logged.assert_called_once()
    update.assert_called_once_with(5, "stopped", 333, end_time=True)


def test_complete_elapsed_marks_completed(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    update = mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch.object(server.timer, "stop")
    logged = mocker.patch.object(
        server.timer, "logged_focus_seconds", return_value=1200
    )

    server.timer.session_id = 8
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.ELAPSED
    response = _send(server, "complete")
    assert response["status"] == "ok"
    logged.assert_called_once()
    log_event.assert_called_once_with(8, "complete")
    update.assert_called_once_with(8, "completed", 1200, end_time=True)


def test_complete_elapsed_when_paused(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch.object(server.timer, "stop")
    mocker.patch.object(server.timer, "logged_focus_seconds", return_value=60)

    server.timer.session_id = 8
    server.timer.state = TimerState.PAUSED
    server.timer.mode = TimerMode.ELAPSED
    response = _send(server, "complete")
    assert response["status"] == "ok"


def test_complete_countdown_returns_error(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    update = mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch.object(server.timer, "stop")

    server.timer.session_id = 3
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.COUNTDOWN
    response = _send(server, "complete")
    assert response["status"] == "error"
    assert "elapsed" in response["message"].lower()
    update.assert_not_called()


def test_status_response_includes_db_path(mocker, tmp_path):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.DB_PATH", tmp_path / "daemon.sqlite")
    response = _send(server, "status")
    assert response["status"] == "ok"
    assert response["data"]["db_path"] == str((tmp_path / "daemon.sqlite").resolve())


def test_complete_no_active_session(mocker):
    server = DaemonServer()
    server.timer.session_id = None
    server.timer.state = TimerState.STOPPED
    server.timer.mode = TimerMode.ELAPSED
    response = _send(server, "complete")
    assert response["status"] == "error"


def test_shutdown_command_sets_stop_event(mocker):
    server = DaemonServer()
    response = _send(server, "shutdown")
    assert response["status"] == "ok"
    assert server._stop_event.is_set()


def test_daemon_stop_persists_running_session(mocker):
    server = DaemonServer()
    update = mocker.patch("pomocli.daemon.server.update_session")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch.object(server.timer, "stop")
    logged = mocker.patch.object(
        server.timer, "logged_focus_seconds", return_value=42
    )

    server.timer.session_id = 11
    server.timer.state = TimerState.RUNNING
    server.stop()

    logged.assert_called_once()
    update.assert_called_once_with(11, "stopped", 42, end_time=True)
    log_event.assert_called_once_with(11, "stop", {"source": "daemon_shutdown"})


def test_daemon_stop_does_not_clobber_post_countdown_stopped(mocker):
    """After natural complete, timer is STOPPED but session_id may linger; DB is already completed."""
    server = DaemonServer()
    update = mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch.object(server.timer, "stop")

    server.timer.session_id = 11
    server.timer.state = TimerState.STOPPED
    server.stop()

    update.assert_not_called()


def test_start_supersedes_prior_running_session(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    update = mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch.object(server.timer, "start")

    server.timer.session_id = 1
    server.timer.state = TimerState.RUNNING
    server.timer.duration = 1500
    server.timer.time_left = 900
    server.timer.focus_duration = 1500
    logged = mocker.patch.object(
        server.timer, "logged_focus_seconds", return_value=600
    )

    _send(server, "start", {"duration": 25, "session_id": 2})

    logged.assert_called_once()
    update.assert_called_once_with(1, "stopped", 600, end_time=True)
    assert log_event.call_args_list[0].args[:2] == (1, "stop")
    assert log_event.call_args_list[0].args[2].get("source") == "superseded_by_start"
    assert log_event.call_args_list[1].args[:2] == (2, "start")
