import typer
from rich.console import Console
from rich.table import Table
from typing import Optional, List
import subprocess
import sys
import os
import time
from functools import lru_cache

from ..daemon.client import DaemonClient, is_daemon_running
from ..db.operations import (
    get_or_create_task,
    create_session,
    get_recent_tasks,
    get_recent_projects,
    get_recent_tag_names,
    log_distraction,
    add_tags,
    task_name_exists,
    project_name_exists,
    get_sessions_in_range,
    resolve_session_identifier,
    get_session_by_id,
    format_session_public_id,
    edit_session,
    cancel_session,
    delete_session_cascade,
)
from ..db.connection import init_db, DB_PATH
from ..db.backup import run_db_backup, resolve_backup_dir
from ..config import load_config, save_config, DEFAULT_CONFIG
from ..utils.git import get_git_context
from ..time_util import report_time_bounds, get_display_tz, format_local, format_duration_hm
from .. import __build__

from typer.core import TyperGroup
import click
import typer.rich_utils as ru
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

COMMAND_SHORTHANDS = {
    "start": "ss",
    "pause": "pp",
    "resume": "rr",
    "stop": "sp",
    "distract": "dd",
    "status": "stt",
    "extend": "ee",
    "session": "ssn",
}

class CustomHelpGroup(TyperGroup):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        original_print_commands_panel = ru._print_commands_panel
        
        def custom_print_commands_panel(*, name, commands, markup_mode, console, cmd_len):
            t_styles = {
                "show_lines": ru.STYLE_COMMANDS_TABLE_SHOW_LINES,
                "leading": ru.STYLE_COMMANDS_TABLE_LEADING,
                "box": getattr(ru.box, ru.STYLE_COMMANDS_TABLE_BOX, None),
                "border_style": ru.STYLE_COMMANDS_TABLE_BORDER_STYLE,
                "row_styles": ru.STYLE_COMMANDS_TABLE_ROW_STYLES,
                "pad_edge": ru.STYLE_COMMANDS_TABLE_PAD_EDGE,
                "padding": ru.STYLE_COMMANDS_TABLE_PADDING,
            }

            commands_table = Table(
                highlight=False,
                show_header=True,
                expand=True,
                box=t_styles["box"],
                show_lines=t_styles["show_lines"],
                leading=t_styles["leading"],
                border_style=t_styles["border_style"],
                row_styles=t_styles["row_styles"],
                pad_edge=t_styles["pad_edge"],
                padding=t_styles["padding"],
            )
            
            commands_table.add_column(
                "Command",
                style=ru.STYLE_COMMANDS_TABLE_FIRST_COLUMN,
                no_wrap=True,
                width=max(cmd_len, 7),
            )
            commands_table.add_column(
                "Shorthand",
                style="green",
                no_wrap=True,
                width=9,
            )
            commands_table.add_column("Description", justify="left", no_wrap=False, ratio=10)
            
            for command in commands:
                helptext = command.short_help or command.help or ""
                command_name = command.name or ""
                shorthand = COMMAND_SHORTHANDS.get(command_name, "")
                
                command_name_text = Text(command_name)
                if command.deprecated:
                    command_name_text.stylize(ru.STYLE_DEPRECATED_COMMAND)
                    
                commands_table.add_row(
                    command_name_text,
                    Text(shorthand),
                    ru._make_command_help(
                        help_text=helptext,
                        markup_mode=markup_mode,
                    )
                )
                
            if commands_table.row_count:
                console.print(
                    Panel(
                        commands_table,
                        border_style=ru.STYLE_COMMANDS_PANEL_BORDER,
                        title=name,
                        title_align=ru.ALIGN_COMMANDS_PANEL,
                    )
                )
                
        ru._print_commands_panel = custom_print_commands_panel
        try:
            super().format_help(ctx, formatter)
        finally:
            ru._print_commands_panel = original_print_commands_panel

app = typer.Typer(
    name="pomo",
    help="A lightweight, feature-rich CLI Pomodoro timer (countdown and stopwatch / elapsed sessions).",
    add_completion=True,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=CustomHelpGroup,
)
session_app = typer.Typer(help="Manage past sessions.")
app.add_typer(session_app, name="session")
app.add_typer(session_app, name="ssn", hidden=True)
console = Console()
client = DaemonClient()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


@lru_cache(maxsize=1)
def _cached_task_names(cache_bucket: int) -> tuple[str, ...]:
    # Cache task names briefly to keep completion responsive while typing.
    tasks = get_recent_tasks(limit=200)
    names = _dedupe_preserve_order([t["task_name"] for t in tasks if t["task_name"]])
    return tuple(names)


def complete_tasks(incomplete: str):
    # Bucket by 10s to avoid hitting sqlite on every completion invocation.
    names = _cached_task_names(int(time.time() // 10))
    needle = incomplete.casefold()
    for name in names:
        if needle in name.casefold():
            yield name


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------

def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _interactive_start() -> None:
    """Prompt the user to pick a task, project, duration, and tags, then start."""
    import questionary

    try:
        init_db()
        cfg = load_config()
        days = cfg.get("history_retention_days")

        # --- task selection ---
        timezone_config = cfg.get("timezone", "auto")
        recent = get_recent_tasks(limit=30, days=days, timezone_config=timezone_config)
        task_names = _dedupe_preserve_order([t["task_name"] for t in recent if t["task_name"]])

        if task_names:
            choices = ["New task"] + task_names
            answer = questionary.autocomplete("Select a task:", choices=choices).ask()
            if answer is None:
                raise typer.Abort()
            if answer == "New task":
                task = questionary.text("Task name:").ask()
                if task is None:
                    raise typer.Abort()
                task = task.strip()
                while task and task_name_exists(task):
                    reuse = questionary.confirm(
                        f"Task '{task}' already exists. Reuse existing task?",
                        default=True,
                    ).ask()
                    if reuse is None:
                        raise typer.Abort()
                    if reuse:
                        break
                    task = questionary.text("Task name (new):").ask()
                    if task is None:
                        raise typer.Abort()
                    task = task.strip()
            else:
                task = answer
        else:
            task = questionary.text("Task name:").ask()
            if task is None:
                raise typer.Abort()
            task = task.strip()
            while task and task_name_exists(task):
                reuse = questionary.confirm(
                    f"Task '{task}' already exists. Reuse existing task?",
                    default=True,
                ).ask()
                if reuse is None:
                    raise typer.Abort()
                if reuse:
                    break
                task = questionary.text("Task name (new):").ask()
                if task is None:
                    raise typer.Abort()
                task = task.strip()

        if not task:
            raise typer.Abort()

        # --- session type (countdown vs stopwatch) ---
        session_kind = questionary.select(
            "Session type:",
            choices=[
                "Pomodoro (countdown)",
                "Stopwatch (elapsed time)",
            ],
        ).ask()
        if session_kind is None:
            raise typer.Abort()
        elapsed = session_kind == "Stopwatch (elapsed time)"

        # --- project selection ---
        recent_projects = _dedupe_preserve_order(
            get_recent_projects(limit=30, days=days, timezone_config=timezone_config)
        )
        if recent_projects:
            proj_choices = ["No project", "New project"] + recent_projects
            proj_answer = questionary.autocomplete("Select a project:", choices=proj_choices).ask()
            if proj_answer is None:
                raise typer.Abort()
            if proj_answer == "New project":
                project = questionary.text("Project name:").ask()
                if project is None:
                    raise typer.Abort()
                project = project.strip() or None
                while project and project_name_exists(project):
                    reuse = questionary.confirm(
                        f"Project '{project}' already exists. Reuse existing project?",
                        default=True,
                    ).ask()
                    if reuse is None:
                        raise typer.Abort()
                    if reuse:
                        break
                    project = questionary.text("Project name (new):").ask()
                    if project is None:
                        raise typer.Abort()
                    project = project.strip() or None
            elif proj_answer == "No project":
                project = None
            else:
                project = proj_answer
        else:
            project = questionary.text("Project name (leave blank for none):").ask()
            if project is None:
                raise typer.Abort()
            project = project.strip() or None
            while project and project_name_exists(project):
                reuse = questionary.confirm(
                    f"Project '{project}' already exists. Reuse existing project?",
                    default=True,
                ).ask()
                if reuse is None:
                    raise typer.Abort()
                if reuse:
                    break
                project = questionary.text("Project name (new):").ask()
                if project is None:
                    raise typer.Abort()
                project = project.strip() or None

        # --- duration (countdown only) ---
        if elapsed:
            duration = 0
        else:
            default_dur = str(cfg.get("session_duration", 25))
            dur_str = questionary.text("Duration (minutes):", default=default_dur).ask()
            try:
                duration = int(dur_str)
            except (TypeError, ValueError):
                duration = int(default_dur)

        # --- tags ---
        recent_tags = _dedupe_preserve_order(get_recent_tag_names(limit=30))
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

        _start_session(task, project, duration, estimate=None, tags=tags, elapsed=elapsed)
    except KeyboardInterrupt:
        console.print("[bold yellow]Cancelled.[/bold yellow]")
        raise typer.Exit()


def _start_session(
    task: str,
    project: str | None,
    duration: int,
    estimate: int | None,
    tags: list[str] | None,
    *,
    elapsed: bool = False,
    git_repo: str | None = None,
    git_branch: str | None = None,
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
    if git_repo is not None:
        repo_name = git_repo
    if git_branch is not None:
        branch_name = git_branch
    timer_mode = "elapsed" if elapsed else "countdown"
    session_id = create_session(
        task_id, repo_name, branch_name, timer_mode=timer_mode
    )

    if tags:
        add_tags(session_id, tags)

    response = client.start(
        duration,
        session_id,
        timer_mode=timer_mode,
    )
    if response.get("status") == "ok":
        if elapsed:
            parts = [
                f"[bold green]Started stopwatch session for '{task}'[/bold green]"
            ]
        else:
            parts = [
                f"[bold green]Started session for '{task}' ({duration}m)[/bold green]"
            ]
        if project:
            parts.append(f"  Project: {project}")
        if repo_name:
            if branch_name:
                parts.append(f"  Git: {repo_name}/{branch_name}")
            else:
                parts.append(f"  Git: {repo_name}")
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
        "Extend session": "extend",
        # --- Info ---
        "Show status": "status",
        "List today's sessions": "list",
        "View report": "report",
        "Open dashboard": "dash",
        # --- Settings ---
        "Configure settings": "config",
        "Initialize database": "init",
    }

    try:
        answer = questionary.autocomplete(
            "What would you like to do?",
            choices=list(commands.keys()),
        ).ask()
    except KeyboardInterrupt:
        console.print("[bold yellow]Cancelled.[/bold yellow]")
        raise typer.Exit()
    if answer is None:
        console.print("[bold yellow]Cancelled.[/bold yellow]")
        raise typer.Exit()

    cmd = commands[answer]

    if cmd == "start":
        _interactive_start()
    elif cmd == "distract":
        desc = questionary.text("Distraction description (optional):").ask()
        _distract_cmd_impl(desc)
    elif cmd == "report":
        period = questionary.select(
            "Report period:", choices=["today", "week", "month", "quarter", "all"]
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
        _stop_cmd_impl(skip_confirm=True)
    elif cmd == "kill":
        kill()
    elif cmd == "extend":
        _extend_cmd_impl()
    elif cmd == "status":
        _status_cmd_impl()
    elif cmd == "list":
        list_cmd()
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
    duration: int = typer.Option(25, "--duration", "-d", help="Duration in minutes (countdown only; ignored with --elapsed)"),
    estimate: Optional[int] = typer.Option(
        None, "--estimate", "-e", help="Estimated minutes"
    ),
    last: bool = typer.Option(False, "--last", "-l", help="Resume last task"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tags for this session"),
    elapsed: bool = typer.Option(
        False,
        "--elapsed",
        help="Stopwatch mode: counts up, no session extension on distraction",
    ),
    git_repo: Optional[str] = typer.Option(
        None, "--repo", help="Override git repo name stored on the session",
    ),
    git_branch: Optional[str] = typer.Option(
        None, "--branch", help="Override git branch stored on the session",
    ),
):
    """Start a new pomodoro session."""
    _start_cmd_impl(task, project, duration, estimate, last, tag, elapsed, git_repo, git_branch)

@app.command(name="ss", hidden=True)
def start_shorthand(
    task: Optional[str] = typer.Argument(
        None, help="Name of the task", autocompletion=complete_tasks
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project name"
    ),
    duration: int = typer.Option(25, "--duration", "-d", help="Duration in minutes (countdown only; ignored with --elapsed)"),
    estimate: Optional[int] = typer.Option(
        None, "--estimate", "-e", help="Estimated minutes"
    ),
    last: bool = typer.Option(False, "--last", "-l", help="Resume last task"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tags for this session"),
    elapsed: bool = typer.Option(
        False,
        "--elapsed",
        help="Stopwatch mode: counts up, no session extension on distraction",
    ),
    git_repo: Optional[str] = typer.Option(
        None, "--repo", help="Override git repo name stored on the session",
    ),
    git_branch: Optional[str] = typer.Option(
        None, "--branch", help="Override git branch stored on the session",
    ),
):
    """Shorthand for start."""
    _start_cmd_impl(task, project, duration, estimate, last, tag, elapsed, git_repo, git_branch)

def _start_cmd_impl(task, project, duration, estimate, last, tag, elapsed, git_repo, git_branch):
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

    _start_session(
        task,
        project,
        duration,
        estimate,
        tag,
        elapsed=elapsed,
        git_repo=git_repo,
        git_branch=git_branch,
    )


@app.command()
def pause():
    """Pause the current session."""
    _pause_cmd_impl()

@app.command(name="pp", hidden=True)
def pause_shorthand():
    """Shorthand for pause."""
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
    """Shorthand for resume."""
    _resume_cmd_impl()

def _resume_cmd_impl():
    response = client.resume()
    if response.get("status") == "ok":
        console.print("[bold green]Session resumed.[/bold green]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def stop(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Stop and save the current session."""
    _stop_cmd_impl(yes)

@app.command(name="sp", hidden=True)
def stop_shorthand(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Shorthand for stop."""
    _stop_cmd_impl(yes)

def _stop_cmd_impl(skip_confirm: bool = False):
    if not skip_confirm and _is_interactive():
        confirmed = typer.confirm("Stop the current session?", default=False)
        if not confirmed:
            console.print("[bold yellow]Session not stopped.[/bold yellow]")
            raise typer.Exit()

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
    """Shorthand for distract."""
    _distract_cmd_impl(description)

def _distract_cmd_impl(description):
    response = client.distract(description)
    if response.get("status") == "ok":
        msg = "Distraction logged."
        if description:
            msg = f"Distraction logged: {description}"
        st = client.status()
        mode = (st.get("data") or {}).get("timer_mode", "countdown")
        cfg = load_config()
        extend = cfg.get("distraction_extend_minutes", 0)
        if mode != "elapsed" and extend and extend > 0:
            msg += f" Timer extended by {extend}m."
        console.print(f"[bold yellow]{msg}[/bold yellow]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def extend():
    """Extend the current session duration."""
    _extend_cmd_impl()

@app.command(name="ee", hidden=True)
def extend_shorthand():
    """Shorthand for extend."""
    _extend_cmd_impl()

def _extend_cmd_impl():
    response = client.extend()
    if response.get("status") == "ok":
        extended_by = response.get("extended_by", 0)
        console.print(f"[bold green]Session extended by {extended_by}m.[/bold green]")
    else:
        console.print(f"[bold red]Error: {response.get('message')}[/bold red]")


@app.command()
def status():
    """Show current timer status."""
    _status_cmd_impl()

@app.command(name="stt", hidden=True)
def status_shorthand():
    """Shorthand for status."""
    _status_cmd_impl()

def _status_cmd_impl():
    response = client.status()
    if response.get("status") == "ok":
        data = response.get("data", {})
        state = data.get("state")
        if state == "stopped":
            console.print("Pomodoro status: [bold]Not running[/bold]")
        else:
            mode = data.get("timer_mode", "countdown")
            color = "green" if state == "running" else "yellow"
            if mode == "elapsed":
                elapsed = int(data.get("elapsed_seconds", 0))
                mins, secs = divmod(elapsed, 60)
                console.print(
                    f"Pomodoro status: [bold {color}]{state.capitalize()}[/bold {color}] - "
                    f"{mins:02d}:{secs:02d} elapsed (stopwatch)"
                )
            else:
                time_left = data.get("time_left", 0)
                mins, secs = divmod(time_left, 60)
                console.print(
                    f"Pomodoro status: [bold {color}]{state.capitalize()}[/bold {color}] - "
                    f"{mins:02d}:{secs:02d} left"
                )
    else:
        console.print("Pomodoro status: [bold]Not running (Daemon down)[/bold]")


SESSION_STATUS_VALUES = {"running", "paused", "completed", "stopped", "killed"}


def _resolve_session_pk_or_exit(identifier: str) -> int:
    resolved = resolve_session_identifier(identifier)
    if resolved is None:
        console.print(f"[bold red]Session '{identifier}' was not found.[/bold red]")
        raise typer.Exit(1)
    return resolved


@session_app.command("edit")
def session_edit_cmd(
    identifier: str = typer.Argument(..., help="Session short ID or numeric PK"),
    status: Optional[str] = typer.Option(None, "--status", help="New status value"),
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d", help="Duration logged in minutes"
    ),
):
    """Edit a past session."""
    if status is None and duration is None:
        console.print(
            "[bold red]Provide at least one field: --status and/or --duration.[/bold red]"
        )
        raise typer.Exit(1)
    if status is not None and status not in SESSION_STATUS_VALUES:
        allowed = ", ".join(sorted(SESSION_STATUS_VALUES))
        console.print(f"[bold red]Invalid status '{status}'. Use one of: {allowed}[/bold red]")
        raise typer.Exit(1)
    if duration is not None and duration < 0:
        console.print("[bold red]Duration must be >= 0 minutes.[/bold red]")
        raise typer.Exit(1)

    session_pk = _resolve_session_pk_or_exit(identifier)
    changed = edit_session(
        session_pk,
        status=status,
        duration_logged_seconds=(duration * 60) if duration is not None else None,
    )
    if not changed:
        console.print("[bold red]No session was updated.[/bold red]")
        raise typer.Exit(1)

    session_row = get_session_by_id(session_pk)
    display_id = (
        format_session_public_id(session_pk, session_row["start_time"])
        if session_row
        else identifier
    )
    console.print(f"[bold green]Updated session {display_id}.[/bold green]")


@session_app.command("cancel")
def session_cancel_cmd(
    identifier: str = typer.Argument(..., help="Session short ID or numeric PK"),
):
    """Cancel (kill) a past session."""
    session_pk = _resolve_session_pk_or_exit(identifier)
    changed = cancel_session(session_pk)
    if not changed:
        console.print("[bold red]No session was cancelled.[/bold red]")
        raise typer.Exit(1)

    session_row = get_session_by_id(session_pk)
    display_id = (
        format_session_public_id(session_pk, session_row["start_time"])
        if session_row
        else identifier
    )
    console.print(f"[bold yellow]Cancelled session {display_id}.[/bold yellow]")


@session_app.command("delete")
def session_delete_cmd(
    identifier: str = typer.Argument(..., help="Session short ID or numeric PK"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Delete a past session and related records."""
    session_pk = _resolve_session_pk_or_exit(identifier)
    session_row = get_session_by_id(session_pk)
    display_id = (
        format_session_public_id(session_pk, session_row["start_time"])
        if session_row
        else identifier
    )

    if not yes and _is_interactive():
        confirmed = typer.confirm(f"Delete session {display_id}?", default=False)
        if not confirmed:
            console.print("[bold yellow]Deletion cancelled.[/bold yellow]")
            raise typer.Exit()

    deleted = delete_session_cascade(session_pk)
    if not deleted:
        console.print("[bold red]No session was deleted.[/bold red]")
        raise typer.Exit(1)
    console.print(f"[bold green]Deleted session {display_id}.[/bold green]")


from ..ui.reports import generate_report
from ..ui.dashboard import run_dashboard
from ..ui.logo import print_logo


@app.command()
def logo():
    """Print the Pomodoro logo."""
    print_logo()


@app.command()
def dash(
    detail: str = typer.Option("normal", "--detail", help="Detail level: minimal, normal, full")
):
    """Open the live TUI dashboard."""
    run_dashboard(detail)


@app.command()
def report(
    period: str = typer.Argument(
        "today", help="Period to report on (today, week, month, quarter, all)"
    ),
):
    """Show a summary report of logged time."""
    cfg = load_config()
    generate_report(period, timezone_config=cfg.get("timezone", "auto"))


@session_app.command(name="list")
def list_cmd():
    """List today's sessions with status, focus rate, and notes."""
    cfg = load_config()
    timezone_config = cfg.get("timezone", "auto")
    tz = get_display_tz(timezone_config)
    start_utc, end_utc = report_time_bounds("today", tz)
    if not start_utc or not end_utc:
        console.print("[bold red]Could not resolve time range for today.[/bold red]")
        raise typer.Exit(1)

    rows = get_sessions_in_range(start_utc, end_utc)
    if not rows:
        console.print("No sessions logged today.")
        return

    table = Table(title="Today's Sessions")
    table.add_column("Session", justify="right", style="cyan")
    table.add_column("Start", style="cyan")
    table.add_column("Project", style="magenta")
    table.add_column("Task", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Logged", justify="right", style="yellow")
    table.add_column("Distract", justify="right", style="yellow")
    table.add_column("Notes", style="white")

    completed = 0
    total_logged = 0
    for row in rows:
        logged = int(row["duration_logged"] or 0)
        total_logged += logged
        if row["status"] == "completed":
            completed += 1
        start_local = format_local(row["start_time"], timezone_config)
        notes = row["distraction_notes"] or "-"
        project = row["project_name"] or "-"
        session_display = (
            row["public_id"] if "public_id" in row.keys() and row["public_id"] else str(row["id"])
        )
        table.add_row(
            session_display,
            start_local,
            project,
            row["task_name"] or "-",
            row["status"],
            format_duration_hm(logged),
            str(row["distraction_count"] or 0),
            notes,
        )

    console.print(table)
    focus_rate = (completed / len(rows)) * 100
    console.print(
        f"[bold]Focus rate:[/bold] {focus_rate:.0f}% ({completed}/{len(rows)} completed) | "
        f"[bold]Total logged:[/bold] {format_duration_hm(total_logged)}"
    )


@app.command()
def backup():
    """Create a manual backup of the database."""
    cfg = load_config()
    backup_dir = resolve_backup_dir(cfg)
    max_versions = cfg.get("backup_max_versions", 7)
    compress = cfg.get("backup_compress", True)
    
    try:
        new_file, deleted = run_db_backup(
            db_path=DB_PATH,
            backup_dir=backup_dir,
            max_versions=max_versions,
            compress=compress
        )
        console.print(f"[bold green]Backup created:[/bold green] {new_file}")
        if deleted > 0:
            console.print(f"Rotated {deleted} old backup(s).")
    except Exception as e:
        console.print(f"[bold red]Backup failed:[/bold red] {e}")
        raise typer.Exit(1)


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
        ("backup_interval_days", "Automatic backup interval (days, 0 to disable)"),
        ("backup_max_versions", "Maximum backup versions to keep"),
    ]

    try:
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

        tz = questionary.text(
            "Timezone (e.g. auto, Europe/Berlin):",
            default=cfg.get("timezone", DEFAULT_CONFIG["timezone"]),
        ).ask()
        if tz is None:
            raise typer.Abort()
        cfg["timezone"] = tz

        bdir = questionary.text(
            "Backup directory (leave blank for default):",
            default=cfg.get("backup_dir", DEFAULT_CONFIG["backup_dir"]),
        ).ask()
        if bdir is None:
            raise typer.Abort()
        cfg["backup_dir"] = bdir

        bcomp = questionary.confirm(
            "Compress backups (gzip)?", default=cfg.get("backup_compress", True)
        ).ask()
        if bcomp is None:
            raise typer.Abort()
        cfg["backup_compress"] = bcomp
    except KeyboardInterrupt:
        console.print("[bold yellow]Cancelled.[/bold yellow]")
        raise typer.Exit()

    # Summary table
    table = Table(title="Configuration Summary")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    for key, label in numeric_keys:
        table.add_row(label, str(cfg[key]))
    table.add_row("Sound enabled", str(cfg["sound_enabled"]))
    table.add_row("Distraction hotkey", cfg["hotkey_distraction"])
    table.add_row("Timezone", cfg["timezone"])
    table.add_row("Backup directory", cfg["backup_dir"] or "(default)")
    table.add_row("Compress backups", str(cfg["backup_compress"]))
    console.print(table)

    save = questionary.confirm("Save this configuration?", default=True).ask()
    if save:
        save_config(cfg)
        console.print("[bold green]Configuration saved.[/bold green]")
    else:
        console.print("[bold yellow]Configuration not saved.[/bold yellow]")


if __name__ == "__main__":
    app()
