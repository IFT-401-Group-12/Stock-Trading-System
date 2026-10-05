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
    
@app.route("/login")
def login():
    return render_template("login.html")
    
@app.route("/signup")
def signup():
    return render_template("signup.html")


if __name__ == "__main__":
    app.run(debug=True)
    