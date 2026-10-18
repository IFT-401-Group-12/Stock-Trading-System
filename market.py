"""Market hours gate.

Every buy, sell and cancel checks this first (Process Map: "market-open gate").
The schedule lives in the `market_schedule` table (one row per weekday, set
by an admin) and `market_holidays` (dates the market is closed all day).

Market hours are Eastern time, no matter what time zone the server runs in.
"""

import os
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")


def now_eastern():
    return datetime.now(MARKET_TZ)


def to_eastern(value):
    """Convert a naive UTC datetime from the database to Eastern time."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(MARKET_TZ)


def start_of_today_utc():
    """Midnight Eastern today, as a naive UTC datetime (for database queries)."""
    midnight = datetime.combine(now_eastern().date(), time(0, 0), MARKET_TZ)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _as_time(value):
    """mysql.connector returns TIME columns as timedelta; turn them into time."""
    if value is None or isinstance(value, time):
        return value
    total = int(value.total_seconds())
    return time(total // 3600, (total % 3600) // 60, total % 60)


def get_market_status(connection, now=None):
    """Return (is_open, message) for right now.

    For testing outside market hours, set MARKET_ALWAYS_OPEN=1 in .env.
    """
    if os.getenv("MARKET_ALWAYS_OPEN") == "1":
        return True, "Market Open (testing override)"

    now = now or now_eastern()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT description FROM market_holidays WHERE holiday_date = %s",
            (now.date(),),
        )
        holiday = cursor.fetchone()
        if holiday:
            return False, f"Market Closed: {holiday['description']}"

        cursor.execute(
            "SELECT is_open, open_time, close_time FROM market_schedule "
            "WHERE day_of_week = %s",
            (now.strftime("%A"),),
        )
        day = cursor.fetchone()
    finally:
        cursor.close()

    if not day:
        return False, "Market Closed: no trading hours have been set for today"

    if not day["is_open"]:
        return False, f"Market Closed: closed on {now.strftime('%A')}s"

    open_time = _as_time(day["open_time"])
    close_time = _as_time(day["close_time"])
    hours = f"{open_time.strftime('%-I:%M %p')} – {close_time.strftime('%-I:%M %p')} ET"

    if open_time <= now.time() < close_time:
        return True, f"Market Open · {hours}"

    return False, f"Market Closed · trading hours are {hours}"
