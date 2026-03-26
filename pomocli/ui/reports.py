from rich.console import Console
from rich.table import Table
from typing import List
from collections import defaultdict
import sqlite3
from ..db.connection import get_connection
from ..time_util import report_time_bounds, get_display_tz, parse_stored_utc

console = Console()

def generate_report(period: str = "today", *, timezone_config: str = "auto"):
    """Generate a summary report for the given period."""
    conn = get_connection()
    cursor = conn.cursor()
    
    tz = get_display_tz(timezone_config)
    start_utc, end_utc = report_time_bounds(period, tz)
    
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
    
    # Group by local calendar date in Python
    daily_totals = defaultdict(int)
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
        
        mins, secs = divmod(duration, 60)
        hours, mins = divmod(mins, 60)
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
        
        table.add_row(project, task, sessions, completed, time_str)
        
    console.print(table)
    
    total_mins = total_time // 60
    t_hours, t_mins = divmod(total_mins, 60)
    console.print(f"\n[bold]Total Time Logged:[/bold] {t_hours}h {t_mins}m")

    if trend_rows and period != "today":
        console.print("\n[bold]Daily Trend:[/bold]")
        max_duration = max((r['daily_duration'] or 0) for r in trend_rows)
        if max_duration > 0:
            for r in trend_rows:
                day = r['day']
                dur = r['daily_duration'] or 0
                mins = dur // 60
                bar_len = int((dur / max_duration) * 40)
                bar = "█" * bar_len
                console.print(f"  {day} | {mins:3d}m | [blue]{bar}[/blue]")
