import typer
from rich.console import Console
from rich.table import Table
from typing import Optional, List
import subprocess
import sys
import os
import time

from ..daemon.client import DaemonClient, is_daemon_running
from ..db.operations import (
    get_or_create_task,
    create_session,
    get_recent_tasks,
    get_recent_projects,
    get_recent_tag_names,
    log_distraction,
    add_tags,
)
from ..db.connection import init_db, DB_PATH
from ..config import load_config, save_config, DEFAULT_CONFIG
from ..utils.git import get_git_context
from .. import __build__

app = typer.Typer(
    name="pomo",
    help="A lightweight, feature-rich CLI Pomodoro application.",
    add_completion=True,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()
client = DaemonClient()


def complete_tasks(incomplete: str):
    tasks = get_recent_tasks()
    for task in tasks:
        if incomplete.lower() in task["task_name"].lower():
            yield task["task_name"]


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------

def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _interactive_start() -> None:
    """Prompt the user to pick a task, project, duration, and tags, then start."""
    import questionary

    init_db()
    cfg = load_config()
    days = cfg.get("history_retention_days")

    # --- task selection ---
    recent = get_recent_tasks(limit=10, days=days)
    task_names = [t["task_name"] for t in recent]

    if task_names:
        choices = ["New task"] + task_names
        answer = questionary.autocomplete("Select a task:", choices=choices).ask()
        if answer is None:
            raise typer.Abort()
        if answer == "New task":
            task = questionary.text("Task name:").ask()
        else:
            task = answer
    else:
        task = questionary.text("Task name:").ask()

    if not task:
        raise typer.Abort()

    # --- project selection ---
    recent_projects = get_recent_projects(limit=10, days=days)
    if recent_projects:
        proj_choices = ["No project", "New project"] + recent_projects
        proj_answer = questionary.autocomplete("Select a project:", choices=proj_choices).ask()
        if proj_answer is None:
            raise typer.Abort()
        if proj_answer == "New project":
            project = questionary.text("Project name:").ask() or None
        elif proj_answer == "No project":
            project = None
        else:
            project = proj_answer
    else:
        project = questionary.text("Project name (leave blank for none):").ask() or None

    # --- duration ---
    default_dur = str(cfg.get("session_duration", 25))
    dur_str = questionary.text("Duration (minutes):", default=default_dur).ask()
    try:
        duration = int(dur_str)
    except (TypeError, ValueError):
        duration = int(default_dur)

    # --- tags ---
    recent_tags = get_recent_tag_names(limit=30)
    if recent_tags:
        tag_str = questionary.autocomplete(
            "Tags (comma-separated, or blank):", 
            choices=recent_tags,
        ).ask()
    else:
        tag_str = questionary.text("Tags (comma-separated, or blank):").ask()
        
    tags: list[str] | None = None
    if tag_str:
        tags = [t.strip() for t in tag_str.split(",") if t.strip()]

    _start_session(task, project, duration, estimate=None, tags=tags)


def _start_session(
    task: str,
    project: str | None,
    duration: int,
    estimate: int | None,
    tags: list[str] | None,
) -> None:
    """Core logic shared by CLI-args path and interactive path."""
    ensure_daemon()

    # Check if already running
    status_resp = client.status()
    if status_resp.get("status") == "ok" and status_resp.get("data", {}).get(
        "state"
    ) in ("running", "paused"):
        console.print(
            "[bold red]A session is already running. Stop or kill it first.[/bold red]"
        )
        raise typer.Exit(1)

    task_id = get_or_create_task(task, project, estimate)
    repo_name, branch_name = get_git_context()
    session_id = create_session(task_id, repo_name, branch_name)

    if tags:
        add_tags(session_id, tags)

    response = client.start(duration, session_id)
    if response.get("status") == "ok":
        parts = [f"[bold green]Started session for '{task}' ({duration}m)[/bold green]"]
        if project:
            parts.append(f"  Project: {project}")
        if repo_name:
            parts.append(f"  Git: {repo_name}/{branch_name}")
        if tags:
            parts.append(f"  Tags: {', '.join(tags)}")
        console.print("\n".join(parts))
    else:
        console.print(
            f"[bold red]Failed to start session: {response.get('message')}[/bold red]"
        )


def interactive_mode() -> None:
    """Full interactive command picker when `pomo` is run with no args."""
    import questionary

    if not _is_interactive():
        console.print("Run [bold]pomo --help[/bold] for usage information.")
        raise typer.Exit()

    commands = {
        # --- Timer ---
        "Start a session": "start",
        "Pause session": "pause",
        "Resume session": "resume",
        "Stop session": "stop",
        "Kill session": "kill",
        "Log distraction": "distract",
        # --- Info ---
        "Show status": "status",
        "View report": "report",
        "Open dashboard": "dash",
        # --- Settings ---
        "Configure settings": "config",
        "Initialize database": "init",
    }

    answer = questionary.autocomplete(
        "What would you like to do?",
        choices=list(commands.keys()),
    ).ask()

    if answer is None:
        raise typer.Abort()

    cmd = commands[answer]

    if cmd == "start":
        _interactive_start()
    elif cmd == "distract":
        desc = questionary.text("Distraction description (optional):").ask()
        response = client.distract(desc)
        if response.get("status") == "ok":
            msg = f"Distraction logged: {desc}" if desc else "Distraction logged."
            cfg = load_config()
            extend = cfg.get("distraction_extend_minutes", 0)
            if extend and extend > 0:
                msg += f" Timer extended by {extend}m."
            console.print(f"[bold yellow]{msg}[/bold yellow]")
        else:
            console.print(f"[bold red]Error: {response.get('message')}[/bold red]")
    elif cmd == "report":
        period = questionary.select(
            "Report period:", choices=["today", "week", "all"]
        ).ask()
        if period is None:
            raise typer.Abort()
        generate_report(period)
    elif cmd == "config":
        config_cmd()
    elif cmd == "init":
        init_cmd()
    elif cmd == "pause":
        _pause_cmd_impl()
    elif cmd == "resume":
        _resume_cmd_impl()
    elif cmd == "stop":
        _stop_cmd_impl()
    elif cmd == "kill":
        kill()
    elif cmd == "status":
        _status_cmd_impl()
    elif cmd == "dash":
        run_dashboard()


# ---------------------------------------------------------------------------
# Typer app callback — bare `pomo` launches interactive picker
# ---------------------------------------------------------------------------

def _version_callback(value: bool):
    if value:
        console.print(f"pomocli {__build__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit"),
):
    if ctx.invoked_subcommand is None:
        interactive_mode()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command(name="init")
def init_cmd():
    """Initialize the database and configuration."""
    if DB_PATH.exists():
        if _is_interactive():
            confirmed = typer.confirm(
                "Database already exists. Recreate fresh? (data will be lost)",
                default=False,
            )
            if not confirmed:
                console.print("[bold yellow]Skipped — existing database kept.[/bold yellow]")
                return
        else:
            console.print(
                "[bold red]Database already exists. Run interactively to confirm recreation.[/bold red]"
            )
            raise typer.Exit(1)
        DB_PATH.unlink()

    init_db()
    console.print("[bold green]Database initialized successfully.[/bold green]")


@app.command()
def daemon():
    """Start the background daemon (usually run automatically)."""
    from ..daemon.server import DaemonServer

    server = DaemonServer()
    server.start()


def ensure_daemon():
    """Ensure the daemon is running, starting it if needed."""
    if is_daemon_running():
        resp = client.ping()
        if resp.get("status") == "ok":
            _launch_timer_app()
            return

    subprocess.Popen(
        [sys.executable, "-m", "pomocli.daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(6):
        time.sleep(0.5)
        if is_daemon_running():
            resp = client.ping()
            if resp.get("status") == "ok":
                _launch_timer_app()
                return

    console.print(
        "[bold yellow]Warning: Daemon may not have started. Try 'pomo daemon' manually.[/bold yellow]"
    )


def _launch_timer_app():
    """Launch the PomoCLI Timer macOS status bar app if installed."""
    if sys.platform != "darwin":
        return
    from pathlib import Path

    timer_app_paths = [
        Path.home() / "Applications" / "PomoCLI Timer.app",
        Path("/Applications/PomoCLI Timer.app"),
    ]
    for p in timer_app_paths:
        if p.exists():
            subprocess.Popen(
                ["open", "-g", str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return


@app.command()
def start(
    task: Optional[str] = typer.Argument(
        None, help="Name of the task", autocompletion=complete_tasks
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project name"
    ),
    duration: int = typer.Option(25, "--duration", "-d", help="Duration in minutes"),
    estimate: Optional[int] = typer.Option(
        None, "--estimate", "-e", help="Estimated minutes"
    ),
    last: bool = typer.Option(False, "--last", "-l", help="Resume last task"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tags for this session"),
):
    """Start a new pomodoro session."""
    _start_cmd_impl(task, project, duration, estimate, last, tag)

@app.command(name="ss", hidden=True)
def start_shorthand(
    task: Optional[str] = typer.Argument(
        None, help="Name of the task", autocompletion=complete_tasks
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project name"
    ),
    duration: int = typer.Option(25, "--duration", "-d", help="Duration in minutes"),
    estimate: Optional[int] = typer.Option(
        None, "--estimate", "-e", help="Estimated minutes"
    ),
    last: bool = typer.Option(False, "--last", "-l", help="Resume last task"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tags for this session"),
):
    """Start a new pomodoro session (shorthand)."""
    _start_cmd_impl(task, project, duration, estimate, last, tag)

def _start_cmd_impl(task, project, duration, estimate, last, tag):
    init_db()

    # Handle --last flag
    if last:
        recent = get_recent_tasks(limit=1)
        if not recent:
            console.print("[bold red]No previous tasks found.[/bold red]")
            raise typer.Exit(1)
        last_task = recent[0]
        task = last_task["task_name"]
        project = project or last_task["project_name"]
    elif not task:
        # No task provided and no --last — launch interactive prompt
        if _is_interactive():
            _interactive_start()
            return
        else:
            console.print("[bold red]Please provide a task name or use --last.[/bold red]")
            raise typer.Exit(1)

    _start_session(task, project, duration, estimate, tag)


@app.command()
def pause():
    """Pause the current session."""
    _pause_cmd_impl()

@app.command(name="pp", hidden=True)
def pause_shorthand():
    _pause_cmd_impl()

def _pause_cmd_impl():
    response = client.pause()
    if response.get("status") == "ok":
        console.print("[bold yellow]Session paused.[/bold yellow]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def resume():
    """Resume a paused session."""
    _resume_cmd_impl()

@app.command(name="rr", hidden=True)
def resume_shorthand():
    _resume_cmd_impl()

def _resume_cmd_impl():
    response = client.resume()
    if response.get("status") == "ok":
        console.print("[bold green]Session resumed.[/bold green]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def stop():
    """Stop and save the current session."""
    _stop_cmd_impl()

@app.command(name="sp", hidden=True)
def stop_shorthand():
    _stop_cmd_impl()

def _stop_cmd_impl():
    response = client.stop()
    if response.get("status") == "ok":
        console.print("[bold green]Session stopped and saved.[/bold green]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def kill():
    """Abort the current session without saving as completed."""
    response = client.kill()
    if response.get("status") == "ok":
        console.print("[bold red]Session killed.[/bold red]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def distract(
    description: Optional[str] = typer.Argument(
        None, help="Short description of the distraction"
    ),
):
    """Log a distraction during the current session."""
    _distract_cmd_impl(description)

@app.command(name="dd", hidden=True)
def distract_shorthand(
    description: Optional[str] = typer.Argument(
        None, help="Short description of the distraction"
    ),
):
    _distract_cmd_impl(description)

def _distract_cmd_impl(description):
    response = client.distract(description)
    if response.get("status") == "ok":
        msg = "Distraction logged."
        if description:
            msg = f"Distraction logged: {description}"
        cfg = load_config()
        extend = cfg.get("distraction_extend_minutes", 0)
        if extend and extend > 0:
            msg += f" Timer extended by {extend}m."
        console.print(f"[bold yellow]{msg}[/bold yellow]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def status():
    """Show current timer status."""
    _status_cmd_impl()

@app.command(name="stt", hidden=True)
def status_shorthand():
    _status_cmd_impl()

def _status_cmd_impl():
    response = client.status()
    if response.get("status") == "ok":
        data = response.get("data", {})
        state = data.get("state")
        if state == "stopped":
            console.print("Pomodoro status: [bold]Not running[/bold]")
        else:
            time_left = data.get("time_left", 0)
            mins, secs = divmod(time_left, 60)
            color = "green" if state == "running" else "yellow"
            console.print(
                f"Pomodoro status: [bold {color}]{state.capitalize()}[/bold {color}] - {mins:02d}:{secs:02d} left"
            )
    else:
        console.print("Pomodoro status: [bold]Not running (Daemon down)[/bold]")


from ..ui.reports import generate_report
from ..ui.dashboard import run_dashboard
from ..ui.logo import print_logo


@app.command()
def logo():
    """Print the Pomodoro logo."""
    print_logo()


@app.command()
def dash():
    """Open the live TUI dashboard."""
    run_dashboard()


@app.command()
def report(
    period: str = typer.Argument(
        "today", help="Period to report on (today, week, all)"
    ),
):
    """Show a summary report of logged time."""
    generate_report(period)


@app.command(name="config")
def config_cmd():
    """Interactively configure pomocli settings."""
    import questionary

    if not _is_interactive():
        console.print("[bold red]Config requires an interactive terminal.[/bold red]")
        raise typer.Exit(1)

    cfg = load_config()

    numeric_keys = [
        ("session_duration", "Session duration (minutes)"),
        ("break_duration", "Break duration (minutes)"),
        ("idle_timeout", "Idle timeout (seconds)"),
        ("history_retention_days", "History retention (days)"),
        ("distraction_extend_minutes", "Distraction timer extension (minutes, 0 to disable)"),
    ]

    for key, label in numeric_keys:
        val = questionary.text(
            f"{label}:", default=str(cfg.get(key, DEFAULT_CONFIG[key]))
        ).ask()
        if val is None:
            raise typer.Abort()
        try:
            cfg[key] = int(val)
        except ValueError:
            cfg[key] = DEFAULT_CONFIG[key]

    sound = questionary.confirm(
        "Enable sound notifications?", default=cfg.get("sound_enabled", True)
    ).ask()
    if sound is None:
        raise typer.Abort()
    cfg["sound_enabled"] = sound

    hotkey = questionary.text(
        "Distraction hotkey (e.g. cmd+shift+d):",
        default=cfg.get("hotkey_distraction", DEFAULT_CONFIG["hotkey_distraction"]),
    ).ask()
    if hotkey is None:
        raise typer.Abort()
    cfg["hotkey_distraction"] = hotkey

    # Summary table
    table = Table(title="Configuration Summary")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    for key, label in numeric_keys:
        table.add_row(label, str(cfg[key]))
    table.add_row("Sound enabled", str(cfg["sound_enabled"]))
    table.add_row("Distraction hotkey", cfg["hotkey_distraction"])
    console.print(table)

    save = questionary.confirm("Save this configuration?", default=True).ask()
    if save:
        save_config(cfg)
        console.print("[bold green]Configuration saved.[/bold green]")
    else:
        console.print("[bold yellow]Configuration not saved.[/bold yellow]")


if __name__ == "__main__":
    app()
