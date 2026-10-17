-- Configuration documents only. Explicit installation in the isolated test cluster.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE TABLE IF NOT EXISTS r20_v2_config.preparations(
 scope text NOT NULL, revision bigint NOT NULL, request_id text NOT NULL, request_hash text NOT NULL,
 event_hash text NOT NULL, payload text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,revision),UNIQUE(scope,request_id));
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='r20_preparation_immutable') THEN
 CREATE TRIGGER r20_preparation_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_config.preparations
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_config.append_preparation(s text,r bigint,prev text,k text,req text,body text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE h r20_v2_config.preparations; dup r20_v2_config.preparations; b jsonb; p jsonb; v jsonb; field text;
BEGIN
 IF s !~ '^r20-v2-test-ledger-' OR octet_length(body)>16384 THEN RAISE EXCEPTION 'PREPARATION_SCOPE'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 SELECT * INTO dup FROM r20_v2_config.preparations WHERE scope=s AND request_id=k;
 IF FOUND THEN
   IF dup.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN dup.revision;
 END IF;
 SELECT * INTO h FROM r20_v2_config.preparations WHERE scope=s ORDER BY revision DESC LIMIT 1;
 IF r<>COALESCE(h.revision,0) OR prev<>COALESCE(h.event_hash,'') THEN RAISE EXCEPTION 'CAS_CONFLICT'; END IF;
 b=body::jsonb; p=b->'profile'; v=p->'values';
 IF (b->>'revision')::bigint IS DISTINCT FROM r+1 OR b->>'previous' IS DISTINCT FROM prev
 OR b->>'requestId' IS DISTINCT FROM k OR b->>'requestHash' IS DISTINCT FROM req
 OR b->>'lifecycle' IS NULL OR b->>'lifecycle' NOT IN ('GUARDADO','VALIDO')
 OR b->>'activation' IS DISTINCT FROM 'NOT_ACTIVATED' OR b->>'executionEnabled' IS DISTINCT FROM 'false'
 OR p->>'scope' IS DISTINCT FROM s OR p->>'contract_version' IS DISTINCT FROM '2'
 OR p->>'activation' IS DISTINCT FROM 'NOT_ACTIVATED'
 OR COALESCE(p->>'purpose','') NOT IN ('NORMAL','TECHNICAL_VALIDATION')
 OR (p->>'purpose'='TECHNICAL_VALIDATION' AND v->>'environment' IS DISTINCT FROM 'SHADOW')
 OR p->>'economic_timezone' IS DISTINCT FROM 'America/Santo_Domingo'
 OR p->>'configuration_hash' IS NULL OR p->>'configuration_hash' !~ '^[a-f0-9]{64}$'
 OR jsonb_typeof(v) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'PREPARATION_CONTRACT'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(v))<>7 OR NOT v ?& ARRAY['logical_capital_usd','allocation_usd',
 'requested_allocation_leverage','risk_per_trade_pct','daily_loss_limit_pct','max_open_positions','environment']
 OR jsonb_typeof(v->'environment') IS DISTINCT FROM 'string'
 OR v->>'environment' NOT IN ('SHADOW','IBKR_PAPER') THEN RAISE EXCEPTION 'PREPARATION_FIELDS'; END IF;
 FOREACH field IN ARRAY ARRAY['logical_capital_usd','allocation_usd','requested_allocation_leverage','risk_per_trade_pct','daily_loss_limit_pct'] LOOP
  IF jsonb_typeof(v->field) IS DISTINCT FROM 'string' OR v->>field !~ '^[0-9]{1,96}(\.[0-9]{1,96})?$'
  THEN RAISE EXCEPTION 'PREPARATION_DECIMAL'; END IF;
  IF (v->>field)::numeric<=0 THEN RAISE EXCEPTION 'PREPARATION_POSITIVE'; END IF;
 END LOOP;
 IF (v->>'requested_allocation_leverage')::numeric<1 OR (v->>'risk_per_trade_pct')::numeric>100
 OR (v->>'daily_loss_limit_pct')::numeric>100 OR jsonb_typeof(v->'max_open_positions') IS DISTINCT FROM 'string'
 OR v->>'max_open_positions' !~ '^[0-9]{1,7}$' THEN RAISE EXCEPTION 'PREPARATION_LIMITS'; END IF;
 IF (v->>'max_open_positions')::numeric NOT BETWEEN 1 AND 1000000 THEN RAISE EXCEPTION 'PREPARATION_LIMITS'; END IF;
 IF b->>'lifecycle'='VALIDO' AND (h.payload::jsonb->>'lifecycle' IS DISTINCT FROM 'GUARDADO'
 OR p IS DISTINCT FROM h.payload::jsonb->'profile') THEN RAISE EXCEPTION 'STATE_TRANSITION'; END IF;
 INSERT INTO r20_v2_config.preparations VALUES(s,r+1,k,req,b->>'hash',body,clock_timestamp());
 RETURN r+1;
END $$;
REVOKE ALL ON r20_v2_config.preparations FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
REVOKE ALL ON FUNCTION r20_v2_config.append_preparation(text,bigint,text,text,text,text) FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT SELECT ON r20_v2_config.preparations TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT EXECUTE ON FUNCTION r20_v2_config.append_preparation(text,bigint,text,text,text,text) TO r20_lab_profiles;
COMMIT;
