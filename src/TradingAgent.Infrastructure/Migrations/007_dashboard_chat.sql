CREATE SCHEMA dashboard_chat;
CREATE INDEX shadow_observations_read ON research_shadow.events(study_id,revision DESC)
 WHERE payload::jsonb->>'event'='COMMON_MARKET_OPPORTUNITY_EVALUATED';
CREATE TABLE dashboard_chat.events (
 session_id text NOT NULL CHECK(session_id ~ '^sol-ui-[a-f0-9]{32}$'),
 request_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('RESERVED','RESPONSE','BLOCKED','FAILED')),
 payload text NOT NULL,
 event_hash text NOT NULL CHECK(event_hash ~ '^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(session_id,request_id,kind)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON dashboard_chat.events
 FOR EACH ROW EXECUTE FUNCTION research_shadow.immutable();
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='paper_lab_app') THEN
  GRANT USAGE ON SCHEMA dashboard_chat TO paper_lab_app;
  GRANT SELECT,INSERT ON dashboard_chat.events TO paper_lab_app;
 END IF;
END $$;
