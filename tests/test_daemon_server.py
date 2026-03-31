import json
import socket
import threading

from pomocli.daemon.server import DaemonServer
from pomocli.daemon.timer import TimerState


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
