"""Buy / Sell / Cancel order logic.

Two kinds of orders:

* Market order  - fills right away at the stock's current price.
* Limit order   - the customer names a price. A limit BUY fills once the price
                  drops to that limit or lower; a limit SELL fills once the
                  price rises to that limit or higher. If the price is already
                  there when the order is placed, it fills immediately.
                  Otherwise it is saved as PENDING and the price generator
                  fills it later (see fill_pending_orders). Pending orders can
                  be cancelled.

While a limit order is pending, what it needs is held so it can't be spent twice:
* pending BUY  -> cash (limit price x quantity) is taken out of cash_balance,
                  and the shares are taken out of the stock's volume_available.
* pending SELL -> the shares are taken out of the customer's holdings.
Cancelling gives them back; filling uses them.

Table usage (matches the live RDS schema):
* orders.price        - the limit price while PENDING; the price it actually
                        traded at once EXECUTED.
* transactions        - one row per executed BUY/SELL, and one CANCELLED row
                        per cancelled order. A pending order has no transaction.

Locking: every function locks rows in the same order -
users -> stocks -> orders -> holdings - so two requests touching the same rows
wait for each other instead of deadlocking.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from db import get_db_connection
from market import get_market_status

CENT = Decimal("0.01")


class TradeError(Exception):
    """A trade was rejected. The message is safe to show to the customer."""


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------

def parse_quantity(raw):
    try:
        quantity = int(str(raw).strip())
    except (TypeError, ValueError):
        raise TradeError("Enter a whole number of shares.")
    if quantity <= 0:
        raise TradeError("Quantity must be at least 1 share.")
    if quantity > 1_000_000:
        raise TradeError("Quantity is too large.")
    return quantity


def parse_limit_price(raw):
    try:
        price = money(str(raw).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        raise TradeError("Enter a valid limit price, like 185.00.")
    if price <= 0:
        raise TradeError("Limit price must be greater than $0.00.")
    if price >= Decimal("100000000"):
        raise TradeError("Limit price is too large.")
    return price


# ---------------------------------------------------------------------------
# Row locking helpers (SELECT ... FOR UPDATE)
# ---------------------------------------------------------------------------

def _lock_user(cursor, user_id):
    cursor.execute(
        "SELECT user_id, cash_balance FROM users WHERE user_id = %s FOR UPDATE",
        (user_id,),
    )
    user = cursor.fetchone()
    if not user:
        raise TradeError("Your account could not be found. Please log in again.")
    return user


def _lock_stock(cursor, stock_id):
    cursor.execute(
        "SELECT stock_id, ticker_symbol, company_name, current_price, "
        "volume_available, status FROM stocks WHERE stock_id = %s FOR UPDATE",
        (stock_id,),
    )
    stock = cursor.fetchone()
    if not stock:
        raise TradeError("That stock could not be found.")
    return stock


def _lock_holding(cursor, user_id, stock_id):
    cursor.execute(
        "SELECT holding_id, quantity, avg_cost FROM holdings "
        "WHERE user_id = %s AND stock_id = %s FOR UPDATE",
        (user_id, stock_id),
    )
    return cursor.fetchone()


def _add_shares(cursor, user_id, stock_id, quantity, price_paid):
    """Add shares to holdings and update the average cost per share."""
    holding = _lock_holding(cursor, user_id, stock_id)

    if holding is None:
        cursor.execute(
            "INSERT INTO holdings (user_id, stock_id, quantity, avg_cost) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, stock_id, quantity, money(price_paid)),
        )
        return

    old_qty = holding["quantity"]
    new_qty = old_qty + quantity
    new_avg = money((old_qty * holding["avg_cost"] + quantity * price_paid) / new_qty)

    cursor.execute(
        "UPDATE holdings SET quantity = %s, avg_cost = %s WHERE holding_id = %s",
        (new_qty, new_avg, holding["holding_id"]),
    )


def _return_shares(cursor, user_id, stock_id, quantity):
    """Put held shares back (cancelled limit SELL). Average cost is unchanged."""
    cursor.execute(
        "UPDATE holdings SET quantity = quantity + %s "
        "WHERE user_id = %s AND stock_id = %s",
        (quantity, user_id, stock_id),
    )


def _record_transaction(cursor, user_id, stock_id, order_id, kind, quantity, price, total):
    cursor.execute(
        "INSERT INTO transactions "
        "(user_id, stock_id, order_id, transaction_type, quantity, price, total_amount) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, stock_id, order_id, kind, quantity, price, total),
    )


def _require_market_open(connection):
    is_open, message = get_market_status(connection)
    if not is_open:
        raise TradeError(f"Orders can only be placed or cancelled while the market is open. {message}.")


# ---------------------------------------------------------------------------
# Buy
# ---------------------------------------------------------------------------

def place_buy_order(user_id, stock_id, quantity, order_kind="market", limit_price=None):
    """Place a market or limit BUY. Returns a summary dict for the confirmation."""
    quantity = parse_quantity(quantity)
    is_limit = order_kind == "limit"
    if is_limit:
        limit_price = parse_limit_price(limit_price)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _require_market_open(connection)

        user = _lock_user(cursor, user_id)
        stock = _lock_stock(cursor, stock_id)

        if stock["status"] != "live":
            raise TradeError(f"{stock['ticker_symbol']} is halted and can't be traded right now.")

        if quantity > stock["volume_available"]:
            raise TradeError(
                f"Only {stock['volume_available']:,} shares of "
                f"{stock['ticker_symbol']} are available to buy."
            )

        current_price = stock["current_price"]
        fills_now = (not is_limit) or current_price <= limit_price

        # Fill now: pay today's price. Pending: hold cash at the limit price.
        price = current_price if fills_now else limit_price
        total = money(price * quantity)

        if total > user["cash_balance"]:
            raise TradeError(
                f"Not enough cash. This order needs ${total:,.2f} and you have "
                f"${user['cash_balance']:,.2f} available."
            )

        cursor.execute(
            "UPDATE users SET cash_balance = cash_balance - %s WHERE user_id = %s",
            (total, user_id),
        )
        cursor.execute(
            "UPDATE stocks SET volume_available = volume_available - %s WHERE stock_id = %s",
            (quantity, stock_id),
        )

        if fills_now:
            cursor.execute(
                "INSERT INTO orders (user_id, stock_id, order_type, quantity, price, status, executed_at) "
                "VALUES (%s, %s, 'BUY', %s, %s, 'EXECUTED', UTC_TIMESTAMP())",
                (user_id, stock_id, quantity, price),
            )
            order_id = cursor.lastrowid
            _add_shares(cursor, user_id, stock_id, quantity, price)
            _record_transaction(cursor, user_id, stock_id, order_id, "BUY", quantity, price, total)
        else:
            cursor.execute(
                "INSERT INTO orders (user_id, stock_id, order_type, quantity, price, status) "
                "VALUES (%s, %s, 'BUY', %s, %s, 'PENDING')",
                (user_id, stock_id, quantity, price),
            )
            order_id = cursor.lastrowid

        connection.commit()

        return {
            "order_id": order_id,
            "side": "BUY",
            "ticker": stock["ticker_symbol"],
            "quantity": quantity,
            "price": price,
            "total": total,
            "status": "EXECUTED" if fills_now else "PENDING",
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


# ---------------------------------------------------------------------------
# Sell
# ---------------------------------------------------------------------------

def place_sell_order(user_id, stock_id, quantity, order_kind="market", limit_price=None):
    """Place a market or limit SELL. Returns a summary dict for the confirmation."""
    quantity = parse_quantity(quantity)
    is_limit = order_kind == "limit"
    if is_limit:
        limit_price = parse_limit_price(limit_price)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _require_market_open(connection)

        _lock_user(cursor, user_id)
        stock = _lock_stock(cursor, stock_id)

        if stock["status"] != "live":
            raise TradeError(f"{stock['ticker_symbol']} is halted and can't be traded right now.")

        holding = _lock_holding(cursor, user_id, stock_id)
        owned = holding["quantity"] if holding else 0

        if quantity > owned:
            raise TradeError(
                f"You only have {owned:,} share{'s' if owned != 1 else ''} of "
                f"{stock['ticker_symbol']} available to sell."
            )

        current_price = stock["current_price"]
        fills_now = (not is_limit) or current_price >= limit_price
        price = current_price if fills_now else limit_price
        total = money(price * quantity)

        # Take the shares out of holdings either way: sold now, or held for the pending order.
        cursor.execute(
            "UPDATE holdings SET quantity = quantity - %s WHERE holding_id = %s",
            (quantity, holding["holding_id"]),
        )

        if fills_now:
            cursor.execute(
                "UPDATE users SET cash_balance = cash_balance + %s WHERE user_id = %s",
                (total, user_id),
            )
            cursor.execute(
                "UPDATE stocks SET volume_available = volume_available + %s WHERE stock_id = %s",
                (quantity, stock_id),
            )
            cursor.execute(
                "INSERT INTO orders (user_id, stock_id, order_type, quantity, price, status, executed_at) "
                "VALUES (%s, %s, 'SELL', %s, %s, 'EXECUTED', UTC_TIMESTAMP())",
                (user_id, stock_id, quantity, price),
            )
            order_id = cursor.lastrowid
            _record_transaction(cursor, user_id, stock_id, order_id, "SELL", quantity, price, total)
        else:
            cursor.execute(
                "INSERT INTO orders (user_id, stock_id, order_type, quantity, price, status) "
                "VALUES (%s, %s, 'SELL', %s, %s, 'PENDING')",
                (user_id, stock_id, quantity, price),
            )
            order_id = cursor.lastrowid

        connection.commit()

        return {
            "order_id": order_id,
            "side": "SELL",
            "ticker": stock["ticker_symbol"],
            "quantity": quantity,
            "price": price,
            "total": total,
            "status": "EXECUTED" if fills_now else "PENDING",
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def cancel_order(user_id, order_id):
    """Cancel one of the customer's PENDING orders and release what it was holding."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _require_market_open(connection)

        # Peek (no lock) to learn the stock, so rows can be locked in the standard order.
        cursor.execute(
            "SELECT stock_id FROM orders WHERE order_id = %s AND user_id = %s",
            (order_id, user_id),
        )
        found = cursor.fetchone()
        if not found:
            raise TradeError("That order could not be found on your account.")

        _lock_user(cursor, user_id)
        stock = _lock_stock(cursor, found["stock_id"])

        cursor.execute(
            "SELECT order_id, order_type, quantity, price, status FROM orders "
            "WHERE order_id = %s AND user_id = %s FOR UPDATE",
            (order_id, user_id),
        )
        order = cursor.fetchone()

        if order["status"] != "PENDING":
            raise TradeError(
                f"Order #{order_id} is already {order['status'].lower()} and can't be cancelled."
            )

        quantity = order["quantity"]
        held_amount = money(order["price"] * quantity)

        if order["order_type"] == "BUY":
            cursor.execute(
                "UPDATE users SET cash_balance = cash_balance + %s WHERE user_id = %s",
                (held_amount, user_id),
            )
            cursor.execute(
                "UPDATE stocks SET volume_available = volume_available + %s WHERE stock_id = %s",
                (quantity, stock["stock_id"]),
            )
        else:
            _return_shares(cursor, user_id, stock["stock_id"], quantity)

        cursor.execute(
            "UPDATE orders SET status = 'CANCELLED' WHERE order_id = %s",
            (order_id,),
        )
        _record_transaction(
            cursor, user_id, stock["stock_id"], order_id, "CANCELLED",
            quantity, order["price"], held_amount,
        )

        connection.commit()

        return {
            "order_id": order_id,
            "side": order["order_type"],
            "ticker": stock["ticker_symbol"],
            "quantity": quantity,
            "price": order["price"],
            "total": held_amount,
            "status": "CANCELLED",
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


# ---------------------------------------------------------------------------
# Filling pending limit orders (called by the price generator after each tick)
# ---------------------------------------------------------------------------

def fill_pending_orders(connection):
    """Fill every PENDING limit order whose price has been reached.

    Returns the number of orders filled. Each order is its own transaction,
    so one bad order can't block the rest.
    """
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT o.order_id, o.user_id, o.stock_id FROM orders o "
        "JOIN stocks s ON s.stock_id = o.stock_id "
        "WHERE o.status = 'PENDING' AND s.status = 'live' AND ("
        "  (o.order_type = 'BUY'  AND s.current_price <= o.price) OR "
        "  (o.order_type = 'SELL' AND s.current_price >= o.price)"
        ") ORDER BY o.created_at, o.order_id"
    )
    candidates = cursor.fetchall()
    connection.commit()  # end the read so each fill starts fresh

    filled = 0
    for candidate in candidates:
        try:
            if _fill_one(cursor, candidate):
                connection.commit()
                filled += 1
            else:
                connection.rollback()
        except Exception as error:  # keep going; log and move on
            connection.rollback()
            print(f"[price-generator] could not fill order #{candidate['order_id']}: {error}")

    cursor.close()
    return filled


def _fill_one(cursor, candidate):
    user_id = candidate["user_id"]
    order_id = candidate["order_id"]

    _lock_user(cursor, user_id)
    stock = _lock_stock(cursor, candidate["stock_id"])

    cursor.execute(
        "SELECT order_type, quantity, price, status FROM orders WHERE order_id = %s FOR UPDATE",
        (order_id,),
    )
    order = cursor.fetchone()

    # Re-check under lock: it may have been cancelled, or the price moved back.
    if order["status"] != "PENDING" or stock["status"] != "live":
        return False

    limit_price = order["price"]
    fill_price = stock["current_price"]
    quantity = order["quantity"]
    total = money(fill_price * quantity)

    if order["order_type"] == "BUY":
        if fill_price > limit_price:
            return False
        # Cash was held at the limit price; refund the difference if it filled cheaper.
        refund = money(limit_price * quantity) - total
        if refund > 0:
            cursor.execute(
                "UPDATE users SET cash_balance = cash_balance + %s WHERE user_id = %s",
                (refund, user_id),
            )
        _add_shares(cursor, user_id, stock["stock_id"], quantity, fill_price)
    else:
        if fill_price < limit_price:
            return False
        cursor.execute(
            "UPDATE users SET cash_balance = cash_balance + %s WHERE user_id = %s",
            (total, user_id),
        )
        cursor.execute(
            "UPDATE stocks SET volume_available = volume_available + %s WHERE stock_id = %s",
            (quantity, stock["stock_id"]),
        )

    cursor.execute(
        "UPDATE orders SET status = 'EXECUTED', price = %s, executed_at = UTC_TIMESTAMP() "
        "WHERE order_id = %s",
        (fill_price, order_id),
    )
    _record_transaction(
        cursor, user_id, stock["stock_id"], order_id, order["order_type"],
        quantity, fill_price, total,
    )
    return True


# ---------------------------------------------------------------------------
# Read-only helpers for the pages
# ---------------------------------------------------------------------------

def _fetch_all(sql, params=()):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def get_live_stocks():
    return _fetch_all(
        "SELECT stock_id, ticker_symbol, company_name, current_price, open_price, "
        "day_high, day_low, volume_available, status "
        "FROM stocks ORDER BY ticker_symbol"
    )


def get_cash_balance(user_id):
    rows = _fetch_all("SELECT cash_balance FROM users WHERE user_id = %s", (user_id,))
    return rows[0]["cash_balance"] if rows else Decimal("0.00")


def get_holdings(user_id):
    return _fetch_all(
        "SELECT h.stock_id, s.ticker_symbol, s.company_name, h.quantity, h.avg_cost, "
        "s.current_price, s.status "
        "FROM holdings h JOIN stocks s ON s.stock_id = h.stock_id "
        "WHERE h.user_id = %s AND h.quantity > 0 ORDER BY s.ticker_symbol",
        (user_id,),
    )


def get_orders(user_id, status=None, limit=50):
    sql = (
        "SELECT o.order_id, o.order_type, o.quantity, o.price, o.status, "
        "o.created_at, o.executed_at, s.ticker_symbol, s.company_name, s.current_price "
        "FROM orders o JOIN stocks s ON s.stock_id = o.stock_id WHERE o.user_id = %s"
    )
    params = [user_id]
    if status:
        sql += " AND o.status = %s"
        params.append(status)
    else:
        sql += " AND o.status <> 'PENDING'"
    sql += " ORDER BY o.created_at DESC, o.order_id DESC LIMIT %s"
    params.append(limit)
    return _fetch_all(sql, tuple(params))
