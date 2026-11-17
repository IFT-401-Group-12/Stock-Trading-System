import unittest
from unittest.mock import MagicMock, patch

from auth import (
    DEMO_ACCOUNT_IDENTIFIER,
    DEMO_ACCOUNT_NICKNAME,
    DEMO_BANK_NAME,
    create_user,
)


def make_connection(fail_on_call=None):
    """A fake DB connection whose cursor hands out IDs like MySQL would.

    The users insert gets user_id 42 and the linked_accounts insert gets
    linked_account_id 7. If fail_on_call is set, that execute() call raises.
    """
    connection = MagicMock()
    cursor = connection.cursor.return_value
    ids = {"INSERT INTO users": 42, "INSERT INTO linked_accounts": 7}
    calls = {"count": 0}

    def fake_execute(sql, params=None):
        calls["count"] += 1
        if calls["count"] == fail_on_call:
            raise Exception("Simulated database error")
        for prefix, new_id in ids.items():
            if sql.startswith(prefix):
                cursor.lastrowid = new_id

    cursor.execute.side_effect = fake_execute
    return connection, cursor


def sign_up():
    return create_user(
        "Demo",
        "Customer",
        "demo_customer",
        "demo@example.com",
        "TestPassword123!",
        "TestPassword123!",
    )


class DemoBankAccountTests(unittest.TestCase):

    def test_signup_creates_demo_bank_account(self):
        connection, cursor = make_connection()

        with patch("auth.get_db_connection", return_value=connection):
            user_id = sign_up()

        self.assertEqual(user_id, 42)

        bank_sql, bank_params = cursor.execute.call_args_list[1].args
        self.assertIn("INSERT INTO linked_accounts", bank_sql)
        self.assertEqual(
            bank_params,
            (42, DEMO_BANK_NAME, DEMO_ACCOUNT_NICKNAME, DEMO_ACCOUNT_IDENTIFIER),
        )
        # Matches the schema convention of storing a masked identifier.
        self.assertTrue(DEMO_ACCOUNT_IDENTIFIER.startswith("****"))

        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_failed_demo_bank_insert_rolls_back_registration(self):
        # Call 1 = users insert succeeds, call 2 = linked_accounts insert fails.
        connection, cursor = make_connection(fail_on_call=2)

        with patch("auth.get_db_connection", return_value=connection):
            with self.assertRaisesRegex(Exception, "Simulated database error"):
                sign_up()

        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
