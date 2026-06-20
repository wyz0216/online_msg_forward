from app.time_utils import format_shanghai_time


def test_format_shanghai_time_converts_sqlite_utc_timestamp():
    assert format_shanghai_time("2026-06-20 10:15:30") == "2026-06-20 18:15:30 UTC+08:00"


def test_format_shanghai_time_converts_aware_utc_iso_timestamp():
    assert format_shanghai_time("2026-06-20T10:15:30+00:00") == "2026-06-20 18:15:30 UTC+08:00"


def test_format_shanghai_time_keeps_empty_values_empty():
    assert format_shanghai_time(None) == ""
