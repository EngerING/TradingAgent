CREATE SCHEMA aggressive_growth;
CREATE TABLE aggressive_growth.events (
 experiment_id text NOT NULL CHECK(experiment_id ~ '^aggressive-r20-[a-f0-9]{32}$'),
 revision bigint NOT NULL CHECK(revision>0),
 payload text NOT NULL CHECK(payload::jsonb->>'scope'='AGGRESSIVE_GROWTH_R20'
  AND payload::jsonb->>'classification'='SHADOW_SIMULATED'
  AND payload::jsonb->>'broker_orders'='0' AND payload::jsonb->>'live_enabled'='false'),
 previous_hash text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(experiment_id,revision)
);
CREATE FUNCTION aggressive_growth.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'R20_JOURNAL_IMMUTABLE'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON aggressive_growth.events
 FOR EACH ROW EXECUTE FUNCTION aggressive_growth.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA aggressive_growth TO paper_lab_app;
  GRANT SELECT,INSERT ON aggressive_growth.events TO paper_lab_app;
 END IF;
END $$;
