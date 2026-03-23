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

PYNPUT_AVAILABLE = False
if _INPUT_MONITOR_ENABLED:
    try:
        from pynput import keyboard, mouse
        PYNPUT_AVAILABLE = True
    except ImportError:
        pass




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


