"""Deposit and withdrawal of cash (Jasmine's Deposit/Withdrawal Function).

A customer moves money between a linked bank account and their in-app cash
balance. Matches the Deposit Cash and Withdraw Cash process maps:

* Deposit  - validate the amount, send a request to the bank/payment
             processor, and only credit cash once the bank approves.
* Withdraw - validate the amount, confirm the cash balance covers it, then
             debit cash.

Both record a row in transactions (transaction_type DEPOSIT or WITHDRAWAL)
with balance_after and the linked_account_id used, so Transaction History
shows the move. No stock, order, quantity or price is involved, so those
columns stay NULL.

The user row is locked (SELECT ... FOR UPDATE) for the whole operation so two
requests can't both read the same balance and double-spend it.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from db import get_db_connection

CENT = Decimal("0.01")


class BankingError(Exception):
    """A deposit or withdrawal was rejected. The message is safe to show the customer."""


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(raw):
    """Turn the form's amount string into a positive money value, or reject it."""
    try:
        amount = money(str(raw).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        raise BankingError("Enter a valid amount, like 500.00.")
    if amount <= 0:
        raise BankingError("Amount must be greater than $0.00.")
    if amount >= Decimal("100000000"):
        raise BankingError("Amount is too large.")
    return amount


def _lock_user(cursor, user_id):
    cursor.execute(
        "SELECT user_id, cash_balance FROM users WHERE user_id = %s FOR UPDATE",
        (user_id,),
    )
    user = cursor.fetchone()
    if not user:
        raise BankingError("Your account could not be found. Please log in again.")
    return user


def _get_linked_account(cursor, user_id, linked_account_id):
    """Confirm the chosen bank account exists and belongs to this user."""
    cursor.execute(
        "SELECT linked_account_id FROM linked_accounts "
        "WHERE linked_account_id = %s AND user_id = %s",
        (linked_account_id, user_id),
    )
    account = cursor.fetchone()
    if not account:
        raise BankingError("Choose one of your linked bank accounts.")
    return account["linked_account_id"]


def _record_cash_transaction(cursor, user_id, linked_account_id, kind, amount, balance_after):
    cursor.execute(
        "INSERT INTO transactions "
        "(user_id, transaction_type, total_amount, linked_account_id, balance_after) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, kind, amount, linked_account_id, balance_after),
    )


def _bank_approves(linked_account_id, amount):
    """Stand-in for the bank/payment processor's approve/decline decision.

    The deposit process map sends a request to the bank and waits for an
    approve or decline. There's no real processor in this project, so this
    always approves. It's a real step so the decline path can be exercised
    later by returning False.
    """
    return True


def deposit(user_id, linked_account_id, raw_amount):
    """Deposit cash from a linked bank account into the customer's cash balance."""
    amount = parse_amount(raw_amount)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        user = _lock_user(cursor, user_id)
        account_id = _get_linked_account(cursor, user_id, linked_account_id)

        # Deposit map: ask the bank first; only credit cash if it approves.
        if not _bank_approves(account_id, amount):
            raise BankingError("The bank declined the transaction. No funds were moved.")

        new_balance = money(user["cash_balance"] + amount)
        cursor.execute(
            "UPDATE users SET cash_balance = %s WHERE user_id = %s",
            (new_balance, user_id),
        )
        _record_cash_transaction(cursor, user_id, account_id, "DEPOSIT", amount, new_balance)

        connection.commit()

        return {"type": "DEPOSIT", "amount": amount, "balance_after": new_balance}

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def withdraw(user_id, linked_account_id, raw_amount):
    """Withdraw cash from the customer's cash balance to a linked bank account."""
    amount = parse_amount(raw_amount)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        user = _lock_user(cursor, user_id)
        account_id = _get_linked_account(cursor, user_id, linked_account_id)

        # Withdraw map: the cash balance must cover the amount.
        if amount > user["cash_balance"]:
            raise BankingError(
                f"Not enough cash. You asked to withdraw ${amount:,.2f} but have "
                f"${user['cash_balance']:,.2f} available."
            )

        new_balance = money(user["cash_balance"] - amount)
        cursor.execute(
            "UPDATE users SET cash_balance = %s WHERE user_id = %s",
            (new_balance, user_id),
        )
        _record_cash_transaction(cursor, user_id, account_id, "WITHDRAWAL", amount, new_balance)

        connection.commit()

        return {"type": "WITHDRAWAL", "amount": amount, "balance_after": new_balance}

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

def get_linked_accounts(user_id):
    """The customer's linked bank accounts, for the Manage Balance dropdown."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT linked_account_id, bank_name, account_nickname, account_identifier "
            "FROM linked_accounts WHERE user_id = %s ORDER BY linked_account_id",
            (user_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()