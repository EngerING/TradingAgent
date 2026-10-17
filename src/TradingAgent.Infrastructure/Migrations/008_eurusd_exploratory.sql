CREATE SCHEMA paper_exploratory;
CREATE TABLE paper_exploratory.events (
 cohort_id text NOT NULL CHECK(cohort_id ~ '^eurusd-explore-[a-f0-9]{32}$'),
 revision bigint NOT NULL CHECK(revision>0),
 payload text NOT NULL CHECK(payload::jsonb->>'scope'='EURUSD_PAPER_EXPLORATORY'
 AND payload::jsonb->>'classification'='EXPLORATORY_NOT_VALIDATED'
 AND payload::jsonb->>'live_enabled'='false'),
 previous_hash text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(cohort_id,revision)
);
CREATE FUNCTION paper_exploratory.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'PAPER_EXPLORATORY_IMMUTABLE'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON paper_exploratory.events
 FOR EACH ROW EXECUTE FUNCTION paper_exploratory.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA paper_exploratory TO paper_lab_app;
  GRANT SELECT,INSERT ON paper_exploratory.events TO paper_lab_app;
 END IF;
END $$;
