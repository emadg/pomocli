import socket
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from ..config import CONFIG_DIR
from .protocol import receive_json

SOCKET_PATH = Path(os.environ.get("POMOCLI_SOCKET", CONFIG_DIR / "pomo.sock"))


def is_daemon_running() -> bool:
    """Check if the daemon is alive by attempting a socket connection."""
    if not SOCKET_PATH.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(str(SOCKET_PATH))
            client.sendall(json.dumps({"command": "ping", "args": {}}).encode("utf-8"))
            return receive_json(client).get("status") == "ok"
    except (OSError, ValueError):
        # A timeout is not evidence that the socket is stale. In particular,
        # never unlink another client's live socket while checking health.
        return False


class DaemonClient:
    def _send_command(
        self, command: str, args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not SOCKET_PATH.exists() or not is_daemon_running():
            return {"status": "error", "message": "Daemon is not running"}

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(5.0)
                client.connect(str(SOCKET_PATH))
                request = {"command": command, "args": args or {}}
                client.sendall(json.dumps(request).encode("utf-8"))
                return receive_json(client)
        except (OSError, ValueError) as e:
            return {"status": "error", "message": str(e)}

    def start(
        self,
        duration: int,
        session_id: int,
        *,
        timer_mode: str = "countdown",
        expected_status: Optional[Dict[str, Any]] = None,
    ):
        args: Dict[str, Any] = {
            "duration": duration,
            "session_id": session_id,
            "timer_mode": timer_mode,
        }
        if expected_status is not None:
            args["expected_state"] = expected_status.get("state", "stopped")
            args["expected_session_id"] = expected_status.get("session_id")
            if expected_status.get("daemon_instance") is not None:
                args["expected_daemon_instance"] = expected_status["daemon_instance"]
        return self._send_command("start", args)

    def pause(self, source: str | None = None):
        args: Dict[str, Any] = {}
        if source is not None:
            args["source"] = source
        return self._send_command("pause", args or None)

    def resume(self):
        return self._send_command("resume")

    def stop(self):
        return self._send_command("stop")

    def complete(self):
        """Mark the current elapsed (stopwatch) session as completed."""
        return self._send_command("complete")

    def kill(self):
        return self._send_command("kill")

    def status(self):
        return self._send_command("status")

    def distract(self, description: Optional[str] = None):
        return self._send_command("distract", {"description": description})

    def extend(self):
        return self._send_command("extend")

    def ping(self):
        return self._send_command("ping")

    def shutdown(self):
        """Ask the daemon to exit cleanly (socket server shutdown)."""
        return self._send_command("shutdown")
