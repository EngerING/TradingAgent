-- Installed only by an explicit setup call through the identity-checked TestStore.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS r20_v2_config;
CREATE TABLE IF NOT EXISTS r20_v2_config.events(
 scope text NOT NULL, revision bigint NOT NULL, request_id text NOT NULL, request_hash text NOT NULL,
 event_hash text NOT NULL, payload text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,revision),UNIQUE(scope,request_id));
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='r20_configuration_immutable') THEN
 CREATE TRIGGER r20_configuration_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_config.events
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_config.append_event(s text,r bigint,prev text,k text,req text,accounting text,body text)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE h r20_v2_config.events; dup r20_v2_config.events; current_accounting text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 SELECT * INTO dup FROM r20_v2_config.events WHERE scope=s AND request_id=k;
 IF FOUND THEN
   IF dup.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN dup.revision;
 END IF;
 SELECT * INTO h FROM r20_v2_config.events WHERE scope=s ORDER BY revision DESC LIMIT 1;
 IF r<>COALESCE(h.revision,0) OR prev<>COALESCE(h.event_hash,'') THEN RAISE EXCEPTION 'CAS_CONFLICT'; END IF;
 SELECT event_hash INTO current_accounting FROM r20_v2_test.events WHERE scope_id=s ORDER BY revision DESC LIMIT 1;
 IF accounting IS DISTINCT FROM current_accounting THEN RAISE EXCEPTION 'CAS_CONFLICT'; END IF;
 IF (body::jsonb->>'revision')::bigint<>r+1 OR body::jsonb->>'previous'<>prev
 OR body::jsonb->>'requestId'<>k OR body::jsonb->>'requestHash'<>req
 OR body::jsonb->>'lifecycle' NOT IN ('DRAFT','VALIDATED','ACTIVATED_FOR_SHADOW') THEN RAISE EXCEPTION 'CONFIG_CONTRACT'; END IF;
 INSERT INTO r20_v2_config.events VALUES(s,r+1,k,req,body::jsonb->>'hash',body,clock_timestamp());
 RETURN r+1;
END $$;
COMMIT;
