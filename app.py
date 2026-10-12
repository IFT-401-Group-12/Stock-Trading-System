import os

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

app = Flask(__name__)


def get_db_connection():
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306))
    )

    return connection
    
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
def customer_dashboard():
    return render_template("customer_dashboard.html")


@app.route("/stocks")
def stocks():
    return render_template("stocks.html")


@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")


@app.route("/transactions")
def transactions():
    return render_template("transaction_history.html")
    
@app.route("/orders")
def current_orders():
    return render_template("current_orders.html")
    
@app.route("/login")
def login():
    return render_template("login.html")
    
@app.route("/signup")
def signup():
    return render_template("signup.html")


if __name__ == "__main__":
    app.run(debug=True)
    