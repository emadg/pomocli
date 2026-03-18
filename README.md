# pomocli

A lightweight, feature-rich CLI Pomodoro timer with git awareness, distraction tracking, and a live TUI dashboard.

## Installation

Requires Python 3.10+.

```bash
# Clone and install with uv
git clone <repo-url> && cd pomocli
uv tool install .

# Or install in development mode
uv sync
```

## Quick Start

```bash
# 1. Initialize the database (first time only)
pomo init

# 2. Start a 25-minute session
pomo start "Write README" -p my-project

# 3. Check on your timer
pomo status

# 4. Done early? Stop and save
pomo stop
```

That's it — the background daemon starts automatically when you run `pomo start`. No need to launch it separately.

### Interactive Mode

Run `pomo` with no arguments to get an interactive command picker:

```bash
pomo
```

Use arrow keys to select any command — start a session, check status, open the dashboard, change settings, etc.

Running `pomo start` without a task name also drops into interactive mode, where you can pick from recent tasks and projects.

### Tips

- **You don't need to run the daemon manually.** `pomo start` spawns it in the background automatically.
- **Resume your last task** with `pomo start --last` (or `pomo start -l`).
- **Tag sessions** with `pomo start "Task" -t focus -t deep-work` for filtering in reports.
- **Log distractions** mid-session with `pomo distract` (description is optional). Each distraction automatically extends the timer by the configured amount (default: 2 minutes).
- **Git context is captured automatically** — the current repo and branch are recorded with each session.
- **Customize defaults** with `pomo config` (session duration, break time, sound, etc.). Settings are stored in `~/.config/pomocli/config.toml`.

## Commands

| Command | Description |
|---------|-------------|
| `pomo` | Interactive command picker |
| `pomo start [TASK]` | Start a pomodoro session |
| `pomo pause` | Pause the current session |
| `pomo resume` | Resume a paused session |
| `pomo stop` | Stop and save the current session |
| `pomo kill` | Abort session without saving as completed |
| `pomo distract [DESC]` | Log a distraction |
| `pomo status` | Show current timer status |
| `pomo report [PERIOD]` | Summary report (`today`, `week`, or `all`) |
| `pomo dash` | Open the live TUI dashboard |
| `pomo config` | Interactively configure settings |
| `pomo init` | Initialize (or reinitialize) the database |

### `pomo start` Options

```
pomo start "Task name" [OPTIONS]

Options:
  -p, --project TEXT      Project name
  -d, --duration INTEGER  Duration in minutes (default: 25)
  -e, --estimate INTEGER  Estimated total minutes for the task
  -l, --last              Resume the last task
  -t, --tag TEXT          Tags (repeatable)
```

## Configuration

Run `pomo config` to set preferences interactively. Config lives at `~/.config/pomocli/config.toml`.

| Setting | Default | Description |
|---------|---------|-------------|
| `session_duration` | 25 | Pomodoro duration in minutes |
| `break_duration` | 5 | Break duration in minutes |
| `idle_timeout` | 300 | Seconds of idle before auto-pause (macOS) |
| `sound_enabled` | true | Play sound notifications |
| `history_retention_days` | 30 | Days of task history shown in interactive prompts |
| `hotkey_distraction` | `cmd+shift+d` | Global hotkey for logging distractions (macOS app) |
| `distraction_extend_minutes` | 2 | Minutes added to timer per distraction (0 to disable) |

## Data Storage

Everything lives under `~/.config/pomocli/`:

- `pomocli.db` — SQLite database (sessions, tasks, distractions, tags)
- `config.toml` — User preferences

## macOS Status Bar App

PomoCLI Timer is a native Swift app that adds a status bar icon with live countdown, a configurable global hotkey for logging distractions, and idle detection — no Python dependencies or Accessibility permissions required.

### Build & Install

Requires Xcode Command Line Tools (`xcode-select --install`).

```bash
cd macos/PomoCLITimer
make install    # builds, bundles, copies to ~/Applications/
```

Once installed, `pomo start` will auto-launch the status bar app. You can also open it manually or add it to Login Items.

### Features

- **Status bar icon** — shows `🍅` when idle, `🍅 MM:SS` countdown when running, `⏸ MM:SS` when paused
- **Menu controls** — Pause/Resume, Stop, Quit
- **Global hotkey** — press Cmd+Shift+D (configurable via `hotkey_distraction` in config) to log a distraction
- **Idle detection** — auto-pauses the timer when you're away (uses Quartz, no Accessibility permissions needed)

### Legacy Python macOS Extras

The optional Python-based macOS integrations (`uv pip install ".[macos]"` with `rumps` and `pynput`) are still available but superseded by the native Swift app above.

## Development

```bash
uv sync
uv run pytest
```
