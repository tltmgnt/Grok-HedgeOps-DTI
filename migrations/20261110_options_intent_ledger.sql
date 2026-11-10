-- Options order intent ledger foundation. This migration does NOT enable execution.
-- Apply with a migration owner; application role must not own these tables.
CREATE TABLE IF NOT EXISTS options_order_intents (
    intent_id uuid PRIMARY KEY,
    client_order_id text NOT NULL UNIQUE,
    account_id text NOT NULL CHECK (length(account_id) BETWEEN 1 AND 128),
    environment text NOT NULL CHECK (environment IN ('paper', 'live')),
    contract_symbol text NOT NULL CHECK (length(contract_symbol) BETWEEN 15 AND 32),
    side text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 100),
    limit_price numeric(12, 2) NOT NULL CHECK (limit_price > 0),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'submission_unknown', 'acknowledged',
                         'rejected', 'cancelled', 'filled')),
    broker_order_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status NOT IN ('acknowledged', 'filled') OR broker_order_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS options_order_broker_id_unique
    ON options_order_intents (environment, account_id, broker_order_id)
    WHERE broker_order_id IS NOT NULL;

-- Every state change is auditable, even when a broker response is ambiguous.
CREATE TABLE IF NOT EXISTS options_order_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    intent_id uuid NOT NULL REFERENCES options_order_intents(intent_id) ON DELETE RESTRICT,
    event_type text NOT NULL CHECK (event_type IN
        ('reserved', 'submission_unknown', 'acknowledged', 'rejected',
         'cancelled', 'filled', 'reconciled')),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

-- The ledger is append-only with respect to intent identity and event history.
-- Migration owners should be distinct from runtime roles.
CREATE OR REPLACE FUNCTION options_order_events_no_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'options order events are append-only';
END;
$$;
DROP TRIGGER IF EXISTS options_order_events_immutable ON options_order_events;
CREATE TRIGGER options_order_events_immutable
    BEFORE UPDATE OR DELETE ON options_order_events
    FOR EACH ROW EXECUTE FUNCTION options_order_events_no_mutation();

CREATE OR REPLACE FUNCTION options_intent_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'options order intents cannot be deleted';
    END IF;
    IF (NEW.intent_id, NEW.client_order_id, NEW.account_id, NEW.environment,
        NEW.contract_symbol, NEW.side, NEW.quantity, NEW.limit_price,
        NEW.payload_sha256, NEW.created_at)
       IS DISTINCT FROM
       (OLD.intent_id, OLD.client_order_id, OLD.account_id, OLD.environment,
        OLD.contract_symbol, OLD.side, OLD.quantity, OLD.limit_price,
        OLD.payload_sha256, OLD.created_at) THEN
        RAISE EXCEPTION 'options order intent identity is immutable';
    END IF;
    -- Once assigned, a broker order ID is immutable. Otherwise a replay or
    -- faulty reconciliation could silently relink an intent to another order.
    IF OLD.broker_order_id IS NOT NULL
       AND NEW.broker_order_id IS DISTINCT FROM OLD.broker_order_id THEN
        RAISE EXCEPTION 'options broker order ID is immutable once assigned';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT (
            (OLD.status = 'reserved' AND NEW.status IN ('submission_unknown', 'rejected', 'cancelled'))
            OR (OLD.status = 'submission_unknown' AND NEW.status IN ('acknowledged', 'rejected', 'cancelled', 'filled'))
            OR (OLD.status = 'acknowledged' AND NEW.status IN ('filled', 'cancelled'))
        ) THEN
            RAISE EXCEPTION 'invalid options order status transition';
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS options_intent_immutable ON options_order_intents;
CREATE TRIGGER options_intent_immutable
    BEFORE UPDATE OR DELETE ON options_order_intents
    FOR EACH ROW EXECUTE FUNCTION options_intent_guard();

-- Write an audit record in the same transaction as every reservation or
-- status transition. A failed audit insert rolls back the state change.
CREATE OR REPLACE FUNCTION options_intent_audit()
RETURNS trigger LANGUAGE plpgsql AS $
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO options_order_events (intent_id, event_type, details)
        VALUES (NEW.intent_id, 'reserved', jsonb_build_object(
            'client_order_id', NEW.client_order_id,
            'environment', NEW.environment));
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO options_order_events (intent_id, event_type, details)
        VALUES (NEW.intent_id, NEW.status, jsonb_build_object(
            'previous_status', OLD.status,
            'broker_order_id', NEW.broker_order_id));
    END IF;
    RETURN NEW;
END;
$;
DROP TRIGGER IF EXISTS options_intent_audit_trigger ON options_order_intents;
CREATE TRIGGER options_intent_audit_trigger
    AFTER INSERT OR UPDATE ON options_order_intents
    FOR EACH ROW EXECUTE FUNCTION options_intent_audit();

-- Fail closed: no runtime access granted here. A separately reviewed,
-- least-privilege DB role and authenticated broker reconciliation are required
-- before any options order can be submitted. Never retry an ambiguous POST.
