
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app import app


class PortfolioTests(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

        # Prevent background tasks and database access.
        self.patches = [
            patch("app.start_price_generator"),
            patch("app.current_user_id", return_value=1),
            patch("app.current_admin_id", return_value=None),
            patch("app.get_db_connection", return_value=MagicMock()),
            patch(
                "app.get_market_status",
                return_value=(True, "Market Open (testing)")
            ),
            patch(
                "app.get_cash_balance",
                return_value=Decimal("1000.00")
            ),
            patch(
                "app.get_holdings",
                return_value=[
                    {
                        "ticker_symbol": "AAPL",
                        "company_name": "Apple Inc.",
                        "quantity": 2,
                        "current_price": Decimal("200.00"),
                    }
                ]
            ),
        ]

        for mocked_function in self.patches:
            mocked_function.start()

    def tearDown(self):
        for mocked_function in reversed(self.patches):
            mocked_function.stop()

    def test_portfolio_displays_holdings_and_total(self):
        response = self.client.get("/portfolio")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("AAPL", html)
        self.assertIn("Apple Inc.", html)
        self.assertIn("<td>2</td>", html)
        self.assertIn("$1,000.00", html)
        self.assertIn("$400.00", html)
        self.assertIn("$1,400.00", html)

    def test_portfolio_displays_empty_holdings_message(self):
        with patch("app.get_holdings", return_value=[]):
            response = self.client.get("/portfolio")
            html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("You don't own any stocks yet.", html)


if __name__ == "__main__":
    unittest.main()
