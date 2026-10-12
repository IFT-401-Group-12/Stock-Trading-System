# Stock-Trading-System
Simulated stock trading system for IFT 401 Capstone. Web app with customer and admin functions, AWS backend, and a random stock price generator.

## Running the app

```bash
pip install flask python-dotenv mysql-connector-python
cp .env.example .env      # then fill in DB_PASSWORD, FLASK_SECRET_KEY, etc.
flask --app app run --host 0.0.0.0 --port 5000
```

One-time database setup (on the EC2 server):

```bash
mysql stock_trading < sql/03_create_holdings.sql
```

The market is closed until `market_schedule` has rows (run the seed script that
creates the first admin and the Mon–Fri 9:30–4:00 schedule), or set
`MARKET_ALWAYS_OPEN=1` in `.env` while testing.

## Buy / Sell and the price generator

| File | What it does |
|---|---|
| `trading.py` | Buy, sell and cancel logic. Market orders fill immediately; limit orders wait as `PENDING` and fill when the price reaches them. |
| `price_generator.py` | Random Stock Price Generator: a background thread that moves every live stock's price a small random amount every few seconds while the market is open, tracks the day's open/high/low, logs prices to `stock_price_history`, and fills pending limit orders. |
| `market.py` | Market-hours gate (weekly schedule + holidays, Eastern time) used by trading and the generator. |
| `db.py` | Shared database connection. |
| `templates/buy.html`, `sell.html`, `orders.html` | Buy, Sell and Orders (open orders + cancel) pages. |
| `static/js/live_prices.js` | Refreshes prices on the Stocks/Buy/Sell pages every 5 seconds. |

**Who is logged in:** trading pages use `session["user_id"]`. When the login page
checks a password, it should set `session["user_id"] = user["user_id"]`. Until
then, set `DEV_USER_ID` in `.env` to test as a specific user.

**What a pending limit order holds:** a pending buy sets aside its cash (limit
price × shares) and the shares from `stocks.volume_available`; a pending sell sets
aside the customer's shares from `holdings`. Cancelling returns them; filling
uses them (a buy that fills below its limit gets the difference back).

**Rules followed from the process map:** buy, sell and cancel all require the
market to be open; every executed order and every cancellation writes a
`transactions` row; pending orders don't.

**The price generator starts on the first page request** and only one copy ever
runs, even with several app processes (it holds a MySQL named lock). It only
moves prices while the market is open.
