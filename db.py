"""Database connection shared by the Flask app, trading logic and price generator."""

import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    """Open a new connection to the RDS `stock_trading` database.

    Every connection runs in UTC (time_zone = '+00:00') so TIMESTAMP columns
    always mean the same thing; the app converts to Eastern time for display.
    """
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        ssl_ca=os.getenv("DB_SSL_CA") or None,
    )

    cursor = connection.cursor()
    cursor.execute("SET time_zone = '+00:00'")
    cursor.close()

    return connection
