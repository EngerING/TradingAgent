CREATE SCHEMA price_risk;
CREATE TABLE price_risk.events (
 experiment_id text NOT NULL CHECK(experiment_id ~ '^r10-price-[a-f0-9]{32}$'),
 revision bigint NOT NULL CHECK(revision>0),
 payload text NOT NULL CHECK(payload::jsonb->>'scope'='R10_PRICE_RISK_EXPERIMENTAL'
 AND payload::jsonb->>'classification'='SIMULATED_SHADOW'
 AND payload::jsonb->>'broker_orders'='0' AND payload::jsonb->>'live_enabled'='false'),
 previous_hash text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(experiment_id,revision)
);
CREATE FUNCTION price_risk.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'PRICE_RISK_JOURNAL_IMMUTABLE'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON price_risk.events
 FOR EACH ROW EXECUTE FUNCTION price_risk.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA price_risk TO paper_lab_app;
  GRANT SELECT,INSERT ON price_risk.events TO paper_lab_app;
 END IF;
END $$;
