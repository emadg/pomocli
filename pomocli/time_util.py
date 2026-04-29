import zoneinfo
from datetime import datetime, timezone, timedelta, tzinfo
from typing import cast
from typing import Optional, Tuple

SQLITE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_duration_hm(total_seconds: int) -> str:
    """Format seconds as human-friendly hours/minutes."""
    total_minutes = max(0, int(total_seconds)) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def format_duration_hms(total_seconds: int) -> str:
    """Format seconds including seconds (for deltas and precise spans)."""
    s = max(0, int(total_seconds))
    hours, rem = divmod(s, 3600)
    minutes, sec = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {sec}s"
    if minutes > 0:
        return f"{minutes}m {sec}s"
    return f"{sec}s"

def utc_now_sql() -> str:
    """Return the current UTC time formatted for SQLite."""
    return datetime.now(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)

def get_display_tz(timezone_config: str) -> tzinfo:
    """Resolve a timezone config string to a tzinfo object."""
    if not timezone_config or timezone_config.lower() == "auto":
        # Returns the system local timezone
        local_tz = datetime.now().astimezone().tzinfo
        return cast(tzinfo, local_tz or timezone.utc)
    try:
        return zoneinfo.ZoneInfo(timezone_config)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError(f"Invalid timezone configuration: {timezone_config}")

def parse_stored_utc(naive_sql_str: str) -> datetime:
    """Parse a naive SQLite datetime string and attach UTC timezone."""
    dt = datetime.strptime(naive_sql_str, SQLITE_DATETIME_FORMAT)
    return dt.replace(tzinfo=timezone.utc)

def local_date_iso_from_stored_utc(naive_sql_str: str, tz: tzinfo) -> str:
    """
    Local calendar date ``YYYY-MM-DD`` for a UTC-stored SQLite datetime string.

    Used for report/day bucketing: a session is attributed entirely to the **local
    calendar day of its start** (``start_time``), even when ``end_time`` falls on
    the next local day (e.g. 10 Mar 23:45 → 11 Mar 01:00 counts only toward 10 Mar).
    """
    return parse_stored_utc(naive_sql_str).astimezone(tz).date().isoformat()


def format_local(dt_utc_naive_or_aware: datetime | str, timezone_config: str) -> str:
    """Format a UTC datetime (or string) to local time string."""
    if isinstance(dt_utc_naive_or_aware, str):
        dt = parse_stored_utc(dt_utc_naive_or_aware)
    else:
        if dt_utc_naive_or_aware.tzinfo is None:
            dt = dt_utc_naive_or_aware.replace(tzinfo=timezone.utc)
        else:
            dt = dt_utc_naive_or_aware
            
    tz = get_display_tz(timezone_config)
    return dt.astimezone(tz).strftime(SQLITE_DATETIME_FORMAT)

def retention_cutoff_utc(days: int, tz: tzinfo) -> str:
    """
    Return the UTC instant of local midnight at start of (local_today - days).
    Used as a lower bound for "task touched in the last N local calendar days".
    """
    now_local = datetime.now(tz)
    local_today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_local = local_today_midnight - timedelta(days=days)
    return cutoff_local.astimezone(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)

def report_time_bounds(period: str, tz: tzinfo) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (start_utc_sql_inclusive, end_utc_sql_exclusive) bounds for a report period.
    Periods: 'today', 'week' (last 7 days), 'month' (start of month), 'quarter' (last 90 days), 'all'
    """
    if period == "all":
        return None, None
        
    now_local = datetime.now(tz)
    local_today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # End bound is always tomorrow midnight (exclusive)
    tomorrow_midnight = local_today_midnight + timedelta(days=1)
    end_utc = tomorrow_midnight.astimezone(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)
    
    if period == "today":
        start_local = local_today_midnight
    elif period == "week":
        start_local = local_today_midnight - timedelta(days=7)
    elif period == "month":
        start_local = local_today_midnight.replace(day=1)
    elif period == "quarter":
        start_local = local_today_midnight - timedelta(days=90)
    else:
        return None, None
        
    start_utc = start_local.astimezone(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)
    return start_utc, end_utc


def report_time_bounds_last_n_calendar_days(n: int, tz: tzinfo) -> Tuple[str, str]:
    """
    UTC bounds (start inclusive, end exclusive) for the last ``n`` local calendar
    days ending today: from local midnight at (today - (n - 1)) through tomorrow
    local midnight.

    Requires ``n >= 2`` (use ``report_time_bounds(\"today\", tz)`` for a single day).
    """
    if n < 2:
        raise ValueError("last_n_calendar_days requires n >= 2; use report_time_bounds('today', tz) for one day")

    now_local = datetime.now(tz)
    local_today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_midnight = local_today_midnight + timedelta(days=1)
    end_utc = tomorrow_midnight.astimezone(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)
    start_local = local_today_midnight - timedelta(days=n - 1)
    start_utc = start_local.astimezone(timezone.utc).strftime(SQLITE_DATETIME_FORMAT)
    return start_utc, end_utc
