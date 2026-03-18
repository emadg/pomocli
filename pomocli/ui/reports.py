from rich.console import Console
from rich.table import Table
from typing import List
import sqlite3
from ..db.connection import get_connection

console = Console()

def generate_report(period: str = "today"):
    """Generate a summary report for the given period."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if period == "today":
        date_filter = "date(start_time) = date('now')"
    elif period == "week":
        date_filter = "date(start_time) >= date('now', '-7 days')"
    else:
        date_filter = "1=1"
        
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
    
    cursor.execute(query)
    rows = cursor.fetchall()
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
