CREATE TABLE paper_lab.ford_diagnostic_events (
 trial_id text NOT NULL CHECK(trial_id ~ '^ford-diag-[a-f0-9]{32}$'),
 revision bigint NOT NULL CHECK(revision > 0),
 binding_id text NOT NULL,
 scope text NOT NULL CHECK(scope IN ('FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1','FORD_DIAGNOSTIC_R10')),
 occurred_at timestamptz NOT NULL,
 kind text NOT NULL,
 payload text NOT NULL CHECK(payload::jsonb->'state'->>'environment'='PAPER_TRADING'
   AND payload::jsonb->'state'->>'classification'='EXECUTION_DIAGNOSTICS'
   AND payload::jsonb->'state'->'strategy_version'='null'::jsonb),
 previous_hash text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(trial_id,revision)
);
CREATE FUNCTION paper_lab.ford_diagnostic_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'FORD_DIAGNOSTIC_EVIDENCE_IMMUTABLE'; END $$;
CREATE TRIGGER ford_diagnostic_immutable BEFORE UPDATE OR DELETE ON paper_lab.ford_diagnostic_events
 FOR EACH ROW EXECUTE FUNCTION paper_lab.ford_diagnostic_immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT SELECT,INSERT ON paper_lab.ford_diagnostic_events TO paper_lab_app;
 END IF;
END $$;
