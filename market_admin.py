"""Market Hours & Schedule saving: Jasmine's "Develop Market Hours Function".

The admin Market Hours page (templates/admin/market_hours.html) is built and
already calls these functions. Each one currently raises NotImplementedError,
which the page shows as a "not connected yet" notice. Fill in the bodies and
the page works with no other changes.

Raise MarketAdminError(message) for anything the admin did wrong (bad times,
duplicate date, ...): the page shows the message in red and keeps them on the form.

Tables (live RDS schema):

  market_schedule  - one row per weekday, already seeded (Mon-Fri open
                     9:30-16:00, Sat/Sun closed). UPDATE these rows; don't INSERT.
      day_of_week  ENUM('Monday', ..., 'Sunday')  UNIQUE
      is_open      TINYINT(1)
      open_time    TIME  NULL     (must be set when is_open = 1)
      close_time   TIME  NULL     (must be set when is_open = 1)
      updated_by   INT   NOT NULL -> admins.admin_id
      CHECK: is_open = 0 OR (open_time AND close_time set AND open_time < close_time)

  market_holidays
      holiday_id   INT AUTO_INCREMENT
      holiday_date DATE  UNIQUE
      description  VARCHAR(255) NOT NULL
      created_by   INT   NOT NULL -> admins.admin_id

Once these save, buying/selling and the price generator follow the new hours
automatically: market.get_market_status() reads these tables on every check.
"""


class MarketAdminError(Exception):
    """A problem with what the admin entered. The message is shown on the page."""


def update_market_schedule(admin_id, days):
    """Save the weekly trading hours.

    admin_id: the admins.admin_id of the admin making the change.
    days: list of 7 dicts, one per weekday, Monday first. For example:
        {"day_of_week": "Monday", "is_open": True,
         "open_time": "09:30", "close_time": "16:00"}
        {"day_of_week": "Saturday", "is_open": False,
         "open_time": "", "close_time": ""}
    Times are "HH:MM" strings straight from the form (may be "" for closed days).

    Should: check every open day has both times and open_time < close_time
    (raise MarketAdminError otherwise), then UPDATE each weekday's row with
    is_open, open_time, close_time (NULL when closed) and updated_by = admin_id.
    """
    raise NotImplementedError("Develop Market Hours Function: update_market_schedule")


def add_market_holiday(admin_id, holiday_date, description):
    """Add a full-day market closure.

    holiday_date: "YYYY-MM-DD" string from the form.
    description: e.g. "Thanksgiving".

    Should: require both fields, reject a date that's already a holiday
    (UNIQUE on holiday_date, MySQL error 1062) with MarketAdminError, then
    INSERT with created_by = admin_id.
    """
    raise NotImplementedError("Develop Market Hours Function: add_market_holiday")


def remove_market_holiday(admin_id, holiday_id):
    """Remove a holiday so the market opens normally that day.

    Should: DELETE FROM market_holidays WHERE holiday_id = %s.
    """
    raise NotImplementedError("Develop Market Hours Function: remove_market_holiday")
