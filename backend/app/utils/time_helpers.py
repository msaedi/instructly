from datetime import datetime, time


def time_to_string(t: time) -> str:
    """Always return HH:MM:SS format"""
    return t.strftime("%H:%M:%S")


def string_to_time(time_str: str) -> time:
    """Parse time strings flexibly, handling bitmap '24:00[:00]' sentinels."""
    normalized = time_str
    if len(normalized) == 5:
        normalized += ":00"
    if normalized == "24:00:00":
        return time(0, 0)
    return datetime.strptime(normalized, "%H:%M:%S").time()
