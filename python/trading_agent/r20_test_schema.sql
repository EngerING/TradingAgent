-- TEST DATABASE ONLY. Installed through the identity-checked TestStore, never migrations/011.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR inet_server_addr()<>'127.0.0.1'::inet
 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS r20_v2_test;
CREATE TABLE IF NOT EXISTS r20_v2_test.profiles (
  scope_id text NOT NULL, version bigint NOT NULL CHECK(version>0),
  profile_hash text NOT NULL, payload text NOT NULL,
  PRIMARY KEY(scope_id,version)
);
CREATE TABLE IF NOT EXISTS r20_v2_test.events (
  scope_id text NOT NULL, revision bigint NOT NULL CHECK(revision>0),
  request_id text NOT NULL, previous_hash text NOT NULL, event_hash text NOT NULL,
  profile_version bigint NOT NULL, payload text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(scope_id,revision), UNIQUE(scope_id,request_id),
  FOREIGN KEY(scope_id,profile_version) REFERENCES r20_v2_test.profiles(scope_id,version)
);
CREATE OR REPLACE FUNCTION r20_v2_test.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY'; END $$;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='r20_v2_profiles_immutable') THEN
 CREATE TRIGGER r20_v2_profiles_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_test.profiles
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 CREATE TRIGGER r20_v2_events_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_test.events
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_test.validate_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior r20_v2_test.events; b jsonb; d jsonb; p jsonb; old jsonb; od jsonb;
  eq numeric; charge jsonb; replacement jsonb; expected_budget numeric;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.scope_id,0));
 SELECT * INTO prior FROM r20_v2_test.events WHERE scope_id=NEW.scope_id ORDER BY revision DESC LIMIT 1;
 IF NEW.revision<>COALESCE(prior.revision,0)+1 OR NEW.previous_hash<>COALESCE(prior.event_hash,'')
 OR NEW.event_hash<>encode(sha256(convert_to(NEW.previous_hash||chr(10)||NEW.revision::text||chr(10)||
    NEW.request_id||chr(10)||NEW.payload,'UTF8')),'hex') THEN RAISE EXCEPTION 'CHAIN_INTEGRITY'; END IF;
 b=NEW.payload::jsonb; d=b->'daily'; p=b->'profile';
 IF NEW.scope_id !~ '^r20-v2-test-ledger-[a-zA-Z0-9_-]+$'
 OR (b->>'format') IS DISTINCT FROM 'R20_V2_TEST_ACCOUNTING_V1'
 OR (d->>'scope_id') IS DISTINCT FROM NEW.scope_id OR (p->>'scope_id') IS DISTINCT FROM NEW.scope_id
 OR (d->>'profile_hash') IS DISTINCT FROM (p->>'configuration_hash')
 OR (d->>'profile_version')::bigint IS DISTINCT FROM NEW.profile_version
 OR NOT EXISTS (SELECT 1 FROM r20_v2_test.profiles WHERE scope_id=NEW.scope_id
   AND version=NEW.profile_version AND payload::jsonb=p AND profile_hash=p->>'configuration_hash')
 THEN RAISE EXCEPTION 'PROFILE_INTEGRITY'; END IF;
 IF jsonb_typeof(b->'costs') IS DISTINCT FROM 'array' OR jsonb_typeof(b->'open_gross') IS DISTINCT FROM 'array'
 OR jsonb_typeof(d->'loss_blocked') IS DISTINCT FROM 'boolean'
 OR jsonb_typeof(d->'operational_blocks') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'SNAPSHOT_FIELDS'; END IF;
 IF (SELECT count(*)<>count(DISTINCT c->>'cost_id') FROM jsonb_array_elements(b->'costs') c)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(b->'costs') c WHERE c->>'status' NOT IN ('RESERVED','ACCRUED','SETTLED')
   OR (c->>'amount')::numeric<0)
 THEN RAISE EXCEPTION 'COST_HISTORY'; END IF;
 eq=(p->>'capital_base_usd')::numeric+(b->>'realized_gross')::numeric
   +COALESCE((SELECT sum((x->>1)::numeric) FROM jsonb_array_elements(b->'open_gross') x),0)
   -COALESCE((SELECT sum((c->>'amount')::numeric) FROM jsonb_array_elements(b->'costs') c),0);
 IF eq IS NULL OR (d->>'current_equity')::numeric IS DISTINCT FROM eq THEN RAISE EXCEPTION 'EQUITY_MISMATCH'; END IF;
 IF GREATEST(0,(d->>'reference')::numeric-eq)>=(d->>'budget')::numeric AND NOT (d->>'loss_blocked')::boolean
 THEN RAISE EXCEPTION 'LOSS_LATCH_REQUIRED'; END IF;
 IF prior.revision IS NOT NULL THEN
   old=prior.payload::jsonb; od=old->'daily';
   IF (d->>'at')::timestamptz<(od->>'at')::timestamptz OR d->>'day_id'<od->>'day_id'
   OR NEW.profile_version<prior.profile_version
   OR (p->>'capital_base_usd')::numeric<>(old->'profile'->>'capital_base_usd')::numeric
   THEN RAISE EXCEPTION 'STATE_REGRESSION'; END IF;
   IF NOT (d->'operational_blocks') @> (od->'operational_blocks') THEN RAISE EXCEPTION 'OPERATIONAL_BLOCK_REMOVED'; END IF;
   IF d->>'day_id'=od->>'day_id' THEN
     expected_budget=LEAST((od->>'budget')::numeric,(od->>'eligible_base')::numeric*(p->>'daily_loss_limit_pct')::numeric/100);
     IF (d->>'reference') IS DISTINCT FROM (od->>'reference')
     OR (d->>'eligible_base') IS DISTINCT FROM (od->>'eligible_base')
     OR (d->>'budget')::numeric>expected_budget
     OR ((od->>'loss_blocked')::boolean AND NOT (d->>'loss_blocked')::boolean)
     THEN RAISE EXCEPTION 'DAILY_TRANSITION'; END IF;
   ELSE
     IF (d->'operational_blocks') @> '["ECONOMIC_BOUNDARY_UNVERIFIED"]'::jsonb AND (
       (d->>'reference') IS DISTINCT FROM (od->>'reference')
       OR (d->>'budget') IS DISTINCT FROM (od->>'budget')
       OR ((od->>'loss_blocked')::boolean AND NOT (d->>'loss_blocked')::boolean))
     THEN RAISE EXCEPTION 'UNVERIFIED_BOUNDARY_CANNOT_RESET'; END IF;
     IF (NEW.profile_version<=prior.profile_version AND NOT (
       NEW.profile_version=prior.profile_version AND p=old->'profile'
       AND (d->>'entry_profile_valid')::boolean=false
       AND (d->>'at')::timestamptz>=(p->>'effective_until')::timestamptz))
     OR (d->>'inventory_verified')::boolean
     OR (d->'open_terms') IS DISTINCT FROM (od->'open_terms')
     OR (d->'pending_terms') IS DISTINCT FROM (od->'pending_terms')
     THEN RAISE EXCEPTION 'NEW_DAY_RECONCILIATION_REQUIRED'; END IF;
   END IF;
   FOR charge IN SELECT * FROM jsonb_array_elements(old->'costs') LOOP
     SELECT c INTO replacement FROM jsonb_array_elements(b->'costs') c WHERE c->>'cost_id'=charge->>'cost_id';
     IF charge->>'status'='SETTLED' AND replacement IS DISTINCT FROM charge
     OR charge->>'status'='ACCRUED' AND (replacement IS NULL OR replacement->>'status'='RESERVED'
       OR (replacement->>'amount')::numeric IS DISTINCT FROM (charge->>'amount')::numeric)
     THEN RAISE EXCEPTION 'COST_HISTORY'; END IF;
   END LOOP;
 END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='r20_v2_validate_insert') THEN
 CREATE TRIGGER r20_v2_validate_insert BEFORE INSERT ON r20_v2_test.events
 FOR EACH ROW EXECUTE FUNCTION r20_v2_test.validate_insert();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_test.append_state(
 s text, k text, expected bigint, prev text, v bigint, ph text, profile text, body text)
RETURNS json LANGUAGE plpgsql AS $$
DECLARE h r20_v2_test.events; duplicate r20_v2_test.events; n bigint; hash text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 SELECT * INTO duplicate FROM r20_v2_test.events WHERE scope_id=s AND request_id=k;
 IF FOUND THEN
   IF duplicate.payload<>body THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN json_build_object('revision',duplicate.revision,'hash',duplicate.event_hash);
 END IF;
 SELECT * INTO h FROM r20_v2_test.events WHERE scope_id=s ORDER BY revision DESC LIMIT 1;
 IF expected<>COALESCE(h.revision,0) OR prev<>COALESCE(h.event_hash,'') THEN
   RAISE EXCEPTION 'CAS_CONFLICT';
 END IF;
 INSERT INTO r20_v2_test.profiles VALUES(s,v,ph,profile) ON CONFLICT DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM r20_v2_test.profiles WHERE scope_id=s AND version=v
               AND profile_hash=ph AND payload=profile) THEN RAISE EXCEPTION 'PROFILE_VERSION_REUSED'; END IF;
 n=expected+1;
 hash=encode(sha256(convert_to(prev||chr(10)||n::text||chr(10)||k||chr(10)||body,'UTF8')),'hex');
 INSERT INTO r20_v2_test.events VALUES(s,n,k,prev,hash,v,body,clock_timestamp());
 RETURN json_build_object('revision',n,'hash',hash);
END $$;
COMMIT;
