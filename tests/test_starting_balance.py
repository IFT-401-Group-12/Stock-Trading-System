
import unittest
from unittest.mock import MagicMock, patch

from auth import create_user


class StartingBalanceTests(unittest.TestCase):

    @patch("auth.get_db_connection")
    def test_new_customer_receives_10000_and_demo_bank(self, mock_connection):
        connection = MagicMock()
        cursor = MagicMock()
        cursor.lastrowid = 42

        connection.cursor.return_value = cursor
        mock_connection.return_value = connection

        user_id = create_user(
            "Test",
            "Customer",
            "testcustomer",
            "test@example.com",
            "TestPassword123!",
            "TestPassword123!",
        )

        self.assertEqual(user_id, 42)

        # Registration should create a user and linked bank account.
        self.assertEqual(cursor.execute.call_count, 2)

        user_sql, user_params = cursor.execute.call_args_list[0].args
        self.assertIn("cash_balance", user_sql)
        self.assertEqual(user_params[-1], "10000.00")

        bank_sql, bank_params = cursor.execute.call_args_list[1].args
        self.assertIn("linked_accounts", bank_sql)
        self.assertEqual(bank_params[0], 42)
        self.assertEqual(bank_params[1], "Athena Demo Bank")
        self.assertEqual(bank_params[2], "Demo Checking")

        # Both records must be committed together.
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
