"""Desktop clients must never mutate a replacement session or lose framing."""

import json
import socket
import threading

import pytest

from pomocli.config import DEFAULT_CONFIG
from pomocli.daemon.protocol import MAX_MESSAGE_BYTES, receive_json
from pomocli.daemon.server import DaemonServer
from pomocli.daemon.timer import TimerMode, TimerState


def command(server, name, **args):
    left, right = socket.socketpair()
    worker = threading.Thread(target=server.handle_client, args=(left,))
    worker.start()
    try:
        right.settimeout(3)
        right.sendall(json.dumps({"command": name, "args": args}).encode())
        return receive_json(right)
    finally:
        right.close()
        worker.join(timeout=3)
        assert not worker.is_alive()


@pytest.fixture
def active_server(mocker):
    server = DaemonServer()
    server.timer.session_id = 42
    server.timer.state = TimerState.RUNNING
    server.timer.mode = TimerMode.ELAPSED
    server.timer.elapsed_seconds = 123
    mocker.patch("pomocli.daemon.server.update_session")
    mocker.patch("pomocli.daemon.server.log_session_event")
    mocker.patch("pomocli.daemon.server.play_sound")
    return server


@pytest.mark.parametrize("action", ["pause", "resume", "stop", "kill", "complete", "distract", "extend"])
def test_stale_session_is_not_mutated(active_server, action):
    response = command(active_server, action, expected_session_id=41)
    assert response["status"] == "error"
    assert active_server.timer.session_id == 42
    assert active_server.timer.state == TimerState.RUNNING


def test_return_prompt_cannot_resume_manual_pause(active_server):
    command(active_server, "pause", source="idle", expected_session_id=42, expected_state="running")
    assert active_server.pause_source == "idle"
    command(active_server, "resume")
    command(active_server, "pause")
    response = command(active_server, "resume", expected_session_id=42, expected_state="paused", expected_pause_source="idle")
    assert response["status"] == "error"
    assert active_server.timer.state == TimerState.PAUSED
    assert active_server.pause_source == "manual"


def test_legacy_commands_and_guarded_return_work(active_server):
    assert command(active_server, "pause", source="screen_lock")["status"] == "ok"
    assert command(active_server, "resume", expected_session_id=42, expected_state="paused", expected_pause_source="screen_lock")["status"] == "ok"
    assert active_server.timer.state == TimerState.RUNNING
    assert active_server.pause_source is None


def test_guard_rejects_restarted_daemon(active_server):
    response = command(active_server, "stop", expected_session_id=42, expected_daemon_instance="previous-daemon")
    assert response["status"] == "error"
    assert active_server.timer.session_id == 42


def test_completion_is_distinct_from_stop_and_retained_in_status(active_server):
    assert command(active_server, "complete")["status"] == "ok"
    status = command(active_server, "status")["data"]
    assert status["completion_event"] == {"sequence": 1, "session_id": 42}
    assert status["daemon_instance"] == active_server.daemon_instance
    assert status["session_id"] is None
    assert command(active_server, "complete")["status"] == "error"
    assert active_server.completion_event["sequence"] == 1


def test_natural_completion_advances_marker(active_server):
    active_server._on_complete()
    assert active_server.completion_event == {"sequence": 1, "session_id": 42}
    active_server.timer.session_id = 43
    active_server._on_complete()
    assert active_server.completion_event == {"sequence": 2, "session_id": 43}
    command(active_server, "stop")
    assert active_server.completion_event["sequence"] == 2


def test_idle_source_records_idle_and_pause(active_server, mocker):
    events = mocker.patch("pomocli.daemon.server.log_session_event")
    command(active_server, "pause", source="idle")
    assert [(c.args[1], c.args[2:] or ()) for c in events.call_args_list] == [
        ("idle", ()), ("pause", ({"source": "idle"},)),
    ]


def test_fragmented_request_including_multibyte_text(active_server):
    left, right = socket.socketpair()
    worker = threading.Thread(target=active_server.handle_client, args=(left,))
    worker.start()
    data = json.dumps({"command": "status", "args": {"note": "🍅"}}, ensure_ascii=False).encode()
    try:
        right.settimeout(3)
        split = data.index("🍅".encode()) + 2
        right.sendall(data[:split])
        right.sendall(data[split:])
        assert receive_json(right)["status"] == "ok"
    finally:
        right.close()
        worker.join(timeout=3)


def test_response_larger_than_4096_bytes():
    left, right = socket.socketpair()
    value = {"data": {"task_name": "🍅" * 2000}}
    worker = threading.Thread(target=lambda: (left.sendall(json.dumps(value).encode()), left.close()))
    worker.start()
    try:
        assert receive_json(right) == value
    finally:
        right.close()
        worker.join(timeout=3)


def test_json_size_limit():
    left, right = socket.socketpair()
    try:
        left.sendall(b" " * MAX_MESSAGE_BYTES)
        with pytest.raises(ValueError, match="64 KiB"):
            receive_json(right)
    finally:
        left.close()
        right.close()


def test_linux_config_merges_without_changing_macos_defaults(mocker, tmp_path):
    from pomocli.config import load_config
    config = tmp_path / "config.toml"
    config.write_text('[linux]\nshow_tray = false\n')
    mocker.patch("pomocli.config.CONFIG_PATH", config)
    loaded = load_config()
    assert loaded["hotkey_distraction"] == "cmd+shift+d"
    assert loaded["linux"]["hotkey_distraction"] == "CTRL+ALT+d"
    assert loaded["linux"]["show_tray"] is False
    loaded["linux"]["autolaunch"] = False
    assert DEFAULT_CONFIG["linux"]["show_tray"] is True
    assert DEFAULT_CONFIG["linux"]["autolaunch"] is True


def test_optional_linux_launcher(mocker):
    from pomocli.daemon.desktop import launch_linux_companion
    mocker.patch("pomocli.daemon.desktop.load_config", return_value={"linux": {"autolaunch": True}})
    mocker.patch("pomocli.daemon.desktop.shutil.which", return_value="/opt/pomo-tray")
    popen = mocker.patch("pomocli.daemon.desktop.subprocess.Popen")
    launch_linux_companion()
    assert popen.call_args.args[0] == ["/opt/pomo-tray"]
    assert popen.call_args.kwargs["start_new_session"] is True
    mocker.patch("pomocli.daemon.desktop.load_config", return_value={"linux": {"autolaunch": False}})
    launch_linux_companion()
    assert popen.call_count == 1


def test_missing_or_failed_companion_does_not_break_cli(mocker):
    from pomocli.daemon.desktop import launch_linux_companion
    mocker.patch("pomocli.daemon.desktop.load_config", return_value={})
    which = mocker.patch("pomocli.daemon.desktop.shutil.which", return_value=None)
    popen = mocker.patch("pomocli.daemon.desktop.subprocess.Popen", side_effect=OSError("not executable"))
    launch_linux_companion()
    popen.assert_not_called()
    which.return_value = "/opt/pomo-tray"
    launch_linux_companion()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_config_edits_platform_shortcuts_without_replacing_other_platform(mocker, platform):
    from copy import deepcopy
    from types import SimpleNamespace
    from pomocli.cli import main

    config = deepcopy(DEFAULT_CONFIG)
    mocker.patch.object(main.sys, "platform", platform)
    mocker.patch.object(main, "_is_interactive", return_value=True)
    mocker.patch.object(main, "load_config", return_value=config)
    save = mocker.patch.object(main, "save_config")
    mocker.patch.object(main.console, "print")
    def text(_prompt, default):
        value = default.replace("+d", "+x").replace("+p", "+s")
        return SimpleNamespace(ask=lambda: value)
    mocker.patch("questionary.text", side_effect=text)
    mocker.patch("questionary.confirm", side_effect=lambda _prompt, default: SimpleNamespace(ask=lambda: default))
    main.config_cmd()
    save.assert_called_once_with(config)
    if platform == "linux":
        assert config["linux"]["hotkey_distraction"] == "CTRL+ALT+x"
        assert config["linux"]["hotkey_quick_start"] == "CTRL+ALT+s"
        assert config["hotkey_distraction"] == "cmd+shift+d"
        assert config["hotkey_quick_start"] == "cmd+shift+p"
    else:
        assert config["hotkey_distraction"] == "cmd+shift+x"
        assert config["hotkey_quick_start"] == "cmd+shift+s"
        assert config["linux"]["hotkey_distraction"] == "CTRL+ALT+d"
        assert config["linux"]["hotkey_quick_start"] == "CTRL+ALT+p"


def test_guarded_start_cannot_replace_session_started_during_dialog(active_server):
    response = command(active_server, "start", duration=25, session_id=43,
                       expected_state="stopped", expected_session_id=None,
                       expected_daemon_instance=active_server.daemon_instance)
    assert response["status"] == "error"
    assert active_server.timer.session_id == 42
    assert active_server.timer.state == TimerState.RUNNING


def test_python_start_passes_captured_status_guards(mocker):
    from pomocli.daemon.client import DaemonClient
    client = DaemonClient()
    send = mocker.patch.object(client, "_send_command", return_value={"status": "ok"})
    client.start(25, 43, expected_status={"state": "stopped", "session_id": None, "daemon_instance": "instance"})
    assert send.call_args.args[1]["expected_state"] == "stopped"
    assert send.call_args.args[1]["expected_session_id"] is None
    assert send.call_args.args[1]["expected_daemon_instance"] == "instance"


def test_cli_failed_start_returns_nonzero_and_finalizes_new_row(mocker):
    from typer.testing import CliRunner
    from pomocli.cli.main import app
    mocker.patch("pomocli.cli.main.init_db")
    mocker.patch("pomocli.cli.main.ensure_daemon")
    mocker.patch("pomocli.cli.main._require_daemon_db_matches_cli")
    mocker.patch("pomocli.cli.main._resolve_task_name", side_effect=lambda name: name)
    mocker.patch("pomocli.cli.main._resolve_project_name", side_effect=lambda name: name)
    mocker.patch("pomocli.cli.main.get_or_create_task", return_value=1)
    mocker.patch("pomocli.cli.main.create_session", return_value=43)
    mocker.patch("pomocli.cli.main.get_git_context", return_value=(None, None))
    mocker.patch("pomocli.cli.main.client.status", return_value={"status": "ok", "data": {"state": "stopped", "session_id": None}})
    mocker.patch("pomocli.cli.main.client.start", return_value={"status": "error", "message": "Session changed"})
    update = mocker.patch("pomocli.cli.main.update_session")
    result = CliRunner().invoke(app, ["start", "Example"])
    assert result.exit_code == 1
    assert "Failed to start" in result.stdout
    update.assert_called_once_with(43, "stopped", 0, end_time=True)


def test_macos_config_reader_ignores_linux_table(tmp_path):
    """Run the actual Foundation parser when the Swift compiler is available."""
    import shutil
    import subprocess
    from pathlib import Path
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler is unavailable on this machine")
    package = Path(__file__).resolve().parents[1] / "macos/PomoCLITimer"
    executable = tmp_path / "config-reader-tests"
    subprocess.run([compiler, str(package / "Sources/PomoCLITimer/ConfigReader.swift"),
                    str(package / "Tests/ConfigReaderTests.swift"), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
