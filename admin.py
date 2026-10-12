"""Administrator Web Interface: Create Stock, and Market Hours & Schedule.

Every page here requires the current user to be in the admins table.

* Create Stock saves through Sarah's create_stock() (stocks.py).
* Market Hours saves through Jasmine's functions in market_admin.py, which
  aren't written yet; until they are, saving shows a "not connected yet" notice.
"""

import re
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import errors as mysql_errors

import market_admin
from auth import current_admin_id, current_user_id
from db import get_db_connection
from stocks import create_stock

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def admin_required(view):
    """Only admins get in. Admin id is passed to the view as admin_id."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            flash("Please log in as an administrator.", "error")
            return redirect(url_for("login"))

        admin_id = current_admin_id()
        if not admin_id:
            flash("That page is for administrators only.", "error")
            return redirect(url_for("customer_dashboard"))

        return view(*args, admin_id=admin_id, **kwargs)

    return wrapper


def _fetch_all(sql, params=()):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def _time_value(value):
    """TIME columns come back as timedelta; format as HH:MM for <input type="time">."""
    if value is None:
        return ""
    total = int(value.total_seconds())
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


# ---------------------------------------------------------------------------
# Create Stock
# ---------------------------------------------------------------------------

def _validate_new_stock(form):
    """Check the Create Stock form. Returns (values, errors)."""
    errors = {}

    ticker = form.get("ticker_symbol", "").strip().upper()
    company = form.get("company_name", "").strip()
    price_raw = form.get("initial_price", "").strip().replace("$", "").replace(",", "")
    volume_raw = form.get("volume_available", "").strip().replace(",", "")

    if not TICKER_PATTERN.match(ticker):
        errors["ticker_symbol"] = "Use 1 to 5 letters, like AAPL."

    if not company:
        errors["company_name"] = "Enter the company name."
    elif len(company) > 255:
        errors["company_name"] = "Company name is too long."

    price = None
    try:
        price = Decimal(price_raw).quantize(Decimal("0.01"))
        if price <= 0:
            errors["initial_price"] = "Price must be greater than $0.00."
        elif price >= Decimal("100000000"):
            errors["initial_price"] = "Price is too large."
    except (InvalidOperation, ValueError):
        errors["initial_price"] = "Enter a price, like 125.50."

    volume = None
    try:
        volume = int(volume_raw)
        if volume < 1:
            errors["volume_available"] = "Volume must be at least 1 share."
        elif volume > 2_000_000_000:
            errors["volume_available"] = "Volume is too large."
    except ValueError:
        errors["volume_available"] = "Enter a whole number of shares."

    values = {
        "ticker_symbol": ticker,
        "company_name": company,
        "initial_price": price,
        "volume_available": volume,
    }
    return values, errors


@admin_bp.route("/")
@admin_required
def home(admin_id):
    return redirect(url_for("admin.stocks"))


@admin_bp.route("/stocks", methods=["GET", "POST"])
@admin_required
def stocks(admin_id):
    form = {}
    errors = {}

    if request.method == "POST":
        form = request.form
        values, errors = _validate_new_stock(form)

        if not errors:
            try:
                create_stock(
                    values["ticker_symbol"],
                    values["company_name"],
                    values["initial_price"],
                    values["volume_available"],
                    created_by=admin_id,
                )
                flash(
                    f"{values['ticker_symbol']} is now listed at ${values['initial_price']:,.2f} "
                    f"with {values['volume_available']:,} shares. Its price starts moving "
                    "with the market.",
                    "success",
                )
                return redirect(url_for("admin.stocks"))
            except mysql_errors.IntegrityError as error:
                if error.errno == 1062:  # duplicate key: ticker already exists
                    errors["ticker_symbol"] = f"{values['ticker_symbol']} is already listed."
                else:
                    raise

        flash("Please fix the highlighted fields.", "error")

    listings = _fetch_all(
        "SELECT s.stock_id, s.ticker_symbol, s.company_name, s.current_price, "
        "s.volume_available, s.status, s.created_at, u.username AS created_by_name "
        "FROM stocks s "
        "LEFT JOIN admins a ON a.admin_id = s.created_by "
        "LEFT JOIN users u ON u.user_id = a.user_id "
        "ORDER BY s.created_at DESC, s.stock_id DESC"
    )

    return render_template(
        "admin/create_stock.html",
        listings=listings,
        form=form,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Market Hours & Schedule
# ---------------------------------------------------------------------------

def _load_schedule():
    rows = {
        r["day_of_week"]: r
        for r in _fetch_all(
            "SELECT day_of_week, is_open, open_time, close_time, updated_at "
            "FROM market_schedule"
        )
    }
    days = []
    for day in WEEKDAYS:
        row = rows.get(day)
        days.append({
            "day_of_week": day,
            "is_open": bool(row and row["is_open"]),
            "open_time": _time_value(row["open_time"]) if row else "",
            "close_time": _time_value(row["close_time"]) if row else "",
            "saved": row is not None,
            "updated_at": row["updated_at"] if row else None,
        })
    return days


@admin_bp.route("/market-hours")
@admin_required
def market_hours(admin_id):
    holidays = _fetch_all(
        "SELECT holiday_id, holiday_date, description FROM market_holidays "
        "ORDER BY holiday_date"
    )
    return render_template(
        "admin/market_hours.html",
        days=_load_schedule(),
        holidays=holidays,
    )


def _run_market_admin(action, success_message):
    """Call one of Jasmine's market_admin functions and report the result."""
    try:
        action()
        flash(success_message, "success")
    except NotImplementedError:
        flash(
            "Saving isn't connected yet. This page is ready; the save logic is the "
            "Develop Market Hours Function (market_admin.py).",
            "info",
        )
    except market_admin.MarketAdminError as error:
        flash(str(error), "error")
    return redirect(url_for("admin.market_hours"))


@admin_bp.route("/market-hours", methods=["POST"])
@admin_required
def save_market_hours(admin_id):
    days = [
        {
            "day_of_week": day,
            "is_open": request.form.get(f"{day}_is_open") == "on",
            "open_time": request.form.get(f"{day}_open_time", "").strip(),
            "close_time": request.form.get(f"{day}_close_time", "").strip(),
        }
        for day in WEEKDAYS
    ]
    return _run_market_admin(
        lambda: market_admin.update_market_schedule(admin_id, days),
        "Trading hours saved.",
    )


@admin_bp.route("/holidays", methods=["POST"])
@admin_required
def add_holiday(admin_id):
    holiday_date = request.form.get("holiday_date", "").strip()
    description = request.form.get("description", "").strip()
    return _run_market_admin(
        lambda: market_admin.add_market_holiday(admin_id, holiday_date, description),
        f"Holiday added: {description or holiday_date}.",
    )


@admin_bp.route("/holidays/<int:holiday_id>/remove", methods=["POST"])
@admin_required
def remove_holiday(admin_id, holiday_id):
    return _run_market_admin(
        lambda: market_admin.remove_market_holiday(admin_id, holiday_id),
        "Holiday removed.",
    )
