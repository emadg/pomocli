# Developers guide

## Time and timezones

- **Storage:** SQLite keeps instants as **UTC** strings (`YYYY-MM-DD HH:MM:SS`). Do not rely on SQLite `date('now')` or naive `date(start_time)` for user-facing calendar periods.
- **Display / rules:** Anything the user reads as a clock time or calendar bucket (“today”, “this month”, “last 30 days”) uses the **effective display timezone** from config (`timezone`, default `auto` = system local).
- **Code:** Use [`pomocli/time_util.py`](pomocli/time_util.py)—`utc_now_sql`, `get_display_tz`, `parse_stored_utc`, `report_time_bounds`, `retention_cutoff_utc`, `format_local`—instead of duplicating offset or boundary logic.

## Roadmap

### Shipped

- Shell and Typer help (`-h`), command shorthands (`ss`, `pp`, `rr`, …), optional shell completion.
- Interactive command picker and interactive start (questionary autocomplete for tasks, projects, tags).
- Live dashboard (`pomo dash`) with `--detail minimal|normal|full`.
- Reporting with period summaries and ASCII daily trend charts (`today` / `week` / `month` / `quarter` / `all`).
- Distraction logging from CLI and from the macOS app (debounced, Swift-only global hotkey).
- Git repo and branch captured on sessions when available.
- Daemon logging with structured timestamps (UTC in log formatter).
- **UTC persistence** with **configurable display timezone** for reports and interactive history retention; centralized helpers in `time_util.py`.
- **Seed script** for realistic demo data; warns when seeding the default DB path without `POMOCLI_DB_PATH`.
- **Database backups** (`pomocli.db.backup`): optional gzip compression, rotation, manual `pomo backup`, and automatic background runs via the daemon.

### Next up

- **CLI / UX:** Configurable shortcuts for start, pause, resume, distract (beyond Typer shorthands). Polish session lifecycle when stop, kill, and idle interact.
- **Branding:** Status bar and CLI/dashboard logo refinements.
- **Tasks:** Surface estimates in the UI; edit or roll up estimates over time.
- **Insights:** Timeline or week view for reflection; optional goals or planned focus blocks vs. actual time.

### Ideas (backlog)

- Scheduling recurring focus blocks and comparing planned vs. actual.
- Richer analysis (trends, exports) building on the same UTC + `time_util` boundaries.
