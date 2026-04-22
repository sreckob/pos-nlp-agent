-- ============================================================
--  POS Payment Transaction System — Database Schema
--  Natural Language Prompt Agent Project
--  Card brands: VISA, MASTERCARD, AMEX, DINACARD, UNIONPAY
-- ============================================================

DROP TABLE IF EXISTS transactions;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE transactions (

    -- Identity
    transaction_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Timing
    transaction_date    TIMESTAMP       NOT NULL,

    -- Amount
    amount              NUMERIC(12, 2)  NOT NULL,
    currency            VARCHAR(3)      NOT NULL,
    -- RSD, EUR, USD

    -- Outcome
    status              VARCHAR(20)     NOT NULL,
    -- APPROVED, DECLINED, REVERSED, PENDING
    response_code       VARCHAR(4)      NOT NULL,
    -- ISO 8583: 00=approved, 51=insuf.funds, 05=do not honour,
    --           14=invalid card, 91=issuer unavail, 57=not permitted,
    --           41=lost card, 43=stolen card, 61=exceeds limit
    approval_code       VARCHAR(6),
    -- 6-char alphanumeric, NULL when not approved

    -- Card details
    pan_masked          VARCHAR(19)     NOT NULL,
    -- Visa/MC/Dina/UP: 411111******1111 (16 digits)
    -- Amex:            3714 ****** 61234 (15 digits)
    card_brand          VARCHAR(20)     NOT NULL,
    -- VISA, MASTERCARD, AMEX, DINACARD, UNIONPAY
    card_type           VARCHAR(20)     NOT NULL,
    -- CHIP, CONTACTLESS, MAGNETIC, MANUAL
    card_class          VARCHAR(20)     NOT NULL,
    -- DEBIT, CREDIT, PREPAID, CORPORATE

    -- Terminal & Merchant
    terminal_id         VARCHAR(20)     NOT NULL,
    merchant_id         VARCHAR(20)     NOT NULL,
    merchant_name       VARCHAR(100)    NOT NULL,
    merchant_category   VARCHAR(50)     NOT NULL,
    -- GROCERY, FUEL, PHARMACY, RESTAURANT, ELECTRONICS,
    -- CLOTHING, UTILITIES, ENTERTAINMENT, FURNITURE,
    -- HARDWARE, HOTEL, RETAIL

    -- Transaction context
    transaction_type    VARCHAR(20)     NOT NULL
    -- PURCHASE, REFUND, REVERSAL, CASH_ADVANCE

);

-- ── Indexes for common NL query patterns ─────────────────────
CREATE INDEX idx_transaction_date   ON transactions (transaction_date);
CREATE INDEX idx_status             ON transactions (status);
CREATE INDEX idx_card_brand         ON transactions (card_brand);
CREATE INDEX idx_card_type          ON transactions (card_type);
CREATE INDEX idx_card_class         ON transactions (card_class);
CREATE INDEX idx_terminal_id        ON transactions (terminal_id);
CREATE INDEX idx_merchant_id        ON transactions (merchant_id);
CREATE INDEX idx_merchant_name      ON transactions (merchant_name);
CREATE INDEX idx_merchant_category  ON transactions (merchant_category);
CREATE INDEX idx_approval_code      ON transactions (approval_code);
CREATE INDEX idx_amount             ON transactions (amount);
CREATE INDEX idx_currency           ON transactions (currency);
CREATE INDEX idx_response_code      ON transactions (response_code);
CREATE INDEX idx_transaction_type   ON transactions (transaction_type);

-- Composite: most common combined filter
CREATE INDEX idx_status_date        ON transactions (status, transaction_date);
CREATE INDEX idx_brand_status       ON transactions (card_brand, status);

SELECT 'Schema created successfully. Table: transactions' AS result;
