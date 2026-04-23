import pytest
from pomocli.daemon.timer import PomodoroTimer, TimerState, TimerMode
import time

def test_timer_initial_state():
    timer = PomodoroTimer()
    assert timer.state == TimerState.STOPPED
    assert timer.time_left == 0

def test_timer_start():
    timer = PomodoroTimer()
    timer.start(duration_minutes=25, session_id=1)
    
    assert timer.state == TimerState.RUNNING
    assert timer.duration == 25 * 60
    assert 1490 <= timer.time_left <= 1500
    assert timer.session_id == 1
    timer.stop()

def test_timer_pause_resume():
    timer = PomodoroTimer()
    timer.start(duration_minutes=25, session_id=1)
    
    timer.pause()
    assert timer.state == TimerState.PAUSED
    
    timer.resume()
    assert timer.state == TimerState.RUNNING
    timer.stop()

def test_timer_tick():
    timer = PomodoroTimer()
    timer.start(duration_minutes=1, session_id=1)

    time.sleep(1.1)  # Wait for at least one tick
    assert timer.time_left < 60
    timer.stop()


def test_timer_elapsed_start_and_ticks():
    timer = PomodoroTimer()
    timer.start_elapsed(session_id=42)
    assert timer.state == TimerState.RUNNING
    assert timer.mode == TimerMode.ELAPSED
    assert timer.session_id == 42
    assert timer.time_left == 0
    assert timer.duration == 0
    time.sleep(2.2)
    assert timer.elapsed_seconds >= 2
    st = timer.get_status()
    assert st["timer_mode"] == "elapsed"
    assert st["elapsed_seconds"] == timer.elapsed_seconds
    timer.stop()


def test_timer_elapsed_pause_freezes():
    timer = PomodoroTimer()
    timer.start_elapsed(session_id=1)
    time.sleep(1.1)
    before = timer.elapsed_seconds
    timer.pause()
    time.sleep(1.0)
    assert timer.elapsed_seconds == before
    timer.resume()
    time.sleep(1.1)
    assert timer.elapsed_seconds > before
    timer.stop()


def test_timer_elapsed_add_time_noop():
    timer = PomodoroTimer()
    timer.start_elapsed(session_id=1)
    timer.add_time(5, counts_as_focus=True)
    assert timer.duration == 0
    assert timer.time_left == 0
    timer.stop()


def test_timer_elapsed_logged_focus_seconds():
    timer = PomodoroTimer()
    timer.start_elapsed(session_id=1)
    timer.elapsed_seconds = 123
    assert timer.logged_focus_seconds() == 123
    timer.stop()


def test_timer_countdown_get_status_elapsed_seconds():
    timer = PomodoroTimer()
    timer.start(duration_minutes=25, session_id=1)
    timer.time_left = timer.duration - 100
    st = timer.get_status()
    assert st["timer_mode"] == "countdown"
    assert st["elapsed_seconds"] == 100
    timer.stop()
