-- Isolated laboratory control plane. Never install in Paper or journal011.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR inet_server_addr()<>'127.0.0.1'::inet
 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS r20_v2_runner;
CREATE TABLE IF NOT EXISTS r20_v2_runner.controls(
 scope text NOT NULL, kind text NOT NULL CHECK(kind IN ('PREREGISTER','STOP')),
 payload text NOT NULL, hash text NOT NULL, PRIMARY KEY(scope,kind));
CREATE OR REPLACE FUNCTION r20_v2_runner.control(s text,k text,p text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE old text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 IF k<>'STOP' THEN RAISE EXCEPTION 'STOP_ONLY'; END IF;
 IF NOT EXISTS(SELECT 1 FROM r20_v2_runner.controls WHERE scope=s AND kind='PREREGISTER')
 THEN RAISE EXCEPTION 'PREREGISTRATION_REQUIRED'; END IF;
 INSERT INTO r20_v2_runner.controls VALUES(s,k,p,encode(sha256(convert_to(p,'UTF8')),'hex')) ON CONFLICT DO NOTHING;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_runner.entry_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.scope,0));
 IF (TG_TABLE_SCHEMA='r20_v2_admission' OR NEW.payload::jsonb->>'kind'='OPEN')
 AND EXISTS(SELECT 1 FROM r20_v2_runner.controls WHERE scope=NEW.scope AND kind='STOP')
 THEN RAISE EXCEPTION 'SHADOW_STOP_REQUESTED'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='r20_runner_controls_immutable') THEN
 CREATE TRIGGER r20_runner_controls_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_runner.controls
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 CREATE TRIGGER r20_runner_reserve_guard BEFORE INSERT ON r20_v2_admission.receipts
 FOR EACH ROW EXECUTE FUNCTION r20_v2_runner.entry_guard();
 CREATE TRIGGER r20_runner_open_guard BEFORE INSERT ON r20_v2_shadow.events
 FOR EACH ROW EXECUTE FUNCTION r20_v2_runner.entry_guard();
 END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA r20_v2_runner FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA r20_v2_runner FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT USAGE ON SCHEMA r20_v2_runner TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT SELECT ON ALL TABLES IN SCHEMA r20_v2_runner TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT EXECUTE ON FUNCTION r20_v2_runner.control(text,text,text) TO r20_lab_shadow;
COMMIT;
