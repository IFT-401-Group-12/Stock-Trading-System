-- =====================================================================
-- 05_backfill_demo_accounts.sql
-- One-time backfill for customers who registered BEFORE signup started
-- creating a demo bank account and $10,000 starting balance.
--
-- 1. Every user without a linked account gets the Athena Demo Bank
--    "Demo Checking" account, so Deposit/Withdraw works for them.
-- 2. Users who have never made a transaction (brand-new, untouched
--    accounts) get the $10,000 starting balance, recorded as an opening
--    DEPOSIT so Transaction History and balance_after stay consistent.
--    Users with existing activity keep their current balance; they can
--    deposit from the demo account if they need more cash.
--
-- Values match the constants in auth.py (STARTING_BALANCE, DEMO_*).
-- Re-runnable: each step skips users it has already handled.
-- Run on EC2:  mysql stock_trading < 05_backfill_demo_accounts.sql
-- =====================================================================

START TRANSACTION;

-- Step 1: demo bank account for anyone who has none.
INSERT INTO linked_accounts (user_id, bank_name, account_nickname, account_identifier)
SELECT u.user_id, 'Athena Demo Bank', 'Demo Checking', '****0000'
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM linked_accounts la WHERE la.user_id = u.user_id
);

-- Step 2: starting balance for users with no transactions yet.
CREATE TEMPORARY TABLE backfill_starting_balance AS
SELECT u.user_id,
       (SELECT MIN(la.linked_account_id)
          FROM linked_accounts la
         WHERE la.user_id = u.user_id) AS linked_account_id,
       u.cash_balance + 10000.00 AS new_balance
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM transactions t WHERE t.user_id = u.user_id
);

INSERT INTO transactions (user_id, transaction_type, total_amount, linked_account_id, balance_after)
SELECT user_id, 'DEPOSIT', 10000.00, linked_account_id, new_balance
FROM backfill_starting_balance;

UPDATE users u
JOIN backfill_starting_balance b ON b.user_id = u.user_id
SET u.cash_balance = b.new_balance;

-- Show what changed before it is committed.
SELECT COUNT(*) AS users_given_starting_balance FROM backfill_starting_balance;
SELECT COUNT(*) AS users_without_linked_account
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM linked_accounts la WHERE la.user_id = u.user_id);

DROP TEMPORARY TABLE backfill_starting_balance;

COMMIT;
