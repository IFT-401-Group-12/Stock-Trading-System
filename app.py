import os
from decimal import Decimal

from dotenv import load_dotenv
from flask import (
    Flask, flash, jsonify, redirect, render_template, request, session, url_for,
)

from admin import admin_bp
from auth import AuthError, create_user, current_admin_id, current_user_id, verify_login
from banking import BankingError, deposit, withdraw, get_linked_accounts, money
from db import get_db_connection
from market import get_market_status, to_eastern
from price_generator import start_price_generator
from stocks import create_stock  # noqa: F401  (Sarah's function; used by the admin pages)
from trading import (
    TradeError, cancel_order, get_cash_balance, get_holdings, get_live_stocks,
    get_orders, place_buy_order, place_sell_order,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")
app.register_blueprint(admin_bp)


# ---------------------------------------------------------------------------
# Current user (see auth.py)
# ---------------------------------------------------------------------------

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

    try:
        is_admin = current_admin_id() is not None
    except Exception:
        is_admin = False

    return {"market_open": is_open, "market_message": message, "is_admin": is_admin}


# ---------------------------------------------------------------------------
# Customer pages
# ---------------------------------------------------------------------------
        
def get_transaction_history(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        sql = """
        SELECT
            t.transaction_id,
            t.created_at,
            t.transaction_type,
            s.ticker_symbol,
            t.quantity,
            t.price,
            t.total_amount,
            t.linked_account_id,
            t.balance_after,
            CASE
                WHEN t.transaction_type = 'CANCELLED' THEN 'CANCELLED'
                ELSE 'COMPLETED'
            END AS status
        FROM transactions t
        LEFT JOIN stocks s
            ON t.stock_id = s.stock_id
        WHERE t.user_id = %s
        ORDER BY t.created_at DESC, t.transaction_id DESC
        """

        

        cursor.execute(sql, (user_id,))
        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()
        
        

def get_current_orders(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        sql = """
            SELECT
                o.order_id,
                o.created_at,
                o.order_type,
                s.ticker_symbol,
                o.quantity,
                o.price,
                (o.quantity * o.price) AS total_amount,
                o.status
            FROM orders o
            JOIN stocks s
                ON o.stock_id = s.stock_id
            WHERE o.user_id = %s
                AND o.status = 'PENDING'
            ORDER BY o.created_at DESC, o.order_id DESC
        """

        cursor.execute(sql, (user_id,))
        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()
   
@app.route("/")
@app.route("/dashboard")
def customer_dashboard():
    user_id = current_user_id()

    if not user_id:
        return login_required_redirect()

    cash_balance = get_cash_balance(user_id)
    holdings = get_holdings(user_id)

    holdings_value = sum(
        Decimal(str(holding["quantity"])) * Decimal(str(holding["current_price"]))
        for holding in holdings
    )

    return render_template(
        "dashboard.html",
        cash_balance=cash_balance,
        total_portfolio_value=cash_balance + holdings_value,
    )


@app.route("/stocks")
def stocks():
    return render_template("stocks.html", stocks=get_live_stocks())


@app.route("/portfolio")
def portfolio():
    user_id = current_user_id()

    if not user_id:
        return login_required_redirect()

    cash_balance = get_cash_balance(user_id)
    holdings = get_holdings(user_id)

    holdings_value = sum(
        Decimal(str(holding["quantity"])) * Decimal(str(holding["current_price"]))
        for holding in holdings
    )

    total_portfolio_value = cash_balance + holdings_value

    return render_template(
        "portfolio.html",
        cash_balance=cash_balance,
        holdings=holdings,
        total_portfolio_value=total_portfolio_value,
    )


@app.route("/transactions")
def transactions():
    user_id = current_user_id()

    if not user_id:
        return login_required_redirect()

    transactions = get_transaction_history(user_id)

    return render_template(
        "transaction_history.html",
        transactions=transactions
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user_id():
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":
        try:
            user_id = verify_login(
                request.form.get("username"),
                request.form.get("password"),
            )
            session["user_id"] = user_id
            flash("Welcome back!", "success")
            return redirect(url_for("customer_dashboard"))
        except AuthError as error:
            flash(str(error), "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user_id():
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":
        try:
            user_id = create_user(
                request.form.get("first_name"),
                request.form.get("last_name"),
                request.form.get("username"),
                request.form.get("email"),
                request.form.get("password"),
                request.form.get("confirm_password"),
            )
            session["user_id"] = user_id
            flash("Your account is ready. Welcome to Athena Trading!", "success")
            return redirect(url_for("customer_dashboard"))
        except AuthError as error:
            flash(str(error), "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("login"))


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


@app.route("/balance", methods=["GET", "POST"])
def balance():
    user_id = current_user_id()
    if not user_id:
        return login_required_redirect()

    if request.method == "POST":
        action = request.form.get("action")
        account_id = request.form.get("linked_account_id", type=int)
        amount = request.form.get("amount")
        try:
            if action == "deposit":
                result = deposit(user_id, account_id, amount)
                flash(f"Deposited {usd(result['amount'])}. New balance {usd(result['balance_after'])}.", "success")
            elif action == "withdraw":
                result = withdraw(user_id, account_id, amount)
                flash(f"Withdrew {usd(result['amount'])}. New balance {usd(result['balance_after'])}.", "success")
            else:
                flash("Choose deposit or withdraw.", "error")
        except BankingError as error:
            flash(str(error), "error")
        return redirect(url_for("balance"))

    return render_template(
        "manage_balance.html",
        cash=get_cash_balance(user_id),
        accounts=get_linked_accounts(user_id),
    )


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
