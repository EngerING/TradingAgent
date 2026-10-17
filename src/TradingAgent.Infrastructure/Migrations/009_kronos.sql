CREATE SCHEMA research_kronos;
CREATE TABLE research_kronos.events (
 id text PRIMARY KEY CHECK(id ~ '^kronos-[a-f0-9]{64}$'),
 kind text NOT NULL CHECK(kind IN ('PREDICTION','OUTCOME','STATUS','EVALUATION')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 payload text NOT NULL CHECK(payload::jsonb->>'scope'='KRONOS_OBSERVATION_ONLY'
   AND payload::jsonb->>'execution_authority'='false' AND payload::jsonb->>'live_enabled'='false'),
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$')
);
CREATE INDEX kronos_events_kind ON research_kronos.events(kind,created_at DESC);
CREATE VIEW research_kronos.predictions AS SELECT id,
 payload::jsonb->>'symbol' AS symbol,payload::jsonb->>'timeframe' AS timeframe,
 (payload::jsonb->>'candle_timestamp')::timestamptz AS candle_timestamp,
 payload::jsonb->>'model_version' AS model_version,payload::jsonb->>'config_hash' AS config_hash,
 payload::jsonb->>'signal_id' AS signal_id,payload::jsonb->>'calibration_state' AS calibration_state,
 (payload::jsonb->>'raw_tp_frequency')::numeric AS raw_tp_frequency,
 (payload::jsonb->>'calibrated_probability')::numeric AS calibrated_probability,
 payload::jsonb AS data FROM research_kronos.events WHERE kind='PREDICTION';
CREATE FUNCTION research_kronos.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'KRONOS_EVIDENCE_IMMUTABLE'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON research_kronos.events
 FOR EACH ROW EXECUTE FUNCTION research_kronos.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA research_kronos TO paper_lab_app;
  GRANT SELECT,INSERT ON research_kronos.events TO paper_lab_app;
  GRANT SELECT ON research_kronos.predictions TO paper_lab_app;
 END IF;
END $$;
