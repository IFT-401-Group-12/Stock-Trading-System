"""Who is using the app right now: the logged-in customer and whether they are an admin.

Login and signup set session["user_id"] after checking the password. -tlboyd3 updated
"""

#tlboyd3 import os removed because it's no longer used.
from decimal import Decimal
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

# Every new customer starts with virtual cash and a fictional linked bank account so they can trade, deposit and withdraw right away.
STARTING_BALANCE = Decimal("10000.00")
DEMO_BANK_NAME = "Athena Demo Bank"
DEMO_ACCOUNT_NICKNAME = "Demo Checking"

# linked_accounts.account_identifier stores a masked value only
DEMO_ACCOUNT_IDENTIFIER = "****0000"

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
    if len(first_name) > 50 or len(last_name) > 50:
        raise AuthError("Name is too long.")
    if len(username) > 30:
        raise AuthError("Username must be 30 characters or fewer.")
    if len(email) > 255:
        raise AuthError("Email is too long.")
    password_hash = generate_password_hash(password)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO users "
            "(first_name, last_name, username, email, password_hash, cash_balance) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (first_name, last_name, username, email, password_hash, STARTING_BALANCE),
        )

        # Get the ID of the newly registered customer.
        user_id = cursor.lastrowid

        # Automatically link a fictional demo bank account.
        cursor.execute(
            "INSERT INTO linked_accounts "
            "(user_id, bank_name, account_nickname, account_identifier) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, DEMO_BANK_NAME, DEMO_ACCOUNT_NICKNAME, DEMO_ACCOUNT_IDENTIFIER),
        )
        linked_account_id = cursor.lastrowid

        # Record the starting balance as an opening deposit from the demo bank, so Transaction History shows where the money came from and balance_after lines up with later transactions.
        cursor.execute(
            "INSERT INTO transactions "
            "(user_id, transaction_type, total_amount, linked_account_id, balance_after) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user_id, "DEPOSIT", STARTING_BALANCE, linked_account_id, STARTING_BALANCE),
        )

        # Save the customer, bank account and opening deposit together.
        connection.commit()
        return user_id

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
