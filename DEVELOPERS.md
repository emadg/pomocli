# Developers Guide

## Time and Timezones

- **Storage**: The SQLite database stores all timestamps as **UTC** strings (`YYYY-MM-DD HH:MM:SS`). Do not use SQLite's `date('now')` or `CURRENT_TIMESTAMP` for queries that depend on the user's local day/week boundaries.
- **UI / Logic**: Everything the user sees or that is defined in calendar terms (e.g. "today", "this month", "last 30 days") uses the **effective display timezone** from the config (`timezone` setting, defaulting to `auto` for system local).
- **Conversions**: Always use the helpers in `pomocli/time_util.py` (like `utc_now_sql`, `get_display_tz`, `report_time_bounds`, `format_local`) to convert between UTC and the local display timezone, or to generate UTC bounds for SQL queries.

## Roadmap & Ideas

### Shipped

- Shell and Typer help (`-h`), command shorthands (`ss`, `pp`, `rr`, …), optional shell completion.
- Interactive command picker and interactive start (questionary autocomplete for tasks, projects, tags).
- Live dashboard (`pomo dash`) with `--detail minimal|normal|full`.
- Reporting with period summaries, session detail rows, and ASCII daily trend charts (`today` / `week` / `month` / `quarter` / `all`).
- Distraction logging from CLI and from the macOS app (debounced, Swift-only global hotkey).
- Git repo and branch captured on sessions when available.
- Daemon logging with structured timestamps (UTC in log formatter).
- Improved logo for macos app and the status bar icon
- **UTC persistence** with **configurable display timezone** for reports and interactive history retention; centralized helpers in `time_util.py`.
- **Seed script** for realistic demo data; warns when seeding the default DB path without `POMOCLI_DB_PATH`.
- **Database backups** (`pomocli.db.backup`): optional gzip compression, rotation, manual `pomo backup`, and automatic background runs via the daemon.
- Improved interactive UX: cleaner `Ctrl-C` cancellation, de-duplicated fuzzy choices, duplicate-name reuse prompts, and snappier completion caches.
- Session lifecycle event logging for `start`, `pause`, `resume`, `extend`, `stop`, `kill`, `idle`, and `complete`.
- Dark-mode status bar icon support via `pomocli-status-icon-dark.png` (with fallback to default icon).
- Session management foundation:
  - `pomo session list` (alias `ssn list`) for today's sessions with status, focus rate, and distraction notes.
  - `pomo session edit|cancel|delete` for past sessions.
  - Deterministic short session IDs (`YY + padded session PK`, UTC-year based) shown in list/report and accepted by session commands.
  - Safe delete path for related session rows (`tags`, `distractions`, `session_events`), with foreign keys enabled in DB connections.
  - Added shorthand discoverability/examples for `session` commands (`ssn`).
- Human-readable duration formatting (`Xh Ym`) across list/report summaries.

### Next Steps / High Priority

- **Session Management Polish (Phase 4 continuation):**
  - Add stronger safety checks around mutating/deleting sessions that are currently active.
  - Improve session edit UX (interactive mode, validation hints, and confirmation summaries).
  - Decide whether short session IDs should remain derived or be stored as a persisted unique column.
- **Insights on top of event stream:**
  - Use `session_events` in user-facing analytics (not only persistence), including event-type summaries and drill-down.
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
