import pytest
import zoneinfo
from datetime import datetime, timezone, timedelta
from pomocli.time_util import (
    utc_now_sql,
    get_display_tz,
    parse_stored_utc,
    format_local,
    retention_cutoff_utc,
    report_time_bounds,
    report_time_bounds_last_n_calendar_days,
    format_duration_hm,
    format_duration_hms,
    local_date_iso_from_stored_utc,
)

def test_utc_now_sql():
    val = utc_now_sql()
    assert len(val) == 19
    # Ensure it parses back
    dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    assert dt.year >= 2024

def test_get_display_tz():
    tz_auto = get_display_tz("auto")
    assert isinstance(tz_auto, timezone) or isinstance(tz_auto, zoneinfo.ZoneInfo)
    
    tz_berlin = get_display_tz("Europe/Berlin")
    assert tz_berlin.key == "Europe/Berlin"
    
    with pytest.raises(ValueError):
        get_display_tz("Invalid/Zone")

def test_parse_stored_utc():
    s = "2025-01-01 12:00:00"
    dt = parse_stored_utc(s)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025
    assert dt.hour == 12

def test_format_local():
    s = "2025-01-01 12:00:00"
    # UTC to Berlin (CET is +1 in Jan)
    local_str = format_local(s, "Europe/Berlin")
    assert local_str == "2025-01-01 13:00:00"
    
    # UTC to NY (EST is -5 in Jan)
    local_str_ny = format_local(s, "America/New_York")
    assert local_str_ny == "2025-01-01 07:00:00"

def test_retention_cutoff_utc(mocker):
    # Mock datetime.now to return a fixed local time
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    fixed_now = datetime(2025, 1, 10, 15, 30, 0, tzinfo=tz)
    
    class MockDatetime:
        @classmethod
        def now(cls, tz=None):
            if tz:
                return fixed_now.astimezone(tz)
            return fixed_now

    mocker.patch("pomocli.time_util.datetime", MockDatetime)
    
    # 0 days retention = today midnight local (2025-01-10 00:00:00 Berlin) -> 2025-01-09 23:00:00 UTC
    cutoff = retention_cutoff_utc(0, tz)
    assert cutoff == "2025-01-09 23:00:00"
    
    # 1 day retention = yesterday midnight local (2025-01-09 00:00:00 Berlin) -> 2025-01-08 23:00:00 UTC
    cutoff_1 = retention_cutoff_utc(1, tz)
    assert cutoff_1 == "2025-01-08 23:00:00"

def test_report_time_bounds(mocker):
    tz = zoneinfo.ZoneInfo("America/New_York")
    fixed_now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=tz)
    
    class MockDatetime:
        @classmethod
        def now(cls, tz=None):
            if tz:
                return fixed_now.astimezone(tz)
            return fixed_now

    mocker.patch("pomocli.time_util.datetime", MockDatetime)
    
    # "today" -> start: 2025-01-15 00:00:00 NY -> 2025-01-15 05:00:00 UTC
    # end: 2025-01-16 00:00:00 NY -> 2025-01-16 05:00:00 UTC
    start, end = report_time_bounds("today", tz)
    assert start == "2025-01-15 05:00:00"
    assert end == "2025-01-16 05:00:00"
    
    # "week" -> start: 2025-01-08 00:00:00 NY -> 2025-01-08 05:00:00 UTC
    start_w, end_w = report_time_bounds("week", tz)
    assert start_w == "2025-01-08 05:00:00"
    assert end_w == "2025-01-16 05:00:00"
    
    # "month" -> start: 2025-01-01 00:00:00 NY -> 2025-01-01 05:00:00 UTC
    start_m, end_m = report_time_bounds("month", tz)
    assert start_m == "2025-01-01 05:00:00"
    assert end_m == "2025-01-16 05:00:00"
    
    # "all" -> None, None
    start_a, end_a = report_time_bounds("all", tz)
    assert start_a is None
    assert end_a is None

    # Last 7 local calendar days ending today: Jan 9 00:00 .. Jan 16 00:00 NY
    start_7, end_7 = report_time_bounds_last_n_calendar_days(7, tz)
    assert start_7 == "2025-01-09 05:00:00"
    assert end_7 == "2025-01-16 05:00:00"

    with pytest.raises(ValueError):
        report_time_bounds_last_n_calendar_days(1, tz)


def test_format_duration_hm():
    assert format_duration_hm(0) == "0m"
    assert format_duration_hm(60) == "1m"
    assert format_duration_hm(1500) == "25m"
    assert format_duration_hm(3900) == "1h 5m"


def test_local_date_iso_from_stored_utc():
    tz = zoneinfo.ZoneInfo("UTC")
    assert local_date_iso_from_stored_utc("2025-06-01 23:00:00", tz) == "2025-06-01"
    tz_b = zoneinfo.ZoneInfo("Europe/Berlin")
    assert local_date_iso_from_stored_utc("2025-06-01 22:00:00", tz_b) == "2025-06-02"


def test_format_duration_hms():
    assert format_duration_hms(0) == "0s"
    assert format_duration_hms(45) == "45s"
    assert format_duration_hms(90) == "1m 30s"
    assert format_duration_hms(3665) == "1h 1m 5s"
