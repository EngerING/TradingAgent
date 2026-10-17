CREATE SCHEMA research_shadow;
CREATE TABLE research_shadow.events (
 study_id text NOT NULL CHECK(study_id ~ '^eurusd-shadow-[a-f0-9]{32}$'),
 revision bigint NOT NULL CHECK(revision > 0),
 payload text NOT NULL CHECK(payload::jsonb->>'classification'='SIMULATED_SHADOW'
   AND payload::jsonb->>'broker_orders'='0' AND payload::jsonb->>'execution_authorized'='false'
   AND payload::jsonb->>'scope'='EURUSD_SHADOW_R1_R5_R10'),
 previous_hash text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(study_id,revision)
);
CREATE FUNCTION research_shadow.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'EURUSD_SHADOW_EVIDENCE_IMMUTABLE'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON research_shadow.events
 FOR EACH ROW EXECUTE FUNCTION research_shadow.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA research_shadow TO paper_lab_app;
  GRANT SELECT,INSERT ON research_shadow.events TO paper_lab_app;
 END IF;
END $$;
