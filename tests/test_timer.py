import pytest
from pomocli.daemon.timer import PomodoroTimer, TimerState
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
