#!/usr/bin/env python3
"""Exercise the real daemon, tray and D-Bus API on a private desktop bus.

Needs distro python3-dbus/python3-gi, dbus-daemon and gdbus. The fake helper
never opens a window or registers real shortcuts. All data is temporary.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time

BUS = "org.pomocli.Desktop"
OBJECT = "/org/pomocli/Desktop"
INTERFACE = "org.pomocli.Desktop1"


def alive(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def run(args):
    repo = Path(__file__).resolve().parents[2]
    python = os.path.abspath(args.python)
    companion = os.path.abspath(args.companion)
    processes, logs, checks = [], [], []
    bus_pid = activated_pid = None
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pomo-linux-smoke-") as directory:
        root = Path(directory)
        config = root / "config"
        config.mkdir()
        (config / "config.toml").write_text('sound_enabled = false\n[linux]\nautolaunch = false\ndesktop_integration = ' + ("true" if args.integrations or args.activation else "false") + "\n")
        db = root / "demo.db"
        path = config / "pomo.sock"
        env = dict(os.environ, HOME=str(root), POMOCLI_CONFIG_DIR=str(config), POMOCLI_DB_PATH=str(db),
                   POMOCLI_SOCKET=str(path), PYTHONPATH=str(repo), PYTHONDONTWRITEBYTECODE="1",
                   POMOCLI_TEST_DESKTOP="1", DISPLAY="", WAYLAND_DISPLAY="/nonexistent-pomo-smoke")
        env.pop("POMO_ENABLE_INPUT_MONITOR", None)
        if args.integrations:
            env["POMOCLI_TEST_INTEGRATIONS"] = "1"
        if args.activation:
            env["POMOCLI_TEST_NO_PORTAL"] = "1"
            env["XDG_DATA_HOME"] = str(root / "data")
            services = root / "data/dbus-1/services"
            services.mkdir(parents=True)
            (services / "org.freedesktop.portal.Desktop.service").write_text(
                "[D-BUS Service]\nName=org.freedesktop.portal.Desktop\n"
                f"Exec=/usr/bin/python3 {repo / 'linux/tests/fake_desktop.py'} --portal-only\n")
        wrapper = root / "pomo"
        wrapper.write_text(f"#!{python}\nfrom pomocli.cli.main import app\napp()\n")
        wrapper.chmod(0o700)
        env["POMOCLI_BIN"] = str(wrapper)
        helper = root / "helper"
        pidfile = root / "helper-pids"
        helper.write_text(f'''#!{python}
import json, os, subprocess, sys, time
child = subprocess.Popen(['sleep', '60'])
with open({str(root / 'helper-token')!r}, 'w') as file: file.write(os.environ.get('XDG_ACTIVATION_TOKEN', ''))
with open({str(pidfile)!r}, 'w') as file: file.write(str(os.getpid()) + ' ' + str(child.pid))
choice = {str(root)!r} + ('/return-choice' if len(sys.argv) > 1 and sys.argv[1] == 'return' else '/quick-start-choice')
while not os.path.exists(choice): time.sleep(0.05)
with open(choice) as file: action = file.read().strip()
os.unlink(choice)
child.terminate(); child.wait()
print(json.dumps(dict(action=action)))
''')
        helper.chmod(0o700)
        env["POMOCLI_DIALOG_BIN"] = str(helper)
        env["XDG_ACTIVATION_TOKEN"] = "pomo-stale-inherited-token"
        def start(command, label):
            log = (output.parent / (output.stem + "." + label + ".log")).open("w")
            logs.append(log)
            process = subprocess.Popen(command, env=env, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process
        def wait(check, timeout=15):
            deadline = time.monotonic() + timeout
            error = None
            while time.monotonic() < deadline:
                try:
                    result = check()
                    if result:
                        return result
                except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                    error = exc
                time.sleep(0.1)
            raise AssertionError(f"Smoke condition timed out: {error}")
        def wire(command, arguments=None):
            with socket.socket(socket.AF_UNIX) as conn:
                conn.settimeout(3)
                conn.connect(str(path))
                conn.sendall(json.dumps({"command": command, "args": arguments or {}}).encode())
                data = bytearray()
                while True:
                    chunk = conn.recv(8192)
                    if not chunk:
                        break
                    data.extend(chunk)
                return json.loads(data)
        def cli(*arguments):
            return subprocess.run([str(wrapper), *arguments], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout
        def call(method, *arguments, dest=BUS, object_path=OBJECT):
            return subprocess.check_output(["gdbus", "call", "--session", "--dest", dest, "--object-path", object_path,
                                            "--method", method, *arguments], env=env, text=True, stderr=subprocess.PIPE).strip()
        def snapshot():
            text = call("org.freedesktop.DBus.Properties.Get", INTERFACE, "Snapshot")
            match = re.match(r"^\(<(.*)>,\)$", text, re.S)
            if not match:
                raise ValueError(f"Unexpected GVariant: {text}")
            return json.loads(ast.literal_eval(match.group(1)))
        def action(name):
            return json.loads(ast.literal_eval(call(INTERFACE + ".Action", name))[0])
        def passed(name):
            checks.append(name)
            print("PASS", name, flush=True)
        def notifications():
            file = output.parent / (output.stem + ".desktop.log")
            return file.read_text().count('"summary": "Session complete"')
        try:
            subprocess.run([python, "-c", "from pomocli.db.connection import init_db; init_db()"], env=env, cwd=repo, check=True)
            bus = subprocess.check_output(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1"], env=env, text=True).splitlines()
            env["DBUS_SESSION_BUS_ADDRESS"] = bus[0]
            env["DBUS_SYSTEM_BUS_ADDRESS"] = bus[0]
            bus_pid = int(bus[1])
            desktop_host = start(["/usr/bin/python3", str(repo / "linux/tests/fake_desktop.py")], "desktop")
            wait(lambda: "true" in call("org.freedesktop.DBus.Properties.Get", "org.kde.StatusNotifierWatcher", "IsStatusNotifierHostRegistered", dest="org.kde.StatusNotifierWatcher", object_path="/StatusNotifierWatcher"))
            daemon = start([python, "-m", "pomocli.daemon"], "daemon")
            wait(lambda: path.exists() and wire("ping")["status"] == "ok")
            if args.activation:
                owned = call("org.freedesktop.DBus.NameHasOwner", "org.freedesktop.portal.Desktop", dest="org.freedesktop.DBus", object_path="/org/freedesktop/DBus")
                assert "false" in owned, owned
            tray = start([companion], "companion")
            wait(lambda: snapshot()["connected"])
            registered = call("org.freedesktop.DBus.Properties.Get", "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems", dest="org.kde.StatusNotifierWatcher", object_path="/StatusNotifierWatcher")
            assert "/StatusNotifierItem" in registered, registered
            passed("actual StatusNotifier tray registration and initial snapshot")
            if args.activation:
                # NameHasOwner never activates the service itself.
                wait(lambda: "true" in call("org.freedesktop.DBus.NameHasOwner", "org.freedesktop.portal.Desktop", dest="org.freedesktop.DBus", object_path="/org/freedesktop/DBus"))
                def portal(method):
                    return call("org.pomocli.TestPortal." + method, dest="org.freedesktop.portal.Desktop", object_path="/org/freedesktop/portal/desktop")
                activated_pid = int(re.search(r"uint32 (\d+)", portal("Pid")).group(1))
                wait(lambda: "distract" in portal("Bindings") and "quick-start" in portal("Bindings"))
                passed("initially dormant portal is activated once and shortcuts are bound")
            subprocess.run([companion], env=env, timeout=5, check=True, capture_output=True)
            assert tray.poll() is None
            passed("duplicate launch exits without another resident instance")
            cli("start", "Countdown smoke", "-d", "25")
            wait(lambda: snapshot()["state"] == "running")
            assert action("quick-start")["status"] == "error"
            assert action("complete")["status"] == "error"
            assert action("pause")["status"] == "ok"
            wait(lambda: snapshot()["state"] == "paused")
            assert action("distract")["status"] == "error"
            assert action("resume")["status"] == "ok"
            wait(lambda: snapshot()["state"] == "running")
            assert action("distract")["status"] == "ok"
            assert action("distract")["status"] == "error"
            with sqlite3.connect(db) as conn:
                assert conn.execute("SELECT count(*) FROM distractions").fetchone()[0] == 1
            assert action("stop")["status"] == "ok"
            wait(lambda: snapshot()["state"] == "stopped")
            passed("countdown menu guards, pause/resume, distraction cooldown and stop")
            cli("start", "Elapsed smoke", "--elapsed")
            wait(lambda: snapshot()["state"] == "running" and snapshot()["timer_mode"] == "elapsed")
            assert action("complete")["status"] == "ok"
            wait(lambda: snapshot()["state"] == "stopped")
            wait(lambda: notifications() == 1)
            time.sleep(1.2)
            assert notifications() == 1
            with sqlite3.connect(db) as conn:
                assert conn.execute("SELECT status FROM sessions ORDER BY id DESC LIMIT 1").fetchone()[0] == "completed"
            passed("elapsed completion persists and notifies exactly once")
            completion_count = 1
            if args.natural_completion:
                cli("start", "Natural completion smoke", "-d", "1")
                wait(lambda: snapshot()["state"] == "running")
                wait(lambda: snapshot()["state"] == "stopped", timeout=75)
                wait(lambda: notifications() == 2)
                time.sleep(1.2)
                assert notifications() == 2
                with sqlite3.connect(db) as conn:
                    row = conn.execute("SELECT status, duration_logged FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
                    assert row == ("completed", 60), row
                completion_count = 2
                passed("real one-minute countdown completes, persists 60 seconds and notifies once")
            if args.integrations:
                def desktop(method, *arguments):
                    return call("org.pomocli.TestDesktop." + method, *arguments,
                                dest="org.pomocli.TestDesktop", object_path="/org/pomocli/TestDesktop")
                wait(lambda: "distract" in desktop("Bindings") and "quick-start" in desktop("Bindings"))
                passed("GlobalShortcuts CreateSession/BindShortcuts handshake")
                cli("start", "Integration session", "--elapsed")
                wait(lambda: snapshot()["state"] == "running")
                desktop("Shortcut", "distract")
                wait(lambda: snapshot().get("feedback"))
                with sqlite3.connect(db) as conn:
                    assert conn.execute("SELECT count(*) FROM distractions").fetchone()[0] == 2
                passed("portal Activated signal invokes guarded distraction")
                desktop("Lock", "true")
                wait(lambda: snapshot()["state"] == "paused" and snapshot()["pause_source"] == "screen_lock")
                cli("resume")
                cli("pause")
                wait(lambda: snapshot()["pause_source"] == "manual")
                desktop("Lock", "false")
                time.sleep(1.1)
                assert not pidfile.exists()
                passed("lock auto-pause and manual pause provenance prevents return prompt")
                cli("resume")
                wait(lambda: snapshot()["state"] == "running")
                desktop("Sleep", "true")
                wait(lambda: snapshot()["state"] == "paused")
                desktop("Lock", "true")
                desktop("Sleep", "false")
                time.sleep(0.5)
                assert not pidfile.exists()
                desktop("Lock", "false")
                wait(lambda: pidfile.exists())
                (root / "return-choice").write_text("resume")
                wait(lambda: snapshot()["state"] == "running")
                pidfile.unlink()
                passed("nested suspend/lock produces one return prompt and guarded resume")
                desktop("Sleep", "true")
                wait(lambda: snapshot()["state"] == "paused")
                desktop("Sleep", "false")
                wait(lambda: pidfile.exists())
                cli("stop")
                cli("start", "Replacement session", "--elapsed")
                wait(lambda: snapshot()["state"] == "running" and snapshot()["task_name"].casefold() == "replacement session")
                replacement_id = snapshot()["session_id"]
                (root / "return-choice").write_text("stop")
                time.sleep(1.5)
                assert snapshot()["session_id"] == replacement_id and snapshot()["state"] == "running"
                pidfile.unlink()
                assert action("stop")["status"] == "ok"
                wait(lambda: snapshot()["state"] == "stopped")
                passed("stale return dialog cannot stop replacement session")
                cli("start", "Already suspending", "--elapsed")
                wait(lambda: snapshot()["state"] == "running")
                desktop_host.terminate()
                desktop_host.wait(timeout=5)
                env["POMOCLI_TEST_PREPARING_SLEEP"] = "1"
                desktop_host = start(["/usr/bin/python3", str(repo / "linux/tests/fake_desktop.py")], "desktop-restarted")
                env.pop("POMOCLI_TEST_PREPARING_SLEEP")
                wait(lambda: "distract" in desktop("Bindings") and "quick-start" in desktop("Bindings"))
                wait(lambda: "/StatusNotifierItem" in call("org.freedesktop.DBus.Properties.Get", "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems", dest="org.kde.StatusNotifierWatcher", object_path="/StatusNotifierWatcher"))
                wait(lambda: snapshot()["state"] == "paused")
                wait(lambda: "uint32 0" in desktop("InhibitorsOpen"))
                desktop("Sleep", "false")
                wait(lambda: pidfile.exists())
                (root / "return-choice").write_text("resume")
                wait(lambda: snapshot()["state"] == "running")
                pidfile.unlink()
                wait(lambda: "uint32 1" in desktop("InhibitorsOpen"))
                passed("initial PreparingForSleep pauses, releases inhibitor and recovers on resume")
                desktop("Shortcut", "distract")
                wait(lambda: snapshot().get("feedback"))
                desktop("Lock", "true")
                wait(lambda: snapshot()["state"] == "paused")
                desktop("Lock", "false")
                wait(lambda: pidfile.exists())
                (root / "return-choice").write_text("resume")
                wait(lambda: snapshot()["state"] == "running")
                pidfile.unlink()
                assert action("stop")["status"] == "ok"
                wait(lambda: snapshot()["state"] == "stopped")
                passed("tray registration, portal identity/session and lock monitor recover after desktop service restart")
                desktop("Shortcut", "quick-start")
                wait(lambda: pidfile.exists())
                helper_pid, cli_pid = map(int, pidfile.read_text().split())
                assert (root / "helper-token").read_text() == "pomo-private-activation"
                (root / "quick-start-choice").write_text("cancel")
                wait(lambda: not alive(helper_pid) and not alive(cli_pid))
                pidfile.unlink()
                passed("fresh portal activation token reaches only its Quick Start helper")
            original = snapshot()["daemon_instance"]
            assert wire("shutdown")["status"] == "ok"
            daemon.wait(timeout=5)
            wait(lambda: not snapshot()["connected"])
            daemon = start([python, "-m", "pomocli.daemon"], "daemon-restarted")
            wait(lambda: snapshot()["connected"] and snapshot()["daemon_instance"] != original)
            assert notifications() == completion_count
            passed("daemon disconnect/restart recovery without replayed completion")
            assert action("quick-start")["status"] == "ok"
            wait(lambda: pidfile.exists())
            assert (root / "helper-token").read_text() == ""
            passed("ordinary helper launch discards stale inherited activation token")
            helper_pid, cli_pid = map(int, pidfile.read_text().split())
            assert alive(helper_pid) and alive(cli_pid)
            subprocess.run([companion, "--quit"], env=env, timeout=5, check=True, capture_output=True)
            tray.wait(timeout=5)
            wait(lambda: not alive(helper_pid) and not alive(cli_pid))
            assert wire("ping")["status"] == "ok"
            passed("quit cleans helper and descendants while preserving Python daemon")
            pidfile.unlink()
            tray = start([companion], "companion-term")
            wait(lambda: snapshot()["connected"])
            assert action("quick-start")["status"] == "ok"
            wait(lambda: pidfile.exists())
            helper_pid, cli_pid = map(int, pidfile.read_text().split())
            tray.terminate()
            tray.wait(timeout=5)
            wait(lambda: not alive(helper_pid) and not alive(cli_pid))
            passed("SIGTERM follows graceful helper cleanup")
            output.write_text(json.dumps({"passed": checks}, indent=2) + "\n")
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if pidfile.exists():
                for pid in map(int, pidfile.read_text().split()):
                    if alive(pid):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            if bus_pid:
                try:
                    os.kill(bus_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if activated_pid and alive(activated_pid):
                # This PID came from our private fake service, never the desktop.
                command = Path(f"/proc/{activated_pid}/cmdline").read_bytes()
                if b"fake_desktop.py" in command and b"--portal-only" in command:
                    try:
                        os.kill(activated_pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for log in logs:
                log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--companion", required=True)
    parser.add_argument("--integrations", action="store_true", help="Also simulate portals, lock and sleep on the private bus")
    parser.add_argument("--activation", action="store_true", help="Test cold D-Bus portal activation (separate from --integrations)")
    parser.add_argument("--natural-completion", action="store_true", help="Also wait for a real one-minute countdown to complete")
    parser.add_argument("--output", default="/tmp/pomocli-linux-smoke.json")
    options = parser.parse_args()
    if options.activation and options.integrations:
        parser.error("run --activation and --integrations separately")
    run(options)
