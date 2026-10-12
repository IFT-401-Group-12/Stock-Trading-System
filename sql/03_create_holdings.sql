-- =====================================================================
-- 03_create_holdings.sql
-- Holdings: how many shares of each stock each customer owns.
--
-- One row per (user, stock). The Buy/Sell trading code inserts the row
-- on a customer's first buy of a stock and updates it after that.
-- avg_cost is the customer's average price paid per share (cost basis),
-- used by the Portfolio and Sell Stock screens to show gain/loss.
--
-- Re-runnable: CREATE TABLE IF NOT EXISTS, no drops.
-- Run on EC2:  mysql stock_trading < 03_create_holdings.sql
-- =====================================================================

CREATE TABLE IF NOT EXISTS holdings (
    holding_id  INT            NOT NULL AUTO_INCREMENT,
    user_id     INT            NOT NULL,
    stock_id    INT            NOT NULL,
    quantity    INT            NOT NULL DEFAULT 0,
    avg_cost    DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    updated_at  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (holding_id),

    -- A customer has at most one holdings row per stock.
    UNIQUE KEY uq_holdings_user_stock (user_id, stock_id),
    KEY idx_holdings_stock (stock_id),

    CONSTRAINT fk_holdings_user  FOREIGN KEY (user_id)  REFERENCES users (user_id),
    CONSTRAINT fk_holdings_stock FOREIGN KEY (stock_id) REFERENCES stocks (stock_id),

    CONSTRAINT chk_holdings_quantity_nonneg CHECK (quantity >= 0),
    CONSTRAINT chk_holdings_avg_cost_nonneg CHECK (avg_cost >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
