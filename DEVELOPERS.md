# Developers Guide

## Timer modes (daemon / DB)

- **Countdown (default):** `timer.py` decrements `time_left`; natural end calls `on_complete` and marks the session completed. Logged seconds use `min(duration - time_left, focus_duration)` (also exposed as `logged_focus_seconds()`).
- **Elapsed:** `start_elapsed(session_id)` increments `elapsed_seconds` only while `RUNNING`. Stop/kill persist `elapsed_seconds`. **`complete` socket command** (CLI `pomo complete`, macOS menu) marks the session **`completed`**, logs a `complete` event, plays the completion sound, then stops the timer—mirroring countdown’s natural `on_complete` path. **`stop`** still sets status **`stopped`**. The Unix-socket `start` command passes `timer_mode: "elapsed"`; status JSON always includes `timer_mode` and `elapsed_seconds` for UIs.
- **Schema:** `sessions.timer_mode` defaults to `countdown`. New installs get the column from `schema.sql`; existing DBs get it via `_apply_schema_migrations()` in `db/connection.py` (run as part of `pomo init` / any code path that calls `init_db()`).

## Time and Timezones

- **Storage**: The SQLite database stores all timestamps as **UTC** strings (`YYYY-MM-DD HH:MM:SS`). Do not use SQLite's `date('now')` or `CURRENT_TIMESTAMP` for queries that depend on the user's local day/week boundaries.
- **UI / Logic**: Everything the user sees or that is defined in calendar terms (e.g. "today", "this month", "last 30 days") uses the **effective display timezone** from the config (`timezone` setting, defaulting to `auto` for system local).
- **Conversions**: Always use the helpers in `pomocli/time_util.py` (like `utc_now_sql`, `get_display_tz`, `report_time_bounds`, `report_time_bounds_last_n_calendar_days`, `format_local`) to convert between UTC and the local display timezone, or to generate UTC bounds for SQL queries.

## Roadmap & Ideas

### Shipped

- Shell and Typer help (`-h`), command shorthands (`ss`, `pp`, `rr`, …), optional shell completion.
- Interactive command picker and interactive start (questionary autocomplete for tasks, projects, tags).
- Live dashboard (`pomo dash`) with `--detail minimal|normal|full`.
- Reporting with period summaries, session detail rows, and ASCII **Daily Trend** for multi-day ranges: per local **session start** day, logged duration, fixed-width **FBS** / **ATQ** (color vs previous day), then a bar scaled to the max day (`reports.py`).
- Distraction logging from CLI and from the macOS app (debounced, Swift-only global hotkey).
- Git repo and branch captured on sessions when available.
- Daemon logging with structured timestamps (UTC in log formatter).
- Improved logo for macos app and the status bar icon
- **UTC persistence** with **configurable display timezone** for reports and interactive history retention; centralized helpers in `time_util.py`.
- **Seed script** for realistic demo data; warns when seeding the default DB path without `POMOCLI_DB_PATH`.
- **Database backups** (`pomocli.db.backup`): optional gzip compression, rotation, manual `pomo backup`, and automatic background runs via the daemon.
- Improved interactive UX: cleaner `Ctrl-C` cancellation, de-duplicated fuzzy choices, duplicate-name reuse prompts, and snappier completion caches.
- Session lifecycle event logging for `start`, `pause`, `resume`, `extend`, `stop`, `kill`, `idle`, and `complete`.
- macOS menu bar icon uses **template** rendering (`pomocli-status-icon.png` primary, `pomocli-status-icon-dark.png` only if the primary PNG is absent from the app bundle) so the system picks contrast against the menu bar / wallpaper tint.
- Session management foundation:
  - `pomo session list` (alias `ssn list`) for today's sessions with status, focus block / attention-quality footers, total logged time, and distraction notes.
  - `pomo session edit|cancel|delete` for past sessions.
  - Deterministic short session IDs (`YY + padded session PK`, UTC-year based) shown in list/report and accepted by session commands.
  - Safe delete path for related session rows (`tags`, `distractions`, `session_events`), with foreign keys enabled in DB connections.
  - Added shorthand discoverability/examples for `session` commands (`ssn`).
- Human-readable duration formatting (`Xh Ym`) across list/report summaries.
- **Elapsed (stopwatch) sessions:** `pomo start --elapsed` and interactive “Stopwatch (elapsed time)”. Daemon `PomodoroTimer` supports `TimerMode.elapsed` (`start_elapsed`): counts up while running, no `on_complete` from the timer; `get_status()` exposes `timer_mode` and `elapsed_seconds`. Distractions do not extend the clock; `pomo extend` returns an error. Sessions persist `timer_mode` on the `sessions` table (`countdown` | `elapsed`); `init_db()` runs an idempotent `ALTER` for existing databases. CLI overrides: `--repo`, `--branch`. macOS menu bar shows elapsed with a stopwatch prefix; `pomo status` and `pomo dash` branch on `timer_mode`. **`pomo complete` / `cm`** and the macOS **Complete session** menu item call the daemon **`complete`** command for elapsed sessions only.
- **Focus metrics (`pomocli/metrics/focus.py`):** **Focus block success rate** (qualifying sessions with wall span ≥25 minutes; per-session score 1.0 minus 0.1 per pause event and per distraction, floored at 0). **Attention quality rate** (wall span minus pause intervals from `session_events` and up to 10 minutes distraction recovery per distraction, capped by time remaining in the session). Surfaced on `pomo report` session-detail footers, per-day **Daily Trend** rows (with `local_date_iso_from_stored_utc` bucketing), and `pomo session list`. Implementation uses `get_session_events`, `get_distraction_timestamps_for_session`, and `get_sessions_in_range` rows.
- **Session management polish:** `pomo session edit|cancel|delete` refuse the session currently bound to the daemon (or DB rows with `end_time` NULL and status `running`/`paused`). **`pomo session edit`** with no `--status`/`--duration` runs an interactive flow (when TTY): current values, field picker, confirmation summary before write. Covered by CLI tests (`test_session_edit_blocked_when_daemon_holds_session`, `test_session_edit_blocked_when_db_session_open_without_daemon`).

### Next Steps / High Priority

- Decide whether short session IDs should remain derived or be stored as a persisted unique column.
- **Insights on top of event stream (continued):**
  - Event-type summaries and drill-down beyond the two headline rates.
  - Treat `sessions.timer_mode = 'elapsed'` explicitly where other metrics assume a planned duration (e.g. classic focus rate vs target block length).
- **CLI / UX Improvements:**
  - Customize pomo shortcut keys for start, pause, resume, distract.
- **Distractions:**
  - Fix the glitchy distract recorder (prevent double beeps, ensure the timer doesn't show the old time before the extension is applied).
  - Add an optional popup from the macOS status bar to capture notes when a distraction occurs (with a toggle in the status bar UI to enable/disable).
- **macOS Status Bar:**
  - Add options for how the timer is displayed in the menu bar: show timer, hide timer and just show the session duration (just show active icon), or change icon color (e.g., green to red) as the focus block progresses.

### Future Features / Backlog

- **Session Management & History:**
  - Add the ability to score past sessions and attach notes to them.
- **Task & Project Management:**
  - Provide functionality to review and merge duplicate tasks or project names.
  - Add and update time estimates for tasks; surface these estimates in the UI.
- **Insights & Planning:**
  - Create a timeline view for days or weeks to reflect on how time was spent and adjust approaches.
  - Advanced scheduling: plan days/weeks for focus work, track actual time against those schedules, and analyze trends.
  - Leverage recorded session events (pause/resume/stop/kill/extend/idle) for timeline accuracy and deeper insights.
- **Aesthetics and UX**
  - adding menu control to open a new terminal shortcut key?
  - make the timer space be fixed so as the time changes without number of digits changing like for example going from 18:58 -> 11:11 the space remains fixed without small adjustments, kinda mono-space for the timer characters
  - make the macos app icon a bit smaller seems bigger compared to other apps in my mac, smaller square overall
  - 