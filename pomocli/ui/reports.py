from rich.console import Console
from rich.table import Table
from typing import DefaultDict
from collections import defaultdict
from ..db.connection import get_connection
from ..db.operations import get_sessions_in_range
from ..time_util import (
    report_time_bounds,
    get_display_tz,
    parse_stored_utc,
    format_local,
    format_duration_hm,
)

console = Console()

def generate_report(period: str = "today", *, timezone_config: str = "auto"):
    """Generate a summary report for the given period."""
    conn = get_connection()
    cursor = conn.cursor()
    
    tz = get_display_tz(timezone_config)
    start_utc, end_utc = report_time_bounds(period, tz)
    
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
    
    # Group by local calendar date in Python
    daily_totals: DefaultDict[str, int] = defaultdict(int)
    for r in raw_trend_rows:
        if not r['start_time']:
            continue
        dt_utc = parse_stored_utc(r['start_time'])
        dt_local = dt_utc.astimezone(tz)
        local_day = dt_local.date().isoformat()
        daily_totals[local_day] += (r['duration_logged'] or 0)
        
    trend_rows = [{"day": day, "daily_duration": dur} for day, dur in sorted(daily_totals.items())]
    
    conn.close()
    
    table = Table(title=f"Pomodoro Report ({period.capitalize()})")
    
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
        duration = row['total_duration'] or 0
        total_time += duration
        
        table.add_row(project, task, sessions, completed, format_duration_hm(duration))
        
    console.print(table)
    
    console.print(f"\n[bold]Total Time Logged:[/bold] {format_duration_hm(total_time)}")

    if session_rows:
        detail_table = Table(title=f"Session Details ({period.capitalize()})")
        detail_table.add_column("Session", justify="right", style="cyan")
        detail_table.add_column("Start", style="cyan")
        detail_table.add_column("Project", style="magenta")
        detail_table.add_column("Task", style="magenta")
        detail_table.add_column("Status", style="green")
        detail_table.add_column("Logged", justify="right", style="yellow")
        detail_table.add_column("Distract", justify="right", style="yellow")
        detail_table.add_column("Notes", style="white")

        completed_sessions = 0
        total_logged_sessions = 0
        for row in session_rows:
            logged = int(row["duration_logged"] or 0)
            total_logged_sessions += logged
            if row["status"] == "completed":
                completed_sessions += 1
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
        focus_rate = (completed_sessions / len(session_rows)) * 100
        console.print(
            f"[bold]Focus rate:[/bold] {focus_rate:.0f}% ({completed_sessions}/{len(session_rows)} completed) | "
            f"[bold]Total logged:[/bold] {format_duration_hm(total_logged_sessions)}"
        )

    if trend_rows and period != "today":
        console.print("\n[bold]Daily Trend:[/bold]\n")
        max_duration = max((r['daily_duration'] or 0) for r in trend_rows)

        if max_duration > 0:
            for r in trend_rows:
                day = r['day']
                dur = r['daily_duration'] or 0
                hm_dur = format_duration_hm(dur)
                bar_len = int((dur / max_duration) * 40)
                bar = "█" * bar_len
                
                # normalize the bars to the same length for date and hm_dur
                console.print(f" {day:<10} | {hm_dur:>8} | [blue]{bar}[/blue]")
            console.print()