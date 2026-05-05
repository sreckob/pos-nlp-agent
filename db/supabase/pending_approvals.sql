-- ============================================================
--  pending_approvals — operations queue for ops-approver agent
--  Customer-side actions (dispute reversal, loyalty credit)
--  enqueue a row here. Ops console reads + decides. Decision
--  triggers the actual write_ops call.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS pending_approvals (

    -- Identity
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Type + payload
    type                    VARCHAR(20)     NOT NULL,
    -- DISPUTE | LOYALTY
    payload                 JSONB           NOT NULL,
    -- DISPUTE: {original_tx_id, duplicate_tx_id, pan_masked, amount, merchant_name}
    -- LOYALTY: {pan_masked, points_to_add, transaction_ids[]}

    -- Lifecycle
    status                  VARCHAR(20)     NOT NULL DEFAULT 'PENDING',
    -- PENDING | APPROVED | REJECTED

    -- Customer linkage (for WS push back)
    customer_session_id     VARCHAR(64)     NOT NULL,
    customer_language       VARCHAR(2)      DEFAULT 'en',

    -- Approver agent's auto-recommendation (filled when ops opens detail)
    agent_recommendation    JSONB,
    -- {decision, confidence, audit_summary, blocking_reason}

    -- Decision metadata (filled at /ops/decide)
    decided_at              TIMESTAMP,
    decided_by              VARCHAR(64),
    -- For demo: 'ops_console' (single role). Production: real user id.
    audit_summary           TEXT,

    -- Audit
    created_at              TIMESTAMP       NOT NULL DEFAULT NOW()

);

CREATE INDEX IF NOT EXISTS idx_pending_status      ON pending_approvals (status);
CREATE INDEX IF NOT EXISTS idx_pending_type        ON pending_approvals (type);
CREATE INDEX IF NOT EXISTS idx_pending_session     ON pending_approvals (customer_session_id);
CREATE INDEX IF NOT EXISTS idx_pending_created_at  ON pending_approvals (created_at DESC);

SELECT 'pending_approvals table ready.' AS result;
