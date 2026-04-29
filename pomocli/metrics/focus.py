"""
Focus metrics: Focus Block Success Rate and Attention Quality Rate.

Uses wall-clock session span (end_time - start_time), session_events for pauses,
and distractions table timestamps for capped recovery time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..time_util import parse_stored_utc

# Max refocus time charged per distraction (seconds).
DISTRACTION_RECOVERY_CAP_SECONDS = 10 * 60

# Minimum wall-clock span for Focus Block Success Rate qualifying sessions.
QUALIFYING_SESSION_MIN_SECONDS = 25 * 60


def _as_mapping(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """sqlite3.Row is not a dict and lacks .get(); use a plain mapping for metrics."""
    if isinstance(row, dict):
        return row
    return dict(row)


def pause_seconds_from_events(
    events: Iterable[Mapping[str, Any]],
    session_end_sql: str,
) -> int:
    """
    Sum pause/resume gaps from session_events.

    Each ``pause`` opens an interval closed by the next ``resume``, or by
    ``session_end_sql`` if the session ended while paused.
    """
    end_dt = parse_stored_utc(session_end_sql)
    total = 0
    pause_start: Optional[datetime] = None

    # sqlite3.Row has no .get(); normalize for sort and iteration.
    rows = [_as_mapping(e) for e in events]
    for ev in sorted(
        rows,
        key=lambda r: (str(r["timestamp"]), int(r.get("id") or 0)),
    ):
        et = str(ev["event_type"])
        ts = parse_stored_utc(str(ev["timestamp"]))
        if et == "pause":
            pause_start = ts
        elif et == "resume" and pause_start is not None:
            total += int(max(0, (ts - pause_start).total_seconds()))
            pause_start = None

    if pause_start is not None:
        total += int(max(0, (end_dt - pause_start).total_seconds()))

    return total


def total_distraction_recovery_seconds(
    distraction_timestamps_sql: Sequence[str],
    session_start_sql: str,
    session_end_sql: str,
) -> int:
    """
    Sum ``min(10 minutes, seconds remaining in session at distraction time)`` per
    distraction whose timestamp falls in ``[start, end)``.
    """
    start_dt = parse_stored_utc(session_start_sql)
    end_dt = parse_stored_utc(session_end_sql)
    total = 0
    for raw in distraction_timestamps_sql:
        ts = parse_stored_utc(str(raw))
        if ts < start_dt or ts >= end_dt:
            continue
        remaining = int(max(0, (end_dt - ts).total_seconds()))
        total += min(DISTRACTION_RECOVERY_CAP_SECONDS, remaining)
    return total


def _wall_span_seconds(row: Mapping[str, Any]) -> Optional[int]:
    st = row.get("start_time")
    en = row.get("end_time")
    if not st or not en:
        return None
    a = parse_stored_utc(str(st))
    b = parse_stored_utc(str(en))
    return int(max(0, (b - a).total_seconds()))


def _is_qualifying_focus_block(row: Mapping[str, Any]) -> bool:
    if row.get("status") == "killed":
        return False
    span = _wall_span_seconds(row)
    if span is None:
        return False
    return span >= QUALIFYING_SESSION_MIN_SECONDS


def focus_block_session_score(
    session_row: Mapping[str, Any],
    pause_event_count: int,
    distraction_count: int,
) -> float:
    """
    Per-session score for Focus Block Success Rate (qualifying sessions only).

    Starts at 1.0; subtracts 0.1 per pause event and per distraction.
    Contribution is floored at 0.0.
    """
    if not _is_qualifying_focus_block(session_row):
        return 0.0
    raw = 1.0 - 0.1 * (pause_event_count + distraction_count)
    return max(0.0, raw)


def attention_quality_effective_seconds(
    session_row: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    distraction_timestamps_sql: Sequence[str],
) -> Optional[int]:
    """
    Effective focus seconds for Attention Quality numerator (single session).

    ``wall - pause_seconds - distraction_recovery``. Returns None if there is
    no usable wall span. Killed sessions contribute None. Result floored at 0.
    """
    if session_row.get("status") == "killed":
        return None
    span = _wall_span_seconds(session_row)
    if span is None:
        return None
    st = str(session_row["start_time"])
    en = str(session_row["end_time"])
    pause_sec = pause_seconds_from_events(events, en)
    rec_sec = total_distraction_recovery_seconds(distraction_timestamps_sql, st, en)
    return max(0, span - pause_sec - rec_sec)


def focus_block_success_rate_value(
    numerator_sum: float,
    qualifying_count: int,
) -> Optional[float]:
    """Ratio numerator_sum / qualifying_count; None if no qualifying sessions."""
    if qualifying_count <= 0:
        return None
    return numerator_sum / qualifying_count


def attention_quality_rate_value(
    numerator_seconds: int,
    denominator_seconds: int,
) -> Optional[float]:
    """Attention quality ratio; None if denominator is 0."""
    if denominator_seconds <= 0:
        return None
    return numerator_seconds / denominator_seconds


@dataclass(frozen=True)
class FocusMetricsSummary:
    focus_block_success_rate: Optional[float]
    focus_block_qualifying_count: int
    focus_block_numerator: float
    attention_quality_rate: Optional[float]
    attention_quality_numerator_seconds: int
    attention_quality_denominator_seconds: int


def summarize_focus_metrics(session_rows: Sequence[Mapping[str, Any]]) -> FocusMetricsSummary:
    """
    Compute both metrics for session rows from ``get_sessions_in_range`` (or
    equivalent), loading events and distraction timestamps per session.
    """
    from ..db.operations import get_session_events, get_distraction_timestamps_for_session

    fb_num = 0.0
    fb_den = 0
    aq_num = 0
    aq_den = 0

    for row in session_rows:
        rm = _as_mapping(row)
        sid = int(rm["id"])
        events = get_session_events(sid)
        pause_n = sum(1 for e in events if str(e["event_type"]) == "pause")
        distract_n = int(rm.get("distraction_count") or 0)

        if _is_qualifying_focus_block(rm):
            fb_den += 1
            fb_num += focus_block_session_score(rm, pause_n, distract_n)

        span = _wall_span_seconds(rm)
        if span is None or rm.get("status") == "killed":
            continue
        aq_den += span
        d_ts = get_distraction_timestamps_for_session(sid)
        eff = attention_quality_effective_seconds(rm, events, d_ts)
        if eff is not None:
            aq_num += eff

    return FocusMetricsSummary(
        focus_block_success_rate=focus_block_success_rate_value(fb_num, fb_den),
        focus_block_qualifying_count=fb_den,
        focus_block_numerator=fb_num,
        attention_quality_rate=attention_quality_rate_value(aq_num, aq_den),
        attention_quality_numerator_seconds=aq_num,
        attention_quality_denominator_seconds=aq_den,
    )
