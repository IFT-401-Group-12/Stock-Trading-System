import unittest
from decimal import Decimal
from unittest.mock import patch

from auth import STARTING_BALANCE
from test_demo_bank import make_connection, sign_up


class StartingBalanceTests(unittest.TestCase):

    def test_starting_balance_is_10000(self):
        self.assertEqual(STARTING_BALANCE, Decimal("10000.00"))

    def test_new_customer_receives_starting_balance(self):
        connection, cursor = make_connection()

        with patch("auth.get_db_connection", return_value=connection):
            sign_up()

        # Registration creates the user, the demo bank account and an opening deposit.
        self.assertEqual(cursor.execute.call_count, 3)

        user_sql, user_params = cursor.execute.call_args_list[0].args
        self.assertIn("cash_balance", user_sql)
        self.assertEqual(user_params[-1], STARTING_BALANCE)

    def test_starting_balance_recorded_as_opening_deposit(self):
        connection, cursor = make_connection()

        with patch("auth.get_db_connection", return_value=connection):
            sign_up()

        deposit_sql, deposit_params = cursor.execute.call_args_list[2].args
        self.assertIn("INSERT INTO transactions", deposit_sql)
        # (user_id, type, total_amount, linked_account_id, balance_after)
        self.assertEqual(
            deposit_params,
            (42, "DEPOSIT", STARTING_BALANCE, 7, STARTING_BALANCE),
        )
        connection.commit.assert_called_once()

    def test_failed_opening_deposit_rolls_back_registration(self):
        connection, _ = make_connection(fail_on_call=3)

        with patch("auth.get_db_connection", return_value=connection):
            with self.assertRaises(Exception):
                sign_up()

        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
