"""Timezone utilities ensuring 100% consistent Indian Standard Time (IST) across all environments."""
import datetime
from datetime import timezone, timedelta
from typing import Optional

# Indian Standard Time (UTC + 05:30)
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime.datetime:
    """Return current timezone-aware datetime in Indian Standard Time (IST)."""
    return datetime.datetime.now(IST)

def now_ist_naive() -> datetime.datetime:
    """
    Return current IST datetime as naive datetime (without tzinfo).
    Allows direct arithmetic and comparisons with train schedule timestamps
    which are stored without tzinfo.
    """
    return datetime.datetime.now(IST).replace(tzinfo=None)

def today_ist() -> datetime.date:
    """Return today's date in Indian Standard Time (IST)."""
    return now_ist().date()

def time_ist() -> datetime.time:
    """Return current time in Indian Standard Time (IST)."""
    return now_ist_naive().time()

def format_ist_time(dt: Optional[datetime.datetime] = None, include_seconds: bool = True, fmt_12h: bool = True) -> str:
    """
    Format a datetime (or current time if None) in Indian Standard Time (IST).
    Examples:
      - 12h: "05:40:23 PM IST" or "05:40 PM IST"
      - 24h: "17:40:23 IST" or "17:40 IST"
    """
    if dt is None:
        target = now_ist()
    elif dt.tzinfo is None:
        # If naive, treat as IST
        target = dt
    else:
        target = dt.astimezone(IST)

    if fmt_12h:
        pattern = "%I:%M:%S %p IST" if include_seconds else "%I:%M %p IST"
    else:
        pattern = "%H:%M:%S IST" if include_seconds else "%H:%M IST"
    return target.strftime(pattern)

def format_ist_datetime(dt: Optional[datetime.datetime] = None) -> str:
    """Format datetime as 'YYYY-MM-DD HH:MM:SS IST'."""
    if dt is None:
        target = now_ist()
    elif dt.tzinfo is None:
        target = dt
    else:
        target = dt.astimezone(IST)
    return target.strftime("%Y-%m-%d %H:%M:%S IST")
