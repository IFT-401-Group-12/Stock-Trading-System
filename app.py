import os
from decimal import Decimal

from dotenv import load_dotenv
from flask import (
    Flask, flash, jsonify, redirect, render_template, request, session, url_for,
)

from db import get_db_connection
from market import get_market_status, to_eastern
from price_generator import start_price_generator
from trading import (
    TradeError, cancel_order, get_cash_balance, get_holdings, get_live_stocks,
    get_orders, place_buy_order, place_sell_order,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

def current_user_id():
    """The logged-in customer's user_id.

    Login should set session["user_id"] after checking the password. Until
    login is wired up, set DEV_USER_ID in .env to test as that user.
    """
    user_id = session.get("user_id") or os.getenv("DEV_USER_ID")
    return int(user_id) if user_id else None


def login_required_redirect():
    flash("Please log in to trade.", "error")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

@app.template_filter("usd")
def usd(value):
    if value is None:
        return "—"
    return f"${Decimal(value):,.2f}"


@app.template_filter("compact_usd")
def compact_usd(value):
    value = Decimal(value or 0)
    for size, suffix in ((Decimal("1e12"), "T"), (Decimal("1e9"), "B"), (Decimal("1e6"), "M")):
        if value >= size:
            return f"${value / size:,.2f}{suffix}"
    return f"${value:,.2f}"


@app.template_filter("et")
def et(value, fmt="%b %-d, %Y · %-I:%M %p"):
    converted = to_eastern(value)
    return converted.strftime(fmt) if converted else "—"


@app.context_processor
def inject_market_status():
    """Makes market_open / market_message available on every page."""
    try:
        connection = get_db_connection()
        try:
            is_open, message = get_market_status(connection)
        finally:
            connection.close()
    except Exception:
        is_open, message = False, "Market status unavailable"
    return {"market_open": is_open, "market_message": message}


# ---------------------------------------------------------------------------
# Admin: create stock (Sarah)
# ---------------------------------------------------------------------------

def create_stock(ticker_symbol, company_name, initial_price, volume_available, created_by=None):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        sql = """
            INSERT INTO stocks
            (
                ticker_symbol,
                company_name,
                current_price,
                open_price,
                day_high,
                day_low,
                volume_available,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            ticker_symbol.upper(),
            company_name,
            initial_price,
            initial_price,
            initial_price,
            initial_price,
            volume_available,
            created_by
        )

        cursor.execute(sql, values)
        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


# ---------------------------------------------------------------------------
# Customer pages
# ---------------------------------------------------------------------------

@app.route("/")
def customer_dashboard():
    return render_template("customer_dashboard.html")


@app.route("/stocks")
def stocks():
    return render_template("stocks.html", stocks=get_live_stocks())


@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")


@app.route("/transactions")
def transactions():
    return render_template("transaction_history.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/signup")
def signup():
    return render_template("signup.html")


# ---------------------------------------------------------------------------
# Buy / Sell / Orders
# ---------------------------------------------------------------------------

def _order_flash(result):
    verb = "Bought" if result["side"] == "BUY" else "Sold"
    shares = f"{result['quantity']:,} share{'s' if result['quantity'] != 1 else ''}"

    if result["status"] == "EXECUTED":
        return (
            f"{verb} {shares} of {result['ticker']} at {usd(result['price'])} "
            f"· total {usd(result['total'])}."
        )

    side = "buy" if result["side"] == "BUY" else "sell"
    return (
        f"Limit order placed: {side} {shares} of {result['ticker']} at "
        f"{usd(result['price'])}. It will fill automatically when the price is reached."
    )


@app.route("/trade/buy", methods=["GET", "POST"])
def buy():
    user_id = current_user_id()
    if not user_id:
        return login_required_redirect()

    if request.method == "POST":
        try:
            result = place_buy_order(
                user_id,
                int(request.form.get("stock_id", 0)),
                request.form.get("quantity"),
                request.form.get("order_kind", "market"),
                request.form.get("limit_price"),
            )
            flash(_order_flash(result), "success")
            return redirect(url_for("orders") if result["status"] == "PENDING" else url_for("buy"))
        except (TradeError, ValueError) as error:
            flash(str(error) if isinstance(error, TradeError) else "Choose a stock to buy.", "error")
            return redirect(url_for("buy", stock_id=request.form.get("stock_id")))

    all_stocks = [s for s in get_live_stocks() if s["status"] == "live"]
    return render_template(
        "buy.html",
        stocks=all_stocks,
        selected_id=request.args.get("stock_id", type=int),
        cash=get_cash_balance(user_id),
    )


@app.route("/trade/sell", methods=["GET", "POST"])
def sell():
    user_id = current_user_id()
    if not user_id:
        return login_required_redirect()

    if request.method == "POST":
        try:
            result = place_sell_order(
                user_id,
                int(request.form.get("stock_id", 0)),
                request.form.get("quantity"),
                request.form.get("order_kind", "market"),
                request.form.get("limit_price"),
            )
            flash(_order_flash(result), "success")
            return redirect(url_for("orders") if result["status"] == "PENDING" else url_for("sell"))
        except (TradeError, ValueError) as error:
            flash(str(error) if isinstance(error, TradeError) else "Choose a stock to sell.", "error")
            return redirect(url_for("sell", stock_id=request.form.get("stock_id")))

    return render_template(
        "sell.html",
        holdings=get_holdings(user_id),
        selected_id=request.args.get("stock_id", type=int),
        cash=get_cash_balance(user_id),
    )


@app.route("/orders")
def orders():
    user_id = current_user_id()
    if not user_id:
        return login_required_redirect()

    return render_template(
        "orders.html",
        open_orders=get_orders(user_id, status="PENDING", limit=200),
        recent_orders=get_orders(user_id, limit=25),
    )


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
def cancel(order_id):
    user_id = current_user_id()
    if not user_id:
        return login_required_redirect()

    try:
        result = cancel_order(user_id, order_id)
        side = "buy" if result["side"] == "BUY" else "sell"
        released = (
            f"{usd(result['total'])} returned to your cash balance"
            if result["side"] == "BUY"
            else f"{result['quantity']:,} shares returned to your portfolio"
        )
        flash(f"Cancelled limit {side} order #{order_id} for {result['ticker']} · {released}.", "success")
    except TradeError as error:
        flash(str(error), "error")

    return redirect(url_for("orders"))


@app.route("/api/stocks")
def api_stocks():
    """Live prices for the Stocks, Buy and Sell pages to refresh without reloading."""
    return jsonify([
        {
            "stock_id": s["stock_id"],
            "ticker": s["ticker_symbol"],
            "current_price": float(s["current_price"]),
            "open_price": float(s["open_price"]) if s["open_price"] is not None else None,
            "day_high": float(s["day_high"]) if s["day_high"] is not None else None,
            "day_low": float(s["day_low"]) if s["day_low"] is not None else None,
            "volume_available": s["volume_available"],
            "status": s["status"],
        }
        for s in get_live_stocks()
    ])


# Start the Random Stock Price Generator when the server handles its first
# request. (Starting it here rather than at import keeps Flask's debug reloader
# from running a second copy; a MySQL lock also guarantees only one runs.)
@app.before_request
def ensure_price_generator_running():
    start_price_generator()


if __name__ == "__main__":
    app.run(debug=True)
