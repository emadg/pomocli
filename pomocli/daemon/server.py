import socket
import json
import os
import signal
import subprocess
from pathlib import Path
import threading
import sys
import logging
from .timer import PomodoroTimer, TimerState
from ..db.operations import update_session, log_distraction
from ..config import load_config
from .macos import IdleDetector
from .. import __build__

SOCKET_PATH = Path.home() / ".config" / "pomocli" / "pomo.sock"
PID_PATH = Path.home() / ".config" / "pomocli" / "pomo.pid"


def play_sound(sound_type: str):
    """Play a system sound based on event type."""
    sounds = {
        "start": "/System/Library/Sounds/Glass.aiff",
        "complete": "/System/Library/Sounds/Glass.aiff",
        "distract": "/System/Library/Sounds/Basso.aiff",
    }
    sound_file = sounds.get(sound_type)
    if sound_file and os.path.exists(sound_file):
        subprocess.Popen(
            ["afplay", sound_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class DaemonServer:
    def __init__(self):
        self.timer = PomodoroTimer()
        self.timer.on_tick = self._on_tick
        self.timer.on_complete = self._on_complete
        self._running = False
        self._stop_event = threading.Event()

        cfg = load_config()

        # macOS integrations - disabled on macOS in favor of the Swift app
        # On other platforms, IdleDetector may still work via pynput
        self.idle_detector = IdleDetector(
            timeout_seconds=cfg.get("idle_timeout", 300), on_idle=self._on_idle
        )

    def _toggle_pause(self):
        if self.timer.state == TimerState.RUNNING:
            self.timer.pause()
        elif self.timer.state == TimerState.PAUSED:
            self.timer.resume()

    def _stop_session(self):
        if self.timer.session_id:
            logged = self.timer.duration - self.timer.time_left
            update_session(self.timer.session_id, "stopped", logged, end_time=True)
        self.timer.stop()

    def _on_idle(self):
        if self.timer.state == TimerState.RUNNING:
            self.timer.pause()

    def _extend_on_distract(self):
        """Extend timer by configured minutes when a distraction is logged."""
        cfg = load_config()
        extend = cfg.get("distraction_extend_minutes", 0)
        if extend and extend > 0:
            self.timer.add_time(extend)

    def _on_distract(self):
        if self.timer.session_id and self.timer.state == TimerState.RUNNING:
            log_distraction(self.timer.session_id, "Quick distraction via hotkey")
            self._extend_on_distract()
            play_sound("distract")

    def _on_tick(self, time_left: int):
        pass

    def _on_complete(self):
        if self.timer.session_id:
            update_session(
                self.timer.session_id, "completed", self.timer.duration, end_time=True
            )
            play_sound("complete")

    def handle_client(self, conn: socket.socket):
        try:
            data = conn.recv(4096).decode("utf-8")
            if not data:
                return

            request = json.loads(data)
            command = request.get("command")
            args = request.get("args", {})

            response = {"status": "ok"}

            if command == "start":
                duration = args.get("duration", 25)
                session_id = args.get("session_id")
                self.timer.start(duration, session_id)
                play_sound("start")
            elif command == "pause":
                self.timer.pause()
            elif command == "resume":
                self.timer.resume()
            elif command == "stop":
                if self.timer.session_id:
                    logged = self.timer.duration - self.timer.time_left
                    update_session(
                        self.timer.session_id, "stopped", logged, end_time=True
                    )
                self.timer.stop()
            elif command == "kill":
                if self.timer.session_id:
                    logged = self.timer.duration - self.timer.time_left
                    update_session(
                        self.timer.session_id, "killed", logged, end_time=True
                    )
                self.timer.stop()
            elif command == "distract":
                desc = args.get("description")
                if self.timer.session_id and self.timer.state == TimerState.RUNNING:
                    log_distraction(self.timer.session_id, desc)
                    self._extend_on_distract()
                    play_sound("distract")
                else:
                    response = {
                        "status": "error",
                        "message": "No active session running",
                    }
            elif command == "status":
                status_data = self.timer.get_status()
                if status_data.get("session_id"):
                    try:
                        from ..db.operations import get_session_task_info
                        info = get_session_task_info(status_data["session_id"])
                        if info:
                            status_data.update(info)
                    except Exception as e:
                        logging.error(f"Failed to enrich status: {e}")
                response["data"] = status_data
            elif command == "ping":
                response["data"] = "pong"
            elif command == "shutdown":
                self._stop_event.set()
            else:
                response = {"status": "error", "message": "Unknown command"}

            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(
                    json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                )
            except Exception:
                pass
        finally:
            conn.close()

    def start(self):
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        # Write PID file so CLI can check if daemon is alive
        PID_PATH.write_text(str(os.getpid()))

        log_level = os.environ.get("POMO_LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ"
        )
        logging.Formatter.converter = time.gmtime

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(SOCKET_PATH))
        self.server.listen(5)
        self.server.settimeout(1.0)  # Allow periodic check of stop event
        self._running = True

        logging.info(f"Daemon {__build__} listening on {SOCKET_PATH} (PID {os.getpid()})")
        sys.stdout.flush()

        # Handle SIGTERM/SIGINT for clean shutdown
        def _signal_handler(signum, frame):
            logging.info("Received shutdown signal")
            self._stop_event.set()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Start optional background listeners (no-op if unavailable or on macOS)
        if sys.platform != "darwin":
            try:
                self.idle_detector.start()
            except Exception as e:
                logging.warning(f"Idle detector unavailable: {e}")
        else:
            logging.debug("Skipping Python IdleDetector on macOS (handled by Swift app)")

        # Main loop - just accept socket connections
        try:
            while not self._stop_event.is_set():
                try:
                    conn, _ = self.server.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client, args=(conn,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            self.stop()

    def stop(self):
        logging.info("Shutting down daemon")
        self._running = False
        self._stop_event.set()
        self.timer.stop()
        self.idle_detector.stop()
        try:
            self.server.close()
        except Exception:
            pass
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        if PID_PATH.exists():
            PID_PATH.unlink()


if __name__ == "__main__":
    server = DaemonServer()
    server.start()
