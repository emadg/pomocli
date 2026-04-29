from rich.console import Console
from rich.table import Table
from datetime import tzinfo
from typing import Any, DefaultDict, List, Mapping, Optional, Sequence, cast
from collections import defaultdict
from ..db.connection import get_connection
from ..db.operations import get_sessions_in_range
from ..metrics.focus import summarize_focus_metrics
from ..time_util import (
    report_time_bounds,
    report_time_bounds_last_n_calendar_days,
    get_display_tz,
    format_local,
    format_duration_hm,
    local_date_iso_from_stored_utc,
)

console = Console()

_EPS = 1e-9
# Fixed width for daily FBS/ATQ numeric columns (monospace-friendly).
_RATE_VALUE_W = 6


def _rate_value_cell(prev: Optional[float], cur: Optional[float]) -> str:
    """
    Fixed-width colored cell for FBS or ATQ (green: n/a, no prior comparable, or
    cur >= prev; red: both comparable and cur < prev).
    """
    w = _RATE_VALUE_W
    if cur is None:
        inner = "n/a".rjust(w)
        return f"[green]{inner}[/green]"
    inner = f"{cur:>{w}.2f}"
    if prev is None or cur + _EPS >= prev:
        tag = "green"
    else:
        tag = "red"
    return f"[{tag}]{inner}[/{tag}]"


def _sessions_by_local_day(
    session_rows: List[Any], tz: tzinfo
) -> DefaultDict[str, List[Any]]:
    """Bucket sessions by **local start date** (see ``local_date_iso_from_stored_utc``)."""
    by_day: DefaultDict[str, List[Any]] = defaultdict(list)
    for sr in session_rows:
        st = sr["start_time"] if hasattr(sr, "keys") else None
        if not st:
            continue
        day = local_date_iso_from_stored_utc(str(st), tz)
        by_day[day].append(sr)
    return by_day

def generate_report(
    period: str = "today",
    *,
    timezone_config: str = "auto",
    last_n_days: Optional[int] = None,
):
    """
    Generate a summary report for the given period or last N local calendar days.

    Multi-day **Daily Trend** lines are: local start date, logged duration, fixed-width
    FBS and ATQ (colored vs the prior day), then a bar scaled to the busiest day.
    Sessions are bucketed by **local start date** (overnight sessions count on the
    start day; see ``local_date_iso_from_stored_utc``).
    """
    conn = get_connection()
    cursor = conn.cursor()

    tz = get_display_tz(timezone_config)
    start_utc: Optional[str]
    end_utc: Optional[str]
    if last_n_days is not None:
        start_utc, end_utc = report_time_bounds_last_n_calendar_days(last_n_days, tz)
        title_scope = f"Last {last_n_days} days"
        show_daily_trend = last_n_days >= 2
    else:
        start_utc, end_utc = report_time_bounds(period, tz)
        title_scope = period.capitalize()
        show_daily_trend = period != "today"
    
    params: tuple[str, str] | tuple[()]
    if start_utc and end_utc:
        date_filter = "s.start_time >= ? AND s.start_time < ?"
        params = (start_utc, end_utc)
    else:
        date_filter = "1=1"
        params = ()
        
    query = f"""
        SELECT 
            t.task_name, 
            t.project_name,
            COUNT(s.id) as session_count,
            SUM(s.duration_logged) as total_duration,
            SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) as completed_count
        FROM sessions s
        JOIN tasks t ON s.task_id = t.id
        WHERE {date_filter}
        GROUP BY t.id
        ORDER BY total_duration DESC
    """
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    trend_query = f"""
        SELECT 
            s.start_time,
            s.duration_logged
        FROM sessions s
        WHERE {date_filter}
    """
    cursor.execute(trend_query, params)
    raw_trend_rows = cursor.fetchall()
    session_rows = get_sessions_in_range(start_utc, end_utc)
    
    # Group logged duration by local **session start** calendar day (overnight
    # sessions count entirely toward the start day, not the end day).
    daily_totals: DefaultDict[str, int] = defaultdict(int)
    for r in raw_trend_rows:
        if not r["start_time"]:
            continue
        local_day = local_date_iso_from_stored_utc(str(r["start_time"]), tz)
        daily_totals[local_day] += int(r["duration_logged"] or 0)
        
    trend_rows: list[dict[str, Any]] = [
        {"day": day, "daily_duration": dur} for day, dur in sorted(daily_totals.items())
    ]
    
    conn.close()
    
    table = Table(title=f"Pomodoro Report ({title_scope})")
    
    table.add_column("Project", style="cyan")
    table.add_column("Task", style="magenta")
    table.add_column("Sessions", justify="right", style="green")
    table.add_column("Completed", justify="right", style="green")
    table.add_column("Time Logged", justify="right", style="yellow")
    
    total_time = 0
    
    for row in rows:
        project = row['project_name'] or "-"
        task = row['task_name']
        sessions = str(row['session_count'])
        completed = str(row['completed_count'])
        duration = int(row["total_duration"] or 0)
        total_time += duration

        table.add_row(project, task, sessions, completed, format_duration_hm(duration))
        
    console.print(table)
    
    console.print(f"\n[bold]Total Time Logged:[/bold] {format_duration_hm(int(total_time))}")

    if session_rows:
        detail_table = Table(title=f"Session Details ({title_scope})")
        detail_table.add_column("Session", justify="right", style="cyan")
        detail_table.add_column("Start", style="cyan")
        detail_table.add_column("Project", style="magenta")
        detail_table.add_column("Task", style="magenta")
        detail_table.add_column("Status", style="green")
        detail_table.add_column("Logged", justify="right", style="yellow")
        detail_table.add_column("Distract", justify="right", style="yellow")
        detail_table.add_column("Notes", style="white")

        total_logged_sessions = 0
        for row in session_rows:
            logged = int(row["duration_logged"] or 0)
            total_logged_sessions += logged
            session_display = (
                row["public_id"] if "public_id" in row.keys() and row["public_id"] else str(row["id"])
            )
            detail_table.add_row(
                session_display,
                format_local(row["start_time"], timezone_config),
                row["project_name"] or "-",
                row["task_name"] or "-",
                row["status"],
                format_duration_hm(logged),
                str(row["distraction_count"] or 0),
                row["distraction_notes"] or "-",
            )

        console.print()
        console.print(detail_table)
        fm = summarize_focus_metrics(cast(Sequence[Mapping[str, Any]], session_rows))
        fb_line = (
            f"[bold]Focus Block Success (FBS):[/bold] {fm.focus_block_success_rate:.2f} "
            f"({fm.focus_block_numerator:.1f}/{fm.focus_block_qualifying_count} qualifying ≥25m)"
            if fm.focus_block_success_rate is not None
            else "[bold]Focus Block Success (FBS):[/bold] n/a (no qualifying ≥25m sessions)"
        )
        aq_line = (
            f"[bold]Attention Quality (ATQ):[/bold] {fm.attention_quality_rate:.2f} "
            f"({format_duration_hm(fm.attention_quality_numerator_seconds)} / "
            f"{format_duration_hm(fm.attention_quality_denominator_seconds)} wall)"
            if fm.attention_quality_rate is not None
            else "[bold]Attention Quality (ATQ):[/bold] n/a"
        )
        console.print(f"[bold]Total logged:[/bold] {format_duration_hm(total_logged_sessions)}")
        console.print(fb_line)
        console.print(aq_line)

    if trend_rows and show_daily_trend:
        console.print("\n[bold]Daily Trend:[/bold]")
        console.print(
            "[dim]  Day (local start) |   Logged | FBS | ATQ | bar (scaled to max day);"
            " FBS/ATQ vs prior row: green = n/a or same/better, red = worse[/dim]\n"
        )
        max_duration = max(int(r["daily_duration"] or 0) for r in trend_rows)
        by_day = _sessions_by_local_day(list(session_rows), tz) if session_rows else defaultdict(list)

        prev_fbs: Optional[float] = None
        prev_atq: Optional[float] = None
        for r in trend_rows:
            day = str(r["day"])
            dur = int(r["daily_duration"] or 0)
            hm_dur = format_duration_hm(dur)
            if max_duration > 0:
                bar_len = int((dur / max_duration) * 40)
                bar = "█" * bar_len
                bar_part = f" [blue]{bar}[/blue]"
            else:
                bar_part = " [dim]—[/dim]"

            day_sessions = by_day.get(day, [])
            fm_day = summarize_focus_metrics(cast(Sequence[Mapping[str, Any]], day_sessions))
            fbs = fm_day.focus_block_success_rate
            atq = fm_day.attention_quality_rate
            fbs_cell = _rate_value_cell(prev_fbs, fbs)
            atq_cell = _rate_value_cell(prev_atq, atq)
            if fbs is not None:
                prev_fbs = fbs
            if atq is not None:
                prev_atq = atq

            console.print(
                f" {day:<10} | {hm_dur:>8} | FBS {fbs_cell} | ATQ {atq_cell} |{bar_part}"
            )
        console.print()