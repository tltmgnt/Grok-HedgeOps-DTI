-- PAPER-only durable entry AND exit intents. Reviewed migration-owner action.
-- This file does not grant order authority or enable scheduled broker trading.
-- Apply to the dedicated PostgreSQL PAPER ledger database before manual execution.
-- Use a separate least-privilege runtime account; do not run schema DDL as runtime.
BEGIN;
CREATE TABLE IF NOT EXISTS paper_order_ledger (
    request_id varchar(48) PRIMARY KEY,
    symbol varchar(15) NOT NULL,
    notional_usd numeric(12,2) NOT NULL CHECK (notional_usd > 0),
    state text NOT NULL CHECK (state IN
        ('ATTEMPT_RESERVED','BROKER_UNCONFIRMED','BROKER_CONFIRMED')),
    broker_order_id text,
    broker_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_exit_ledger (
    request_id varchar(48) PRIMARY KEY,
    symbol varchar(15) NOT NULL,
    quantity numeric(20,8) NOT NULL CHECK (quantity > 0),
    state text NOT NULL CHECK (state IN
        ('ATTEMPT_RESERVED','BROKER_UNCONFIRMED','BROKER_CONFIRMED')),
    broker_order_id text,
    broker_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON TABLE paper_order_ledger FROM PUBLIC;
REVOKE ALL ON TABLE paper_exit_ledger FROM PUBLIC;
COMMIT;

-- The application still needs a separately reviewed dedicated runtime role.
-- Schema ownership, ALTER, DELETE, TRUNCATE and unrestricted table UPDATE
-- must not be granted to untrusted users. Read/reconcile ledger rows manually
-- after any ambiguous broker acknowledgment. No migration auto-runs in Actions.
