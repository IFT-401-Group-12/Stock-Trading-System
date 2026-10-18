"""Who is using the app right now: the logged-in customer and whether they are an admin.

Login should set session["user_id"] after checking the password. Until login
is wired up, set DEV_USER_ID in .env to test as that user.
"""

import os

from flask import session

from db import get_db_connection


def current_user_id():
    user_id = session.get("user_id") or os.getenv("DEV_USER_ID")
    return int(user_id) if user_id else None


def current_admin_id():
    """The admins.admin_id for the current user, or None if they aren't an admin.

    The admins table is the authoritative record of who is an admin (per the
    ERD); users.admin_access is only a convenience flag.
    """
    user_id = current_user_id()
    if not user_id:
        return None

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT admin_id FROM admins WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()
        connection.close()
