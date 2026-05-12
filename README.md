# pomocli

A lightweight, feature-rich CLI Pomodoro timer with git awareness, distraction tracking, optional **stopwatch (elapsed)** sessions, and a live TUI dashboard.

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/emadg/pomocli.git && cd pomocli
uv tool install .
```

Or install in development mode:

```bash
uv sync
```

## Quick Start

```bash
# 1. Initialize the database (first time only)
pomo init

# 2. Start a 25-minute session
pomo start "Write README" -p my-project

# Or: stopwatch (elapsed time, no countdown)
pomo start "Deep work" -p my-project --elapsed

# 3. Check on your timer
pomo status

# 4. Done early? Stop and save (countdown or stopwatch)
pomo stop

# Stopwatch only: mark the block finished as "completed" (vs stopped)
pomo complete
```

The background daemon starts automatically when you run `pomo start`; you do not need to launch it separately. To control it explicitly, use **`pomo daemon start`** (detached), **`pomo daemon start --attach`** (foreground, logs in the terminal), **`pomo daemon stop`**, or **`pomo daemon restart`**. Each of those prints the **resolved SQLite database path** for the current environment (`POMOCLI_DB_PATH` or default). Bare **`pomo daemon`** reports a missing command; use **`pomo daemon -h`** for help.

### Interactive mode

Run `pomo` with no arguments for the interactive command picker (arrow keys, fuzzy search).

Running `pomo start` without a task name opens interactive start: pick from recent tasks and projects, choose **Pomodoro (countdown)** or **Stopwatch (elapsed)**, then duration (countdown only) and tags.

### Session modes

| Mode | Command | Timer | Distractions | `pomo extend` |
|------|---------|-------|----------------|---------------|
| **Pomodoro (default)** | `pomo start "Task"` | Counts down from `--duration` (default 25m); ends with `complete` at zero | May add time if `distraction_extend_minutes` > 0 | Adds configured minutes |
| **Stopwatch (elapsed)** | `pomo start "Task" --elapsed` | Counts **up** while running; no target time | Logged only; timer does **not** extend | Not available (error) |

Stopwatch sessions still support pause, resume, idle auto-pause, and `stop` / `kill` to end the session. Use **`pomo complete`** (or `pomo cm`) to end a stopwatch with **`completed`** status and the completion sound—like a natural Pomodoro finish—whereas **`pomo stop`** saves as **`stopped`**. Logged duration is the elapsed running time (paused time excluded), same wall-clock idea as the countdown timer.

### Tips

- **Daemon:** `pomo start` starts the daemon if needed; use **`pomo daemon start|stop|restart`** when you want to manage it yourself (see above).
- **Last task:** `pomo start --last` (or `-l`) resumes the most recently used task.
- **Tags:** `pomo start "Task" -t focus -t deep-work` attaches tags to the session (stored for each session; useful for your own records and interactive tag hints).
- **Distractions:** `pomo distract` with an optional description. On **countdown** sessions, each distraction can extend the timer by `distraction_extend_minutes` (default: 2). On **elapsed** sessions, distractions are recorded only; the clock does not change.
- **Lifecycle events:** Session events (`start`, `pause`, `resume`, `extend`, `stop`, `kill`, `idle`, `complete`) are logged for later analysis. Countdown sessions emit `complete` when the timer reaches zero. Elapsed sessions do not auto-complete; use **`pomo complete`** (daemon `complete` command) to log `complete` and set status `completed`. Elapsed sessions do not emit `extend` from distractions.
- **Git:** Current repo and branch are saved with each session when you are inside a git working tree. Override with `--repo` and/or `--branch` on `pomo start` (e.g. when the session is not tied to your cwd).
- **Config:** `pomo config` edits defaults; settings live in `~/.config/pomocli/config.toml`.
- **Interactive cancel:** Use `Ctrl-C` to cleanly exit interactive picker/start/config flows.
- **Reports:** `pomo report today` (or `week`, `month`, `quarter`, `all`) uses your configured **timezone** for “today” and calendar periods (see [Configuration](#configuration)). Session detail footers label **Focus Block Success (FBS)** and **Attention Quality (ATQ)** (definitions: ≥25m qualifying sessions / pauses / distractions for FBS; wall time vs pauses and capped distraction recovery for ATQ). On multi-day ranges, the **Daily Trend** block lists each local **start** calendar day with logged duration, fixed-width **FBS** and **ATQ** (green vs red compared to the previous listed day), then an ASCII bar scaled to the busiest day. Overnight sessions count only on the day they **started** (local).

## Commands

| Command | Shorthand | Description |
|---------|-----------|-------------|
| `pomo` | | Interactive command picker |
| `pomo start [TASK]` | `ss` | Start a session (countdown Pomodoro or `--elapsed` stopwatch) |
| `pomo pause` | `pp` | Pause the current session |
| `pomo resume` | `rr` | Resume a paused session |
| `pomo stop` | `sp` | Stop and save the current session (`stopped`) |
| `pomo complete` | `cm` | **Stopwatch only:** finish session as `completed` (same idea as countdown reaching zero) |
| `pomo kill` | | Abort session without marking completed |
| `pomo distract [DESC]` | `dd` | Log a distraction |
| `pomo extend` | `ee` | Extend the current session (configured minutes) |
| `pomo status` | `stt` | Show timer status |
| `pomo session list` | `ssn list` | List sessions (default: **today**); add `--days N` / `-d N` (N ≥ 2) for the last **N** local calendar days including today |
| `pomo session <subcommand>` | `ssn <subcommand>` | Manage past sessions (`list`, `edit`, `cancel`, `delete`). You cannot edit, cancel, or delete the **active** timer session until it is stopped or completed. |
| `pomo report [PERIOD]` | | Summary + session detail + focus metrics; multi-day runs add **Daily Trend** (date, logged time, FBS/ATQ columns, bar). Periods: `today`, `week`, `month`, `quarter`, or `all`. Optional `--days N` / `-d N` (N ≥ 2) uses the last **N** local calendar days and **overrides** the period |
| `pomo backup` | | Create a manual database backup |
| `pomo dash` | | Live TUI dashboard (`--detail minimal`, `normal`, or `full`) |
| `pomo logo` | | Print the CLI logo |
| `pomo config` | | Interactive configuration |
| `pomo init` | | Create or reinitialize the database |

Use `-h` or `--help` on any command for options.

### Shell completion

```bash
pomo --show-completion
```

Follow the printed instructions for bash, zsh, fish, or PowerShell.

### `pomo start` options

```
pomo start "Task name" [OPTIONS]

Options:
  -p, --project TEXT      Project name
  -d, --duration INTEGER  Duration in minutes (default: 25; ignored with --elapsed)
  -e, --estimate INTEGER  Estimated total minutes for the task
  -l, --last              Resume the last task
  -t, --tag TEXT          Tags (repeatable)
      --elapsed           Stopwatch mode: elapsed time, no distraction extension
      --repo TEXT         Override git repo name stored on the session
      --branch TEXT       Override git branch stored on the session
```

The same options apply to the `ss` shorthand.

## Configuration

Run `pomo config` interactively, or edit `~/.config/pomocli/config.toml`.

| Setting | Default | Description |
|---------|---------|-------------|
| `session_duration` | 25 | Pomodoro length (minutes) |
| `break_duration` | 5 | Break length (minutes) |
| `idle_timeout` | 300 | Seconds idle before auto-pause (macOS, with status bar app) |
| `sound_enabled` | true | Sound notifications |
| `history_retention_days` | 30 | How far back recent tasks/projects are shown in interactive start |
| `hotkey_distraction` | `cmd+shift+d` | Global distraction hotkey (macOS app) |
| `distraction_note_prompt` | `false` | macOS app only: show a dialog to enter an optional distraction note before logging (Cancel/Esc skips). Unrelated: the app always uses a **2s** bolt flash and **2s** cooldown after each successful hotkey distraction (not configurable). |
| `distraction_extend_minutes` | 2 | Minutes added per distraction (`0` to disable) |
| `timezone` | `auto` | Display and calendar semantics for reports and retention: `auto` uses system local time, or set an IANA name (e.g. `Europe/Berlin`) |
| `backup_interval_days` | 0 | Minimum days between automatic backups (`0` to disable) |
| `backup_max_versions` | 7 | Maximum backup files to keep |
| `backup_dir` | `""` | Directory for backups (empty uses `~/.config/pomocli/backups`) |
| `backup_compress` | true | Gzip backups (`.db.gz`) to save space |

**Time storage:** Session and task timestamps are stored in **UTC** in the database. Reports and “last N days” history use the effective timezone above so “today” and trend buckets match your local calendar.

## Data storage

Everything under `~/.config/pomocli/`:

| Path | Purpose |
|------|---------|
| `pomocli.db` | SQLite: tasks, sessions (`timer_mode`: `countdown` or `elapsed`), tags, distractions |
| `config.toml` | User preferences |
| `backups/` | Default directory for automatic and manual backups |

Override the database location for backups or demos:

```bash
export POMOCLI_DB_PATH=/path/to/custom.db
pomo report week
```

### Database backups

Pomocli can automatically back up your database using the SQLite backup API (ensuring consistency even while the timer runs).

- **Automatic:** Set `backup_interval_days` > 0 in `pomo config`. The daemon will check periodically and create a backup if the interval has passed.
- **Manual:** Run `pomo backup` at any time (or via cron).
- **Compression:** Backups are gzipped by default (`.db.gz`). To restore, just unzip it: `gunzip -c pomocli-YYYYMMDD-HHMMSS.db.gz > restored.db`.
- **Rotation:** Old backups are automatically deleted so only the newest `backup_max_versions` remain.

## macOS status bar app

**PomoCLI Timer** is a small Swift app: menu-bar countdown, global distraction hotkey, and idle detection—without Python or Accessibility permissions for those features.

### Build and install

Requires Xcode Command Line Tools (`xcode-select --install`).

```bash
cd macos/PomoCLITimer
make install    # build, bundle, copy to ~/Applications/
```

After install, `pomo start` can auto-launch the app; you can also open it manually or add it to Login Items.

### Features

- **Menu bar** — idle `🍅`; running countdown `🍅 MM:SS` (time remaining); running stopwatch `🍅 ⏱ MM:SS` (time elapsed); paused `⏸ MM:SS` (remaining or elapsed to match the session mode)
- **Menu** — Pause / Resume, Stop, **Complete session** (stopwatch / elapsed only; hidden for countdown), Quit
- **Global hotkey** — default Cmd+Shift+D (`hotkey_distraction` in config); after each successful log, a **2s** bolt flash and **2s** lockout before another distraction can be logged. Optional **`distraction_note_prompt`** opens a note dialog first (Cancel skips logging).
- **Idle detection** — auto-pause when user is inactive (no mouse/keyboard, Quartz-based); on return, prompts to Resume or Stop
- **Lock & sleep detection** — auto-pause when the Mac sleeps, the lid closes, or the screen locks; on wake/unlock, prompts to Resume or Stop the paused session

Global hotkeys and menu-bar integration are provided by the Swift app only; the Python daemon does not register global hotkeys.

## Development

```bash
uv sync
uv run pytest
```

### Demo / test database

`scripts/seed_test_db.py` fills a database with varied tasks, sessions (**countdown** and **elapsed**), `session_events` (start/pause/resume/complete/stop), tags, distractions—including **curated rows** tagged `demo-metrics` that exercise **focus block** and **attention quality** math—plus git fields. Use it for reports, `pomo session list`, and the dashboard.

**Always set `POMOCLI_DB_PATH`** so you do not overwrite your real database:

```bash
POMOCLI_DB_PATH=./demo.db uv run python scripts/seed_test_db.py
POMOCLI_DB_PATH=./demo.db uv run pomo report week
POMOCLI_DB_PATH=./demo.db uv run pomo dash
```

The script prints a reminder if `POMOCLI_DB_PATH` is unset.


Component diagram for the app:

```mermaid
flowchart TB
  subgraph clients["Clients"]
    CLI["cli/main.py<br/>Typer `pomo`"]
    SwiftApp["macOS PomoCLITimer<br/>(Swift)"]
  end

  subgraph daemon_pkg["pomocli.daemon"]
    PyClient["client.py<br/>DaemonClient"]
    Server["server.py<br/>DaemonServer"]
    Timer["timer.py<br/>PomodoroTimer<br/>(countdown + elapsed)"]
    Idle["macos.py<br/>IdleDetector"]
  end

  subgraph ui_pkg["pomocli.ui"]
    Dash["dashboard.py<br/>(Textual)"]
    Reports["reports.py<br/>(Rich)"]
    Logo["logo.py"]
  end

  subgraph metrics_pkg["pomocli.metrics"]
    FocusM["focus.py<br/>block + attention rates"]
  end

  subgraph data_pkg["pomocli.db"]
    Conn["connection.py + schema.sql"]
    Ops["operations.py"]
    Backup["backup.py"]
  end

  subgraph shared["Shared"]
    Config["config/<br/>config.toml"]
    TimeUtil["time_util.py"]
    Git["utils/git.py"]
  end

  Sock["Unix socket<br/>~/.config/pomocli/pomo.sock"]
  SQLite[("SQLite<br/>pomocli.db")]

  CLI --> PyClient
  CLI --> Ops
  CLI --> Conn
  CLI --> Backup
  CLI --> Config
  CLI --> Git
  CLI --> Reports
  CLI --> Dash
  CLI --> Logo
  CLI --> FocusM

  Dash --> PyClient

  SwiftApp --> Sock

  PyClient <-->|JSON over AF_UNIX| Sock
  Server <-->|listen / handle| Sock
  Server --> Timer
  Server --> Ops
  Server --> Backup
  Server --> Config
  Server --> Idle
  Server -.->|DB path only| Conn

  Ops --> Conn
  Ops --> TimeUtil
  Reports --> Conn
  Reports --> TimeUtil
  Reports --> FocusM
  FocusM --> Ops
  Backup --> SQLite
  Conn --> SQLite

  Timer -.->|session lifecycle callbacks| Server
```
