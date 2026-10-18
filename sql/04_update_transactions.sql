-- Athena Trading System
-- Migration 04: Add linked account and balance tracking
-- Run only on databases that do not already have these changes.

ALTER TABLE transactions
    ADD COLUMN linked_account_id INT NULL,
    ADD COLUMN balance_after DECIMAL(10,2) NULL;

ALTER TABLE transactions
    ADD CONSTRAINT fk_transactions_linked_account
    FOREIGN KEY (linked_account_id)
    REFERENCES linked_accounts(linked_account_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;