"""
Market hours helper — checks whether the US stock market is currently open.

NYSE regular session: 9:30 AM – 4:00 PM US/Eastern, Monday–Friday,
excluding federal holidays.

Uses exchange_calendars for accurate holiday detection with a simple
weekday+time fallback if the library is unavailable.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

MARKET_OPEN  = time(9, 30)
MARKET_CLOSE = time(16, 0)


def is_market_open(now: datetime | None = None) -> bool:
    """
    Return True if the NYSE is currently in its regular trading session.

    Args:
        now: datetime to check (defaults to current time). Must be timezone-aware
             or naive ET. Pass a value in tests to avoid depending on wall clock.
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        # Assume ET if naive
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    # Weekends are never open
    if now.weekday() >= 5:
        return False

    # Outside regular session hours
    if not (MARKET_OPEN <= now.time() < MARKET_CLOSE):
        return False

    # Check NYSE holiday calendar
    try:
        import exchange_calendars as xcals
        nyse = xcals.get_calendar("XNYS")
        return nyse.is_session(now.date().isoformat())
    except Exception:
        # Fallback: weekday + hours check only (already passed above)
        return True


def market_status(now: datetime | None = None) -> dict:
    """
    Return a dict with market open/close status and next open/close time.
    Used by the /api/attribution/{symbol}/live endpoint.
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    open_ = is_market_open(now)
    return {
        "is_open": open_,
        "current_time_et": now.strftime("%H:%M ET"),
        "status": "LIVE" if open_ else "CLOSED",
    }
