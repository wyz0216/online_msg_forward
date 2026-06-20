from datetime import datetime, timedelta, timezone


SHANGHAI_TZ = timezone(timedelta(hours=8), "UTC+08:00")


def format_shanghai_time(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S UTC+08:00")
