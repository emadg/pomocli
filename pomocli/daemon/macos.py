import os
import threading
from typing import Callable, Optional
import time

# macOS input monitoring (pynput) requires Accessibility permissions.
# Without them, macOS sends SIGABRT which kills the entire daemon process.
# These features are disabled by default and can be enabled via env var
# or config once the user has granted permissions to their terminal app.
#
# To enable: export POMO_ENABLE_INPUT_MONITOR=1
# (Requires granting Accessibility permission to your terminal in
#  System Settings > Privacy & Security > Accessibility)
_INPUT_MONITOR_ENABLED = os.environ.get("POMO_ENABLE_INPUT_MONITOR", "").strip() in (
    "1",
    "true",
    "yes",
)

try:
    import rumps
    RUMPS_AVAILABLE = True
except ImportError:
    RUMPS_AVAILABLE = False

PYNPUT_AVAILABLE = False
if _INPUT_MONITOR_ENABLED:
    try:
        from pynput import keyboard, mouse
        PYNPUT_AVAILABLE = True
    except ImportError:
        pass


class PomodoroStatusBar:
    """macOS menu bar status display. No-ops gracefully when rumps is unavailable."""

    def __init__(self, on_pause: Callable, on_stop: Callable):
        self.on_pause = on_pause
        self.on_stop = on_stop
        self._app = None
        self.available = RUMPS_AVAILABLE

        if RUMPS_AVAILABLE:
            try:
                self._app = _RumpsApp(on_pause, on_stop)
            except Exception:
                self.available = False

    def run(self):
        if self._app:
            self._app.run()

    def update_status(self, state: str, time_left: int):
        if not self._app:
            return
        try:
            if state == "stopped":
                self._app.title = "🍅"
            else:
                mins, secs = divmod(time_left, 60)
                icon = "🍅" if state == "running" else "⏸"
                self._app.title = f"{icon} {mins:02d}:{secs:02d}"
        except Exception:
            pass


if RUMPS_AVAILABLE:
    class _RumpsApp(rumps.App):
        def __init__(self, on_pause: Callable, on_stop: Callable):
            super().__init__("🍅", quit_button=None)
            self._on_pause = on_pause
            self._on_stop = on_stop
            self.menu = [
                rumps.MenuItem("Pause/Resume", callback=self._toggle_pause),
                rumps.MenuItem("Stop", callback=self._stop_session),
                None,
                rumps.MenuItem("Quit Daemon", callback=self._quit),
            ]

        def _toggle_pause(self, _):
            self._on_pause()

        def _stop_session(self, _):
            self._on_stop()

        def _quit(self, _):
            rumps.quit_application()


class IdleDetector:
    """Detects user inactivity via pynput. No-ops when pynput is unavailable."""

    def __init__(self, timeout_seconds: int, on_idle: Callable):
        self.timeout_seconds = timeout_seconds
        self.on_idle = on_idle
        self.last_activity = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.available = PYNPUT_AVAILABLE

    def _on_activity(self, *args):
        self.last_activity = time.time()

    def _check_idle(self):
        while self._running:
            if time.time() - self.last_activity > self.timeout_seconds:
                self.on_idle()
                self.last_activity = time.time()
            time.sleep(1)

    def start(self):
        if not PYNPUT_AVAILABLE:
            return

        self._running = True
        try:
            self.keyboard_listener = keyboard.Listener(on_press=self._on_activity)
            self.mouse_listener = mouse.Listener(
                on_move=self._on_activity, on_click=self._on_activity
            )
            self.keyboard_listener.start()
            self.mouse_listener.start()
        except Exception as e:
            print(f"Warning: Could not start idle detector listeners: {e}")
            self.available = False

        self._thread = threading.Thread(target=self._check_idle, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, "keyboard_listener"):
            try:
                self.keyboard_listener.stop()
            except Exception:
                pass
        if hasattr(self, "mouse_listener"):
            try:
                self.mouse_listener.stop()
            except Exception:
                pass


class GlobalHotkey:
    """Global hotkey listener (Cmd+Shift+D). No-ops when pynput is unavailable."""

    def __init__(self, on_distract: Callable):
        self.on_distract = on_distract
        self.listener = None
        self.available = PYNPUT_AVAILABLE

    def start(self):
        if not PYNPUT_AVAILABLE:
            return

        try:
            self.listener = keyboard.GlobalHotKeys(
                {"<cmd>+<shift>+d": self.on_distract}
            )
            self.listener.start()
        except Exception as e:
            print(f"Warning: Could not start global hotkey listener: {e}")
            self.available = False

    def stop(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
