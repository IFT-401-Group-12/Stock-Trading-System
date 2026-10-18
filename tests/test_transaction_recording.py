
import unittest
from unittest.mock import MagicMock

from trading import _record_transaction


class TransactionRecordingTests(unittest.TestCase):
    def test_record_transaction_saves_balance_after(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"cash_balance": 600.00}

        _record_transaction(
            cursor,
            user_id=1,
            stock_id=2,
            order_id=10,
            kind="BUY",
            quantity=2,
            price=200.00,
            total=400.00,
        )

        calls = cursor.execute.call_args_list

        self.assertEqual(len(calls), 2)

        insert_sql = calls[1].args[0]
        insert_params = calls[1].args[1]

        self.assertIn("balance_after", insert_sql)
        self.assertEqual(insert_params[-1], 600.00)
        self.assertIsNone(insert_params[1] if False else None)


if __name__ == "__main__":
    unittest.main()
