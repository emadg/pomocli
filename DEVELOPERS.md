# Developers Guide

## Time and Timezones

- **Storage**: The SQLite database stores all timestamps as **UTC** strings (`YYYY-MM-DD HH:MM:SS`). Do not use SQLite's `date('now')` or `CURRENT_TIMESTAMP` for queries that depend on the user's local day/week boundaries.
- **UI / Logic**: Everything the user sees or that is defined in calendar terms (e.g. "today", "this month", "last 30 days") uses the **effective display timezone** from the config (`timezone` setting, defaulting to `auto` for system local).
- **Conversions**: Always use the helpers in `pomocli/time_util.py` (like `utc_now_sql`, `get_display_tz`, `report_time_bounds`, `format_local`) to convert between UTC and the local display timezone, or to generate UTC bounds for SQL queries.

## Roadmap for new/enhanced features

### Completed in Round One
- [x] enhance auto-completion for commands, help (added `-h` and shell completion)
- [x] enhance interactive mode (filter down commands as user types, fuzzy search via questionary autocomplete)
- [x] enhance interactive start for project, task, etc (fuzzy search, arrow navigation, tab completion, etc)
- [x] shorthand commands, i.e. pomo ss, pp, rr, dd, sp, stt
- [x] enhance pomo dash, configurable levels of details (`--detail minimal|normal|full`)
- [x] a better less glitchy distract record shortcut (debounced and Swift-only)
- [x] improve reporting, show trends over week, month, quarter (added ASCII trend charts)
- [x] improve logging, add start and end time, date (added standard logging to daemon)

### Next Steps / Future Rounds
- customize pomo shortcut keys for start pause, resume, distract
- add a logo for status bar and cli/dash (an hour glass top shaped as a tomato?)
- improve the state transitions and recorded logs when session is stopped/idle machine/...
- adding schedule / adding estimates for tasks / update estimates
- create a timeline view for days or a week, to see how I spent my time for reflection and updating my approach for next week
- some advanced features, like scheduling days, weeks for focus work and track time against those schedules and analyze for trends

Other ideas added:

