-- ============================================================
--  POS Payment Transaction System — Complete Database Schema
--  Version 2.0 — includes dispute and loyalty columns
--  Natural Language Prompt Agent Project
-- ============================================================

-- ── Extensions ───────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Drop existing tables ──────────────────────────────────────
DROP TABLE IF EXISTS loyalty_accounts;
DROP TABLE IF EXISTS transactions;

-- ── Main transactions table ───────────────────────────────────
CREATE TABLE transactions (

    -- Identity
    transaction_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Timing
    transaction_date        TIMESTAMP       NOT NULL,

    -- Amount
    amount                  NUMERIC(12, 2)  NOT NULL,
    currency                VARCHAR(3)      NOT NULL,
    -- RSD, EUR, USD

    -- Outcome
    status                  VARCHAR(20)     NOT NULL,
    -- APPROVED, DECLINED, REVERSED, PENDING
    response_code           VARCHAR(4)      NOT NULL,
    -- ISO 8583:
    --   00 = approved
    --   51 = insufficient funds
    --   05 = do not honour
    --   14 = invalid card number
    --   61 = exceeds withdrawal limit
    --   57 = transaction not permitted
    --   91 = issuer unavailable
    --   41 = lost card
    --   43 = stolen card
    approval_code           VARCHAR(6),
    -- 6-char alphanumeric, NULL when not approved

    -- Card details
    pan_masked              VARCHAR(19)     NOT NULL,
    -- Visa/MC/Dina/UP: 411111******1111 (16 digits)
    -- Amex:            370000*****1234  (15 digits)
    card_brand              VARCHAR(20)     NOT NULL,
    -- VISA, MASTERCARD, AMEX, DINACARD, UNIONPAY
    card_type               VARCHAR(20)     NOT NULL,
    -- CHIP, CONTACTLESS, MAGNETIC, MANUAL
    card_class              VARCHAR(20)     NOT NULL,
    -- DEBIT, CREDIT, PREPAID, CORPORATE

    -- Terminal & Merchant
    terminal_id             VARCHAR(20)     NOT NULL,
    merchant_id             VARCHAR(20)     NOT NULL,
    merchant_name           VARCHAR(100)    NOT NULL,
    merchant_category       VARCHAR(50)     NOT NULL,
    -- GROCERY, FUEL, PHARMACY, RESTAURANT, ELECTRONICS,
    -- CLOTHING, UTILITIES, ENTERTAINMENT, FURNITURE,
    -- HARDWARE, HOTEL, RETAIL

    -- Transaction context
    transaction_type        VARCHAR(20)     NOT NULL,
    -- PURCHASE, REFUND, REVERSAL, CASH_ADVANCE

    -- ── Loyalty columns ──────────────────────────────────────
    -- Only populated for PANs enrolled in loyalty_accounts.
    -- Non-members always have 0 / FALSE.
    loyalty_points_earned   INTEGER         NOT NULL DEFAULT 0,
    -- Points earned from this transaction
    -- Rule: APPROVED + PURCHASE + RSD + enrolled PAN → FLOOR(amount/100)
    -- All other cases → 0
    loyalty_points_credited BOOLEAN         NOT NULL DEFAULT FALSE,
    -- Whether points have been added to loyalty_accounts.points
    -- Set to TRUE by the loyalty agent after crediting

    -- ── Dispute columns ──────────────────────────────────────
    -- NULL until a dispute is raised on this transaction.
    dispute_status          VARCHAR(20)     DEFAULT NULL,
    -- NULL        = no dispute
    -- DISPUTED    = claim raised, under review
    -- APPROVED    = reversal approved, transaction reversed
    -- REJECTED    = claim rejected
    dispute_id              UUID            DEFAULT NULL,
    -- Same UUID on both transactions in a duplicate charge pair
    -- Allows: SELECT * FROM transactions WHERE dispute_id = 'xxx'
    -- to find both the original and the duplicate
    disputed_at             TIMESTAMP       DEFAULT NULL,
    -- When the dispute claim was raised
    resolved_at             TIMESTAMP       DEFAULT NULL
    -- When the dispute was approved or rejected

);

-- ── Indexes ───────────────────────────────────────────────────

-- Core query patterns
CREATE INDEX idx_transaction_date    ON transactions (transaction_date);
CREATE INDEX idx_status              ON transactions (status);
CREATE INDEX idx_card_brand          ON transactions (card_brand);
CREATE INDEX idx_card_type           ON transactions (card_type);
CREATE INDEX idx_card_class          ON transactions (card_class);
CREATE INDEX idx_terminal_id         ON transactions (terminal_id);
CREATE INDEX idx_merchant_id         ON transactions (merchant_id);
CREATE INDEX idx_merchant_name       ON transactions (merchant_name);
CREATE INDEX idx_merchant_category   ON transactions (merchant_category);
CREATE INDEX idx_approval_code       ON transactions (approval_code);
CREATE INDEX idx_amount              ON transactions (amount);
CREATE INDEX idx_currency            ON transactions (currency);
CREATE INDEX idx_response_code       ON transactions (response_code);
CREATE INDEX idx_transaction_type    ON transactions (transaction_type);
CREATE INDEX idx_pan_masked          ON transactions (pan_masked);

-- Composite indexes for common combined queries
CREATE INDEX idx_status_date         ON transactions (status, transaction_date);
CREATE INDEX idx_brand_status        ON transactions (card_brand, status);
CREATE INDEX idx_approval_code_pan   ON transactions (approval_code, pan_masked);

-- Loyalty indexes
CREATE INDEX idx_loyalty_credited    ON transactions (loyalty_points_credited);
CREATE INDEX idx_loyalty_points      ON transactions (loyalty_points_earned)
    WHERE loyalty_points_earned > 0;

-- Dispute indexes
CREATE INDEX idx_dispute_status      ON transactions (dispute_status)
    WHERE dispute_status IS NOT NULL;
CREATE INDEX idx_dispute_id          ON transactions (dispute_id)
    WHERE dispute_id IS NOT NULL;

-- ── Loyalty accounts table ────────────────────────────────────
CREATE TABLE loyalty_accounts (

    account_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Links to transactions.pan_masked
    pan_masked      VARCHAR(19)     NOT NULL UNIQUE,

    -- Current point balance
    points          INTEGER         NOT NULL DEFAULT 0,

    -- Loyalty tier based on total_spent
    -- STANDARD: 0–49,999 RSD lifetime
    -- SILVER:   50,000–199,999 RSD lifetime
    -- GOLD:     200,000+ RSD lifetime
    tier            VARCHAR(20)     NOT NULL DEFAULT 'STANDARD',
    -- STANDARD, SILVER, GOLD

    -- Lifetime spend in RSD (used for tier calculation)
    total_spent     NUMERIC(12, 2)  NOT NULL DEFAULT 0,

    -- Timestamps
    enrolled_at     TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_updated    TIMESTAMP       NOT NULL DEFAULT NOW()

);

CREATE INDEX idx_loyalty_pan    ON loyalty_accounts (pan_masked);
CREATE INDEX idx_loyalty_tier   ON loyalty_accounts (tier);

-- ── Verification ──────────────────────────────────────────────
SELECT
    'transactions'    AS table_name,
    COUNT(*)          AS column_count
FROM information_schema.columns
WHERE table_name = 'transactions'
  AND table_schema = 'public'

UNION ALL

SELECT
    'loyalty_accounts',
    COUNT(*)
FROM information_schema.columns
WHERE table_name = 'loyalty_accounts'
  AND table_schema = 'public';
