#!/usr/bin/env python3
"""Profile the real daemon and optional companion without touching personal data.

Example:
  python scripts/profile_linux.py --python .venv/bin/python \
    --companion linux/native/target/release/pomo-tray --seconds 3600 \
    --output /tmp/pomo-profile.json

The optional tray runs on a private D-Bus bus with a fake tray/notification host.
All databases/config/sockets are temporary. Desktop integrations are disabled
unless --desktop-integrations enables the private fake services; Wayland idle
remains unavailable. No GUI is launched. PSS apportions shared pages, RSS
includes every mapped page.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import subprocess
import tempfile
import time


def request(path, command, args=None):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(3)
        conn.connect(str(path))
        conn.sendall(json.dumps({"command": command, "args": args or {}}).encode())
        data = bytearray()
        while True:
            chunk = conn.recv(8192)
            if not chunk:
                break
            data.extend(chunk)
        response = json.loads(data)
        if response.get("status") != "ok":
            raise RuntimeError(response)
        return response.get("data")


def sample(pid):
    proc = Path("/proc") / str(pid)
    memory = {}
    for line in (proc / "smaps_rollup").read_text().splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            memory[parts[0].rstrip(":")] = int(parts[1])
    fields = (proc / "stat").read_text().split(") ", 1)[1].split()
    return {"rss_kib": memory["Rss"], "pss_kib": memory["Pss"],
            "pss_with_swap_kib": memory["Pss"] + memory.get("SwapPss", memory.get("Swap", 0)),
            "uss_kib": memory.get("Private_Clean", 0) + memory.get("Private_Dirty", 0),
            "swap_kib": memory.get("Swap", 0), "cpu_ticks": int(fields[11]) + int(fields[12]),
            "threads": len(list((proc / "task").iterdir())), "fds": len(list((proc / "fd").iterdir()))}


def wait_for(check, processes, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"Process {process.args} exited: {process.returncode}")
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for benchmark startup")


def run(args):
    repo = Path(__file__).resolve().parent.parent
    python = os.path.abspath(args.python)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    processes = []
    logs = []
    bus_pid = None
    with tempfile.TemporaryDirectory(prefix="pomocli-profile-") as directory:
        root = Path(directory)
        home = root / "home"
        config = home / ".config/pomocli"
        config.mkdir(parents=True)
        (config / "config.toml").write_text('sound_enabled = false\n[linux]\nautolaunch = false\ndesktop_integration = ' + ('true' if args.desktop_integrations else 'false') + '\n')
        path = config / "pomo.sock"
        env = dict(os.environ, HOME=str(home), POMOCLI_CONFIG_DIR=str(config), POMOCLI_SOCKET=str(path),
                   POMOCLI_DB_PATH=str(root / "demo.db"), PYTHONPATH=str(repo),
                   PYTHONDONTWRITEBYTECODE="1", WAYLAND_DISPLAY="/nonexistent-pomo-profile", DISPLAY="")
        env.pop("POMO_ENABLE_INPUT_MONITOR", None)
        wrapper = root / "pomo"
        wrapper.write_text(f"#!{python}\nfrom pomocli.cli.main import app\napp()\n")
        wrapper.chmod(0o700)
        env["POMOCLI_BIN"] = str(wrapper)
        try:
            subprocess.run([python, str(repo / "scripts/seed_test_db.py")], env=env, cwd=repo, check=True, capture_output=True)
            def start(command, label):
                log = (output.parent / (output.stem + "." + label + ".log")).open("w")
                logs.append(log)
                process = subprocess.Popen(command, env=env, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
                processes.append(process)
                return process
            daemon = start([python, "-m", "pomocli.daemon"], "daemon")
            wait_for(lambda: path.exists() and request(path, "ping"), processes)
            companion = None
            if args.companion:
                bus = subprocess.check_output(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1"], text=True).splitlines()
                env["DBUS_SESSION_BUS_ADDRESS"] = bus[0]
                env["DBUS_SYSTEM_BUS_ADDRESS"] = bus[0]
                env["POMOCLI_TEST_DESKTOP"] = "1"
                if args.desktop_integrations:
                    env["POMOCLI_TEST_INTEGRATIONS"] = "1"
                bus_pid = int(bus[1])
                start(["/usr/bin/python3", str(repo / "linux/tests/fake_desktop.py")], "desktop")
                time.sleep(0.3)
                companion = start([str(Path(args.companion).resolve())], "companion")
                time.sleep(1)
            subprocess.run([str(wrapper), "start", "Resource profile", "-p", "demo", "--elapsed"], env=env, cwd=repo, check=True, capture_output=True)
            time.sleep(1)
            tracked = {"daemon": daemon}
            if companion:
                tracked["companion"] = companion
            samples = {name: [] for name in tracked}
            start_stats = {name: sample(process.pid) for name, process in tracked.items()}
            begin = time.monotonic()
            deadline = begin + args.seconds
            last_saved = 0
            while time.monotonic() < deadline:
                for name, process in tracked.items():
                    if process.poll() is not None:
                        raise RuntimeError(f"{name} exited; inspect {output.stem}.{name}.log")
                    samples[name].append(sample(process.pid))
                elapsed = time.monotonic() - begin
                if elapsed - last_saved >= 30:
                    output.with_suffix(".progress.json").write_text(json.dumps({"elapsed_seconds": round(elapsed, 1), "last": {k: v[-1] for k, v in samples.items()}}, indent=2))
                    last_saved = elapsed
                time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
            elapsed = time.monotonic() - begin
            result = {"seconds": round(elapsed, 2), "python": subprocess.check_output([python, "--version"], text=True).strip(),
                      "desktop_integrations": args.desktop_integrations, "gui": False, "processes": {}}
            if companion:
                result["companion_sha256"] = hashlib.sha256(Path(f"/proc/{companion.pid}/exe").read_bytes()).hexdigest()
            for name, process in tracked.items():
                end = sample(process.pid)
                rows = samples[name]
                stats = {"pid": process.pid, "samples": len(rows),
                         "cpu_percent_one_core": round((end["cpu_ticks"] - start_stats[name]["cpu_ticks"]) / os.sysconf("SC_CLK_TCK") / elapsed * 100, 3)}
                for key in ("rss_kib", "pss_kib", "pss_with_swap_kib", "uss_kib", "swap_kib", "threads", "fds"):
                    stats[key] = {"first": rows[0][key], "last": rows[-1][key], "min": min(row[key] for row in rows), "max": max(row[key] for row in rows), "mean": round(statistics.mean(row[key] for row in rows), 2)}
                result["processes"][name] = stats
            result["combined_pss_mib"] = round(sum(p["pss_kib"]["mean"] for p in result["processes"].values()) / 1024, 3)
            result["combined_pss_with_swap_mib"] = round(sum(p["pss_with_swap_kib"]["mean"] for p in result["processes"].values()) / 1024, 3)
            output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2), flush=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if bus_pid:
                try:
                    os.kill(bus_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for log in logs:
                log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=".venv/bin/python")
    parser.add_argument("--companion")
    parser.add_argument("--desktop-integrations", action="store_true", help="Enable monitors against private fake desktop services; Wayland idle remains unavailable")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--output", default="/tmp/pomocli-profile.json")
    arguments = parser.parse_args()
    if arguments.seconds <= 0 or arguments.interval <= 0:
        parser.error("seconds and interval must be positive")
    if arguments.desktop_integrations and not arguments.companion:
        parser.error("--desktop-integrations requires --companion")
    run(arguments)
