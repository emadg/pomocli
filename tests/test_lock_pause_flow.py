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


def test_lock_pause_flow(mocker):
    server = DaemonServer()
    mocker.patch("pomocli.daemon.server.play_sound")
    mocker.patch("pomocli.daemon.server.update_session")
    log_event = mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch.object(server.timer, "start")
    mocker.patch.object(server.timer, "stop")

    # Start session
    _send(server, "start", {"duration": 25, "session_id": 42})
    server.timer.session_id = 42
    server.timer.state = TimerState.RUNNING

    # Pause with screen_lock source — simulates LockSleepMonitor
    resp = _send(server, "pause", {"source": "screen_lock"})
    assert resp["status"] == "ok"
    assert server.timer.state == TimerState.PAUSED

    pause_call = next(c for c in log_event.call_args_list if c.args[1] == "pause")
    assert pause_call.args[0] == 42
    assert pause_call.args[2] == {"source": "screen_lock"}

    # Resume — assert running
    server.timer.state = TimerState.PAUSED
    resp = _send(server, "resume")
    assert resp["status"] == "ok"
    assert server.timer.state == TimerState.RUNNING

    resume_call = next(c for c in log_event.call_args_list if c.args[1] == "resume")
    assert resume_call.args[0] == 42

    # Re-pause then stop — session should be stopped
    server.timer.state = TimerState.RUNNING
    _send(server, "pause", {"source": "screen_lock"})
    server.timer.state = TimerState.PAUSED
    server.timer.duration = 1500
    server.timer.time_left = 900
    server.timer.focus_duration = 1500
    mocker.patch.object(server.timer, "logged_focus_seconds", return_value=600)

    resp = _send(server, "stop")
    assert resp["status"] == "ok"

    stop_call = next(c for c in log_event.call_args_list if c.args[1] == "stop")
    assert stop_call.args[0] == 42
