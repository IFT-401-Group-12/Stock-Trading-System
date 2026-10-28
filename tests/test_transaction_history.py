import unittest

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import os
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret") #tlboyd3 added .env so secret key tests pass.

from app import app


class TransactionHistoryTests(unittest.TestCase):
    def test_transaction_history_displays_balance_after(self):
        sample_transactions = [{
            "transaction_id": 1,
            "created_at": datetime(2026, 10, 12),
            "transaction_type": "BUY",
            "ticker_symbol": "AAPL",
            "quantity": 2,
            "price": Decimal("200.00"),
            "total_amount": Decimal("400.00"),
            "linked_account_id": None,
            "balance_after": Decimal("600.00"),
            "status": "COMPLETED",
        }]

        with patch("app.current_user_id", return_value=1), \
             patch("app.get_transaction_history",
                   return_value=sample_transactions):
            response = app.test_client().get("/transactions")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Balance After", response.data)
        self.assertIn(b"$600.00", response.data)
        self.assertIn(b"AAPL", response.data)

    def test_transaction_history_handles_missing_balance(self):
        sample_transactions = [{
            "transaction_id": 2,
            "created_at": datetime(2026, 10, 12),
            "transaction_type": "SELL",
            "ticker_symbol": "AAPL",
            "quantity": 1,
            "price": Decimal("210.00"),
            "total_amount": Decimal("210.00"),
            "linked_account_id": None,
            "balance_after": None,
            "status": "COMPLETED",
        }]

        with patch("app.current_user_id", return_value=1), \
             patch("app.get_transaction_history",
                   return_value=sample_transactions):
            response = app.test_client().get("/transactions")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AAPL", response.data)
        self.assertIn(b"Balance After", response.data)
        self.assertIn(b"$210.00", response.data)

