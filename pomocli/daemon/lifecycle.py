"""Start/stop the pomocli socket daemon (shared by CLI and ensure_daemon)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..db.connection import DB_PATH
from .client import DaemonClient, is_daemon_running
from .server import PID_PATH

_START_POLL_ATTEMPTS = 6
_START_POLL_INTERVAL_SEC = 0.5
_STOP_POLL_ATTEMPTS = 20
_STOP_POLL_INTERVAL_SEC = 0.15


def cli_db_path() -> str:
    """Resolved SQLite path for the current environment (matches subprocess daemon)."""
    return str(Path(DB_PATH).resolve())


def start_daemon_background() -> tuple[bool, str]:
    """Spawn detached `python -m pomocli.daemon` if nothing healthy is listening."""
    if is_daemon_running():
        return True, "Daemon already running."

    subprocess.Popen(
        [sys.executable, "-m", "pomocli.daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(_START_POLL_ATTEMPTS):
        time.sleep(_START_POLL_INTERVAL_SEC)
        if is_daemon_running():
            return True, "Daemon started."

    return False, "Daemon may not have started (timeout waiting for socket)."


def stop_daemon(client: DaemonClient | None = None) -> tuple[bool, str]:
    """Graceful shutdown via socket, then SIGTERM using PID file if needed."""
    c = client or DaemonClient()

    if not is_daemon_running():
        _cleanup_stale_pid_file()
        return True, "Daemon was not running."

    resp = c.shutdown()
    if resp.get("status") != "ok":
        # Unresponsive daemon: still try SIGTERM from PID file
        pass

    for _ in range(_STOP_POLL_ATTEMPTS):
        if not is_daemon_running():
            _cleanup_stale_pid_file()
            return True, "Daemon stopped."

        time.sleep(_STOP_POLL_INTERVAL_SEC)

    # SIGTERM fallback
    pid = _read_daemon_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            return False, f"Could not signal daemon PID {pid} (permission denied)."

        for _ in range(_STOP_POLL_ATTEMPTS):
            if not is_daemon_running():
                _cleanup_stale_pid_file()
                return True, "Daemon stopped (after SIGTERM)."

            time.sleep(_STOP_POLL_INTERVAL_SEC)

    return False, "Daemon did not stop in time; try again or use pkill."


def _read_daemon_pid() -> int | None:
    try:
        raw = PID_PATH.read_text().strip()
        return int(raw)
    except (OSError, ValueError):
        return None


def _cleanup_stale_pid_file() -> None:
    """Remove PID file if the process is gone (stale state after crash)."""
    pid = _read_daemon_pid()
    if pid is None:
        if PID_PATH.exists():
            try:
                PID_PATH.unlink()
            except OSError:
                pass
        return
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        try:
            PID_PATH.unlink()
        except OSError:
            pass
    except PermissionError:
        pass
