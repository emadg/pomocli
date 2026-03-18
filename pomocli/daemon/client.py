import socket
import json
from pathlib import Path
from typing import Dict, Any, Optional

SOCKET_PATH = Path.home() / ".config" / "pomocli" / "pomo.sock"


def is_daemon_running() -> bool:
    """Check if the daemon is alive by attempting a socket connection."""
    if not SOCKET_PATH.exists():
        return False
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2.0)
        client.connect(str(SOCKET_PATH))
        client.sendall(json.dumps({"command": "ping", "args": {}}).encode("utf-8"))
        resp = client.recv(4096).decode("utf-8")
        client.close()
        return json.loads(resp).get("status") == "ok"
    except Exception:
        # Stale socket file - clean up
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
            except Exception:
                pass
        return False


class DaemonClient:
    def _send_command(
        self, command: str, args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not SOCKET_PATH.exists() or not is_daemon_running():
            return {"status": "error", "message": "Daemon is not running"}

        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect(str(SOCKET_PATH))

            request = {"command": command, "args": args or {}}
            client.sendall(json.dumps(request).encode("utf-8"))

            response_data = client.recv(4096).decode("utf-8")
            client.close()

            return json.loads(response_data)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def start(self, duration: int, session_id: int):
        return self._send_command("start", {"duration": duration, "session_id": session_id})

    def pause(self):
        return self._send_command("pause")

    def resume(self):
        return self._send_command("resume")

    def stop(self):
        return self._send_command("stop")

    def kill(self):
        return self._send_command("kill")

    def status(self):
        return self._send_command("status")

    def distract(self, description: Optional[str] = None):
        return self._send_command("distract", {"description": description})

    def ping(self):
        return self._send_command("ping")
