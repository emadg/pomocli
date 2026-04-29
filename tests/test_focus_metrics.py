"""Tests for pomocli.metrics.focus."""

from pomocli.metrics.focus import (
    attention_quality_effective_seconds,
    focus_block_session_score,
    pause_seconds_from_events,
    total_distraction_recovery_seconds,
)


def test_pause_seconds_paired():
    events = [
        {"event_type": "start", "timestamp": "2025-01-15 13:00:00", "id": 1},
        {"event_type": "pause", "timestamp": "2025-01-15 13:30:00", "id": 2},
        {"event_type": "resume", "timestamp": "2025-01-15 13:45:00", "id": 3},
    ]
    assert pause_seconds_from_events(events, "2025-01-15 14:00:00") == 15 * 60


def test_pause_seconds_open_at_end():
    events = [
        {"event_type": "pause", "timestamp": "2025-01-15 13:45:00", "id": 1},
    ]
    assert pause_seconds_from_events(events, "2025-01-15 14:00:00") == 15 * 60


def test_distraction_recovery_capped():
    start = "2025-01-15 13:00:00"
    end = "2025-01-15 14:00:00"
    # At 13:45 -> 15 min left; recovery is capped at 10 minutes
    ts = ["2025-01-15 13:45:00"]
    assert total_distraction_recovery_seconds(ts, start, end) == 10 * 60

    # At 13:50 in 60 min session -> 10 min remaining -> full 10 min cap
    ts2 = ["2025-01-15 13:50:00"]
    assert total_distraction_recovery_seconds(ts2, start, end) == 10 * 60


def test_focus_block_session_score_example():
    row_ok = {
        "status": "completed",
        "start_time": "2025-01-15 13:00:00",
        "end_time": "2025-01-15 14:00:00",
    }
    assert focus_block_session_score(row_ok, pause_event_count=1, distraction_count=1) == 0.8
    assert focus_block_session_score(row_ok, pause_event_count=0, distraction_count=0) == 1.0


def test_focus_block_session_score_short_not_qualifying():
    row_short = {
        "status": "completed",
        "start_time": "2025-01-15 13:00:00",
        "end_time": "2025-01-15 13:20:00",
    }
    assert focus_block_session_score(row_short, pause_event_count=0, distraction_count=0) == 0.0


def test_attention_quality_example_sessions():
    # Session 1: 60 min, 15 min pause, distraction at 1:45 -> 15 min left -> 15 min recovery (not 10)
    s1 = {
        "status": "completed",
        "start_time": "2025-01-15 13:00:00",
        "end_time": "2025-01-15 14:00:00",
    }
    ev1 = [
        {"event_type": "pause", "timestamp": "2025-01-15 13:30:00", "id": 1},
        {"event_type": "resume", "timestamp": "2025-01-15 13:45:00", "id": 2},
    ]
    d1 = ["2025-01-15 13:45:00"]
    # 15 min remaining at distraction; recovery capped at 10 min -> 60 - 15 pause - 10 = 35 min
    assert attention_quality_effective_seconds(s1, ev1, d1) == 35 * 60

    # Session 2: 45 min, distraction at 3:10 with 5 min left -> 5 min recovery
    s2 = {
        "status": "stopped",
        "start_time": "2025-01-15 14:30:00",
        "end_time": "2025-01-15 15:15:00",
    }
    d2 = ["2025-01-15 15:10:00"]
    assert attention_quality_effective_seconds(s2, [], d2) == 40 * 60
