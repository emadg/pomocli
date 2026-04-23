import time
import threading
from typing import Optional, Callable
from enum import Enum


class TimerState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class TimerMode(str, Enum):
    COUNTDOWN = "countdown"
    ELAPSED = "elapsed"


class PomodoroTimer:
    def __init__(self):
        self.state = TimerState.STOPPED
        self.mode = TimerMode.COUNTDOWN
        self.duration = 0
        self.focus_duration = 0
        self.time_left = 0
        self.elapsed_seconds = 0
        self.session_id: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.on_tick: Optional[Callable[[int], None]] = None
        self.on_complete: Optional[Callable[[], None]] = None

    def start(self, duration_minutes: int, session_id: int):
        """Countdown Pomodoro: fixed duration, counts down to zero."""
        self.stop()
        self.mode = TimerMode.COUNTDOWN
        self.elapsed_seconds = 0
        self.duration = duration_minutes * 60
        self.focus_duration = self.duration
        self.time_left = self.duration
        self.session_id = session_id
        self.state = TimerState.RUNNING
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def start_elapsed(self, session_id: int):
        """Stopwatch: elapsed time increases while running; no auto-complete."""
        self.stop()
        self.mode = TimerMode.ELAPSED
        self.elapsed_seconds = 0
        self.duration = 0
        self.time_left = 0
        self.focus_duration = 0
        self.session_id = session_id
        self.state = TimerState.RUNNING
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self):
        if self.state == TimerState.RUNNING:
            self.state = TimerState.PAUSED

    def resume(self):
        if self.state == TimerState.PAUSED:
            self.state = TimerState.RUNNING

    def stop(self):
        self.state = TimerState.STOPPED
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.time_left = 0
        self.duration = 0
        self.focus_duration = 0
        self.elapsed_seconds = 0
        self.session_id = None
        self.mode = TimerMode.COUNTDOWN

    def add_time(self, minutes: int, counts_as_focus: bool = True):
        if self.mode == TimerMode.ELAPSED:
            return
        if self.state in (TimerState.RUNNING, TimerState.PAUSED):
            self.time_left += minutes * 60
            self.duration += minutes * 60
            if counts_as_focus:
                self.focus_duration += minutes * 60

    def logged_focus_seconds(self) -> int:
        """Seconds to persist on stop/kill (running focus only for countdown)."""
        if self.mode == TimerMode.ELAPSED:
            return self.elapsed_seconds
        return min(self.duration - self.time_left, self.focus_duration)

    def get_status(self) -> dict:
        if self.mode == TimerMode.COUNTDOWN:
            elapsed_display = max(0, self.duration - self.time_left)
        else:
            elapsed_display = self.elapsed_seconds
        return {
            "state": self.state.value,
            "timer_mode": self.mode.value,
            "time_left": self.time_left,
            "duration": self.duration,
            "focus_duration": self.focus_duration,
            "elapsed_seconds": elapsed_display,
            "session_id": self.session_id,
        }

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self.state == TimerState.RUNNING:
                if self.mode == TimerMode.ELAPSED:
                    self.elapsed_seconds += 1
                    if self.on_tick:
                        self.on_tick(self.time_left)
                elif self.time_left > 0:
                    self.time_left -= 1
                    if self.on_tick:
                        self.on_tick(self.time_left)
                else:
                    self.state = TimerState.STOPPED
                    if self.on_complete:
                        self.on_complete()
                    break
            time.sleep(1)
