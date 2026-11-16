
from unittest.mock import MagicMock, patch

from auth import create_user


def test_demo_bank_creation():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.lastrowid = 42

    with patch("auth.get_db_connection", return_value=connection):
        user_id = create_user(
            "Demo",
            "Customer",
            "demo_customer",
            "demo@example.com",
            "TestPassword123!",
            "TestPassword123!",
        )

    assert user_id == 42
    assert cursor.execute.call_count == 2

    first_query = cursor.execute.call_args_list[0]
    second_query = cursor.execute.call_args_list[1]

    assert "INSERT INTO users" in first_query.args[0]
    assert "INSERT INTO linked_accounts" in second_query.args[0]

    assert second_query.args[1] == (
        42,
        "Athena Demo Bank",
        "Demo Checking",
        "DEMO-CHECKING",
    )

    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()

    print("PASS: Customer and demo bank account created together.")

def test_demo_bank_failure():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.lastrowid = 42

    # Simulate the demo bank INSERT failing.
    cursor.execute.side_effect = [
        None,
        Exception("Simulated database error"),
    ]

    with patch("auth.get_db_connection", return_value=connection):
        try:
            create_user(
                "Demo",
                "Customer",
                "demo_customer",
                "demo@example.com",
                "TestPassword123!",
                "TestPassword123!",
            )
        except Exception as error:
            assert str(error) == "Simulated database error"
        else:
            raise AssertionError("Expected registration to fail")

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()

    print("PASS: Failed demo bank creation rolls back registration.")
    
if __name__ == "__main__":
    test_demo_bank_creation()
    test_demo_bank_failure()
