"""Stock creation (Sarah's Develop Stock Creation Function).

Moved here unchanged from app.py so the admin pages can use it without a
circular import. app.py still imports it, so app.create_stock keeps working.
"""

from db import get_db_connection


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
