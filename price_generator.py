"""Random Stock Price Generator.

A background thread inside the Flask app. While the market is open it nudges
every live stock's price up or down a small random amount every few seconds,
so prices drift gradually the way a real ticker does instead of jumping around.

Each tick:
  1. Checks the market is open (same schedule/holiday rules as trading).
  2. On the first tick of a trading day, sets each stock's open_price,
     day_high and day_low to its current price.
  3. Moves each live stock's current_price by a random % change, and keeps
     day_high / day_low up to date.
  4. Every PRICE_HISTORY_SECONDS, logs each price to stock_price_history.
  5. Fills any pending limit orders the new prices have reached.

New stocks an admin creates are picked up automatically on the next tick.

Settings (.env, all optional):
  PRICE_GENERATOR_ENABLED=0     turn the generator off for this process
  PRICE_TICK_SECONDS=5          how often prices move
  PRICE_VOLATILITY=0.003        typical % move per tick (0.003 = 0.3%)
  PRICE_HISTORY_SECONDS=60      how often prices are logged to history

Only one generator runs at a time, even with several app processes (gunicorn
workers or Flask's debug reloader): each one asks MySQL for a named lock, and
only the process holding it moves prices.
"""

import os
import random
import threading
import time
from decimal import Decimal

from db import get_db_connection
from market import get_market_status, now_eastern, start_of_today_utc
from trading import fill_pending_orders, money

LOCK_NAME = "athena_price_generator"
MIN_PRICE = Decimal("1.00")
MAX_MOVE = 0.02          # never move more than 2% in one tick
PULL_TO_OPEN = 0.005     # gentle pull back toward the day's open, so prices wander but don't run away


def next_price(current, open_price, volatility):
    """Pick the next price: a small random % move, nudged slightly toward the open."""
    current_f = float(current)
    change = random.gauss(0, volatility)

    if open_price:
        change += PULL_TO_OPEN * (float(open_price) - current_f) / current_f

    change = max(-MAX_MOVE, min(MAX_MOVE, change))
    return max(MIN_PRICE, money(current_f * (1 + change)))


class PriceGenerator(threading.Thread):

    def __init__(self):
        super().__init__(name="price-generator", daemon=True)
        self.tick_seconds = float(os.getenv("PRICE_TICK_SECONDS", "5"))
        self.volatility = float(os.getenv("PRICE_VOLATILITY", "0.003"))
        self.history_seconds = float(os.getenv("PRICE_HISTORY_SECONDS", "60"))

        self._stop_event = threading.Event()
        self._lock_connection = None
        self._session_date = None      # the trading day we've already "opened"
        self._last_history = 0.0

    # -- single-instance lock ------------------------------------------------

    def _holds_lock(self):
        """True if this process holds the MySQL lock (taking it if it's free)."""
        try:
            if self._lock_connection is not None:
                cursor = self._lock_connection.cursor()
                cursor.execute("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (LOCK_NAME,))
                (mine,) = cursor.fetchone()
                cursor.close()
                if mine:
                    return True
                self._lock_connection.close()
                self._lock_connection = None

            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT GET_LOCK(%s, 0)", (LOCK_NAME,))
            (got_it,) = cursor.fetchone()
            cursor.close()

            if got_it == 1:
                self._lock_connection = connection
                print("[price-generator] running in this process")
                return True

            connection.close()
            return False

        except Exception as error:
            print(f"[price-generator] lock check failed: {error}")
            self._lock_connection = None
            return False

    # -- main loop -------------------------------------------------------------

    def run(self):
        print(
            f"[price-generator] started: tick every {self.tick_seconds:g}s, "
            f"volatility {self.volatility:.2%}, history every {self.history_seconds:g}s"
        )
        while not self._stop_event.is_set():
            if self._holds_lock():
                try:
                    self.tick()
                except Exception as error:
                    print(f"[price-generator] tick failed: {error}")
            self._stop_event.wait(self.tick_seconds)

        # Stopping: release the lock so another process can take over.
        if self._lock_connection is not None:
            try:
                self._lock_connection.close()
            except Exception:
                pass
            self._lock_connection = None

    def stop(self):
        self._stop_event.set()

    def tick(self):
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            is_open, _ = get_market_status(connection)
            if not is_open:
                return

            today = now_eastern().date()
            if self._session_date != today:
                self._open_trading_day(cursor)
                self._session_date = today

            cursor.execute(
                "SELECT stock_id, current_price, open_price FROM stocks WHERE status = 'live'"
            )
            stocks = cursor.fetchall()

            log_history = time.monotonic() - self._last_history >= self.history_seconds

            for stock in stocks:
                price = next_price(stock["current_price"], stock["open_price"], self.volatility)
                cursor.execute(
                    "UPDATE stocks SET current_price = %s, "
                    "day_high = GREATEST(COALESCE(day_high, %s), %s), "
                    "day_low  = LEAST(COALESCE(day_low, %s), %s) "
                    "WHERE stock_id = %s",
                    (price, price, price, price, price, stock["stock_id"]),
                )
                if log_history:
                    cursor.execute(
                        "INSERT INTO stock_price_history (stock_id, price) VALUES (%s, %s)",
                        (stock["stock_id"], price),
                    )

            connection.commit()
            if log_history:
                self._last_history = time.monotonic()

            fill_pending_orders(connection)

        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def _open_trading_day(self, cursor):
        """First tick of the day: today's open, high and low start at the current price.

        If prices were already logged today (e.g. the app restarted mid-day),
        the day was already opened, so leave open/high/low alone.
        """
        cursor.execute(
            "SELECT COUNT(*) AS n FROM stock_price_history WHERE recorded_at >= %s",
            (start_of_today_utc(),),
        )
        if cursor.fetchone()["n"] > 0:
            return

        cursor.execute(
            "UPDATE stocks SET open_price = current_price, "
            "day_high = current_price, day_low = current_price"
        )
        cursor.execute(
            "INSERT INTO stock_price_history (stock_id, price) "
            "SELECT stock_id, current_price FROM stocks"
        )
        self._last_history = time.monotonic()
        print(f"[price-generator] opened trading day {now_eastern().date()}")


_generator = None


def start_price_generator():
    """Start the background generator once per process (safe to call more than once)."""
    global _generator

    if os.getenv("PRICE_GENERATOR_ENABLED", "1") == "0":
        print("[price-generator] disabled (PRICE_GENERATOR_ENABLED=0)")
        return None

    if _generator is None or not _generator.is_alive():
        _generator = PriceGenerator()
        _generator.start()

    return _generator
