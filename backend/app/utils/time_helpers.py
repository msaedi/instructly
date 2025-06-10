from datetime import datetime, time

def time_to_string(t: time) -> str:
    """Always return HH:MM:SS format"""
    return t.strftime("%H:%M:%S")

def string_to_time(time_str: str) -> time:
    """Parse time string flexibly"""
    # Handle both HH:MM and HH:MM:SS
    if len(time_str) == 5:  # HH:MM
        time_str += ":00"  # Add seconds
    return datetime.strptime(time_str, "%H:%M:%S").time()