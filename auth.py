"""Who is using the app right now: the logged-in customer and whether they are an admin.

Login and signup set session["user_id"] after checking the password. -tlboyd3 updated
"""

#tlboyd3 import os removed because it's no longer used.

from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db_connection


def current_user_id():
    user_id = session.get("user_id")
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

class AuthError(Exception):
    """A login or signup problem. The message is safe to show the user."""


def create_user(first_name, last_name, username, email, password, confirm_password):
    """Create a new customer account with a securely hashed password."""
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    username = (username or "").strip()
    email = (email or "").strip().lower()

    if not all([first_name, last_name, username, email, password]):
        raise AuthError("Please fill in every field.")
    if password != confirm_password:
        raise AuthError("The passwords don't match.")
    if len(password) < 8:
        raise AuthError("Your password must be at least 8 characters.")

    password_hash = generate_password_hash(password)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (first_name, last_name, username, email, password_hash) "
            "VALUES (%s, %s, %s, %s, %s)",
            (first_name, last_name, username, email, password_hash),
        )
        connection.commit()
        return cursor.lastrowid
    except Exception as error:
        connection.rollback()
        # 1062 = duplicate entry on the UNIQUE username or email column.
        if getattr(error, "errno", None) == 1062:
            raise AuthError("That username or email is already taken.")
        raise
    finally:
        cursor.close()
        connection.close()


def verify_login(identifier, password):
    """Check a username-or-email plus password. Returns the user_id, or raises."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        raise AuthError("Enter your username and password.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, password_hash FROM users "
            "WHERE username = %s OR email = %s",
            (identifier, identifier.lower()),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    if not user or not check_password_hash(user["password_hash"], password):
        # Same message whether the user doesn't exist or the password is wrong,
        # so an attacker can't tell which usernames are real.
        raise AuthError("Incorrect username or password.")

    return user["user_id"]
