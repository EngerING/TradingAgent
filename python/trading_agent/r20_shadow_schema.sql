-- Explicit isolated TEST installation; not an operational migration.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR inet_server_addr()<>'127.0.0.1'::inet
 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS r20_v2_shadow;
CREATE TABLE IF NOT EXISTS r20_v2_shadow.permissions(
 scope text NOT NULL, permission_hash text NOT NULL, payload text NOT NULL,
 PRIMARY KEY(scope,permission_hash));
CREATE TABLE IF NOT EXISTS r20_v2_shadow.events(
 scope text NOT NULL, revision bigint NOT NULL, request_id text NOT NULL,
 request_hash text NOT NULL, event_hash text NOT NULL, payload text NOT NULL,
 PRIMARY KEY(scope,revision), UNIQUE(scope,request_id));
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='r20_shadow_events_immutable') THEN
 CREATE TRIGGER r20_shadow_events_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_shadow.events
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 CREATE TRIGGER r20_shadow_permissions_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_shadow.permissions
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_shadow.commit_event(s text,k text,req text,ar bigint,ah text,
 lr bigint,lh text,profile text,body text,event text,material text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE duplicate r20_v2_shadow.events; prior r20_v2_shadow.events; h r20_v2_test.events;
 b jsonb; old jsonb; e jsonb; oe jsonb; q jsonb; p jsonb; rec jsonb; active jsonb;
 kind text; price numeric; answer json; pos jsonb; t jsonb; expected_pnl numeric;
 modeled_equity numeric; maintenance numeric; exposure numeric; exposure_cap numeric;
 expected_realized numeric; count_new integer; total_old numeric; total_new numeric;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 SELECT * INTO duplicate FROM r20_v2_shadow.events WHERE scope=s AND request_id=k;
 IF FOUND THEN
   IF duplicate.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN duplicate.payload;
 END IF;
 SELECT * INTO h FROM r20_v2_test.events WHERE scope_id=s ORDER BY revision DESC LIMIT 1;
 SELECT * INTO prior FROM r20_v2_shadow.events WHERE scope=s ORDER BY revision DESC LIMIT 1;
 IF ar IS DISTINCT FROM h.revision OR ah IS DISTINCT FROM h.event_hash
 OR lr<>COALESCE(prior.revision,0) OR lh<>COALESCE(prior.event_hash,'') THEN RAISE EXCEPTION 'CAS_CONFLICT'; END IF;
 b=body::jsonb;old=h.payload::jsonb;e=event::jsonb;
 oe=COALESCE(prior.payload::jsonb,jsonb_build_object('positions','[]'::jsonb,'trades','[]'::jsonb));
 kind=e->>'kind';q=e->'quote';p=profile::jsonb;
 IF e->>'scope' IS DISTINCT FROM s OR e->>'requestId' IS DISTINCT FROM k
 OR e->>'requestHash' IS DISTINCT FROM req OR (e->>'revision')::bigint<>lr+1
 OR e->>'previousHash' IS DISTINCT FROM lh OR (e->>'accountingRevision')::bigint<>ar+1
 OR material::jsonb IS DISTINCT FROM e-'hash'
 OR e->>'hash' IS DISTINCT FROM encode(sha256(convert_to(material,'UTF8')),'hex')
 OR e->>'classification' IS DISTINCT FROM 'SYNTHETIC_VIRTUAL_LAB'
 OR e->>'cohortStarted' IS DISTINCT FROM 'false' OR e->>'brokerOrders' IS DISTINCT FROM '0'
 OR e->>'liveEnabled' IS DISTINCT FROM 'false' OR b->'profile' IS DISTINCT FROM p
 OR jsonb_typeof(e->'positions') IS DISTINCT FROM 'array' OR jsonb_typeof(e->'trades') IS DISTINCT FROM 'array'
 OR kind NOT IN ('OPEN','MARK','CLOSE','DATA_UNAVAILABLE','MANAGEMENT_DAY','RELEASE','SIGNAL_DIAGNOSTIC')
 THEN RAISE EXCEPTION 'SHADOW_EVENT_CONTRACT'; END IF;
 IF prior.revision IS NOT NULL AND (e->>'at')::timestamptz<(oe->>'at')::timestamptz
 OR (e->>'at')::timestamptz<(old->'daily'->>'at')::timestamptz
 THEN RAISE EXCEPTION 'SHADOW_CLOCK_REGRESSION'; END IF;
 IF kind NOT IN ('DATA_UNAVAILABLE','RELEASE','SIGNAL_DIAGNOSTIC') THEN
   IF q->>'source' IS DISTINCT FROM 'SYNTHETIC_TEST_ONLY' OR q->>'connected' IS DISTINCT FROM 'true'
   OR q->>'market' IS DISTINCT FROM 'OPEN' OR (q->>'bid')::numeric<=0 OR (q->>'ask')::numeric<(q->>'bid')::numeric
   OR q->>'evidence_hash' !~ '^[a-f0-9]{64}$'
   OR (e->>'at')::timestamptz-(q->>'at')::timestamptz NOT BETWEEN interval '0 seconds' AND interval '30 seconds'
   THEN RAISE EXCEPTION 'SHADOW_QUOTE_INVALID'; END IF;
   price=((q->>'bid')::numeric+(q->>'ask')::numeric)/2;
 END IF;
 IF kind IN ('DATA_UNAVAILABLE','SIGNAL_DIAGNOSTIC') THEN
   IF b IS DISTINCT FROM old OR e->'positions' IS DISTINCT FROM oe->'positions'
   OR e->'trades' IS DISTINCT FROM oe->'trades' THEN RAISE EXCEPTION 'INVALID_DATA_CANNOT_FILL'; END IF;
 ELSE
   IF NOT (e->'trades') @> (oe->'trades') THEN RAISE EXCEPTION 'TRADE_HISTORY_IMMUTABLE'; END IF;
   IF (SELECT count(*)<>count(DISTINCT x->>'position_id') FROM jsonb_array_elements(e->'positions') x)
   OR (SELECT count(*)<>count(DISTINCT x->>'position_id') FROM jsonb_array_elements(e->'trades') x)
   THEN RAISE EXCEPTION 'POSITION_DUPLICATED'; END IF;
   -- Full persisted inventory must agree with the accounting ledger.
   IF (SELECT COALESCE(jsonb_agg(x->>'position_id' ORDER BY x->>'position_id'),'[]'::jsonb) FROM jsonb_array_elements(e->'positions') x)
   IS DISTINCT FROM (SELECT COALESCE(jsonb_agg(x->>0 ORDER BY x->>0),'[]'::jsonb) FROM jsonb_array_elements(b->'open_gross') x)
   THEN RAISE EXCEPTION 'SHADOW_INVENTORY_MISMATCH'; END IF;
   SELECT COALESCE(sum((x->>'amount')::numeric),0) INTO total_old FROM jsonb_array_elements(old->'costs') x;
   SELECT COALESCE(sum((x->>'amount')::numeric),0) INTO total_new FROM jsonb_array_elements(b->'costs') x;
   IF kind IN ('OPEN','MARK','CLOSE','MANAGEMENT_DAY') AND total_new IS DISTINCT FROM total_old
   THEN RAISE EXCEPTION 'SHADOW_COST_CONSERVATION'; END IF;
 END IF;
 IF kind='OPEN' THEN
   IF NOT EXISTS(SELECT 1 FROM r20_v2_shadow.permissions WHERE scope=s
     AND payload::jsonb->>'classification'='SYNTHETIC_TEST_ONLY'
     AND (e->>'at')::timestamptz>=(payload::jsonb->>'start')::timestamptz
     AND (e->>'at')::timestamptz<(payload::jsonb->>'end')::timestamptz)
   THEN RAISE EXCEPTION 'SHADOW_PERMISSION_REQUIRED'; END IF;
   SELECT payload::jsonb->'profile' INTO active FROM r20_v2_config.events WHERE scope=s
     AND payload::jsonb->>'lifecycle'='ACTIVATED_FOR_SHADOW' ORDER BY revision DESC LIMIT 1;
   SELECT x INTO pos FROM jsonb_array_elements(e->'positions') x WHERE NOT (oe->'positions') @> jsonb_build_array(x);
   SELECT payload::jsonb INTO rec FROM r20_v2_admission.receipts WHERE scope=s AND request_id=pos->>'reservation';
   PERFORM r20_v2_admission.check_plan(s,rec,p,(e->>'at')::timestamptz);
   IF pos IS NULL OR rec IS NULL OR active IS DISTINCT FROM pos->'entry_profile' OR active IS DISTINCT FROM p
   OR (e->>'at')::timestamptz NOT BETWEEN (p->>'effective_from')::timestamptz AND (p->>'effective_until')::timestamptz
   OR (e->>'at')::timestamptz>=(p->>'effective_until')::timestamptz
   OR (e->>'at')::timestamptz-(rec->'signal'->>'signal_at')::timestamptz NOT BETWEEN interval '0 seconds' AND interval '180 seconds'
   OR old->'daily'->>'loss_blocked' IS DISTINCT FROM 'false'
   OR jsonb_array_length(old->'daily'->'operational_blocks')<>0
   OR NOT (e->'positions') @> (oe->'positions')
   OR jsonb_array_length(e->'positions')<>jsonb_array_length(oe->'positions')+1
   OR e->'trades' IS DISTINCT FROM oe->'trades'
   OR b->'realized_gross' IS DISTINCT FROM old->'realized_gross'
   OR (pos->>'entry_price')::numeric IS DISTINCT FROM price
   OR (pos->>'quantity')::numeric IS DISTINCT FROM (rec->'assessment'->>'quantity')::numeric
   OR pos->>'position_id' IS DISTINCT FROM rec->'signal'->>'signal_id'
   OR pos->>'side' IS DISTINCT FROM rec->'signal'->>'side'
   OR pos->>'engine_hash' IS DISTINCT FROM rec->'signal'->>'engine_hash'
   OR (pos->>'cost_total')::numeric IS DISTINCT FROM (rec->'assessment'->>'estimated_costs')::numeric
   OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(old->'daily'->'pending_terms') x WHERE x->>'position_id'=pos->>'position_id')
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(b->'daily'->'pending_terms') x WHERE x->>'position_id'=pos->>'position_id')
   THEN RAISE EXCEPTION 'SHADOW_OPEN_CERTIFICATE'; END IF;
   IF (pos->>'stop')::numeric IS DISTINCT FROM price-(CASE WHEN pos->>'side'='LONG' THEN 1 ELSE -1 END)*(rec->'signal'->>'stop_distance')::numeric
   OR (pos->>'target')::numeric IS DISTINCT FROM price+(CASE WHEN pos->>'side'='LONG' THEN 1 ELSE -1 END)*2*(rec->'signal'->>'stop_distance')::numeric
   OR (pos->>'target')::numeric<=0 THEN RAISE EXCEPTION 'SHADOW_PROTECTION_INVALID'; END IF;
 ELSIF kind IN ('MARK','CLOSE') THEN
   SELECT (old->'profile'->>'capital_base_usd')::numeric+(old->>'realized_gross')::numeric-total_old+
     COALESCE(sum((CASE WHEN x->>'side'='LONG' THEN 1 ELSE -1 END)*(x->>'quantity')::numeric*(price-(x->>'entry_price')::numeric)),0),
     COALESCE(sum((x->>'quantity')::numeric*price*(x->>'maintenance_fraction')::numeric),0),
     COALESCE(sum((x->>'quantity')::numeric*price),0),min((x->>'hard_exposure_limit')::numeric)
     INTO modeled_equity,maintenance,exposure,exposure_cap FROM jsonb_array_elements(oe->'positions') x;
   expected_realized=(old->>'realized_gross')::numeric;
   FOR pos IN SELECT * FROM jsonb_array_elements(oe->'positions') LOOP
     expected_pnl=(CASE WHEN pos->>'side'='LONG' THEN 1 ELSE -1 END)*(pos->>'quantity')::numeric*(price-(pos->>'entry_price')::numeric);
     IF (e->'positions') @> jsonb_build_array(pos) THEN
       IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(b->'open_gross') x WHERE x->>0=pos->>'position_id' AND (x->>1)::numeric=expected_pnl)
       THEN RAISE EXCEPTION 'SHADOW_MARK_MISMATCH'; END IF;
     ELSE
       SELECT x INTO t FROM jsonb_array_elements(e->'trades') x WHERE x->>'position_id'=pos->>'position_id';
       IF t IS NULL OR t->'position' IS DISTINCT FROM pos OR (t->>'gross')::numeric IS DISTINCT FROM expected_pnl
       OR (t->>'exit_price')::numeric IS DISTINCT FROM price OR t->'exit_quote' IS DISTINCT FROM q
       OR (t->>'net')::numeric IS DISTINCT FROM expected_pnl-(pos->>'cost_total')::numeric
       OR t->>'reason' NOT IN ('STOP_LOSS','TAKE_PROFIT','MODELED_MARGIN_DEFICIT','HARD_EXPOSURE_LIMIT','EMERGENCY_DEFENSIVE_EXIT')
       THEN RAISE EXCEPTION 'SHADOW_CLOSE_CERTIFICATE'; END IF;
       IF t->>'reason'='STOP_LOSS' AND NOT (CASE WHEN pos->>'side'='LONG' THEN price<=(pos->>'stop')::numeric ELSE price>=(pos->>'stop')::numeric END)
       OR t->>'reason'='TAKE_PROFIT' AND NOT (CASE WHEN pos->>'side'='LONG' THEN price>=(pos->>'target')::numeric ELSE price<=(pos->>'target')::numeric END)
       OR t->>'reason'='MODELED_MARGIN_DEFICIT' AND modeled_equity>maintenance
       OR t->>'reason'='HARD_EXPOSURE_LIMIT' AND exposure<=exposure_cap
       OR t->>'reason'='EMERGENCY_DEFENSIVE_EXIT' AND NOT (old->'daily'->'operational_blocks') @> '["EMERGENCY_STOP"]'::jsonb
       THEN RAISE EXCEPTION 'SHADOW_EXIT_NOT_REACHED'; END IF;
       expected_realized=expected_realized+expected_pnl;
     END IF;
   END LOOP;
   IF (b->>'realized_gross')::numeric IS DISTINCT FROM expected_realized
   OR b->'daily'->'pending_terms' IS DISTINCT FROM old->'daily'->'pending_terms'
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(e->'positions') x WHERE NOT (oe->'positions') @> jsonb_build_array(x))
   OR jsonb_array_length(e->'trades')-jsonb_array_length(oe->'trades')
     <>jsonb_array_length(oe->'positions')-jsonb_array_length(e->'positions')
   THEN RAISE EXCEPTION 'SHADOW_INVENTORY_MUTATION'; END IF;
 ELSIF kind='MANAGEMENT_DAY' THEN
   IF e->'positions' IS DISTINCT FROM oe->'positions' OR e->'trades' IS DISTINCT FROM oe->'trades'
   OR b->'costs' IS DISTINCT FROM old->'costs' OR b->'open_gross' IS DISTINCT FROM old->'open_gross'
   OR b->'realized_gross' IS DISTINCT FROM old->'realized_gross'
   OR b->'daily'->>'entry_profile_valid' IS DISTINCT FROM 'false'
   THEN RAISE EXCEPTION 'MANAGEMENT_ONLY'; END IF;
 ELSIF kind='RELEASE' THEN
   IF e->'positions' IS DISTINCT FROM oe->'positions' OR e->'trades' IS DISTINCT FROM oe->'trades'
   OR b->'open_gross' IS DISTINCT FROM old->'open_gross' OR b->'realized_gross' IS DISTINCT FROM old->'realized_gross'
   OR NOT (old->'costs') @> (b->'costs') OR NOT (old->'daily'->'pending_terms') @> (b->'daily'->'pending_terms')
   OR jsonb_array_length(old->'daily'->'pending_terms')<>jsonb_array_length(b->'daily'->'pending_terms')+1
   THEN RAISE EXCEPTION 'RELEASE_PENDING_ONLY'; END IF;
 END IF;
 answer=r20_v2_test.append_state(s,'shadow-'||k,ar,ah,(p->>'configuration_version')::bigint,p->>'configuration_hash',profile,body);
 IF answer->>'hash' IS DISTINCT FROM e->>'accountingHash' THEN RAISE EXCEPTION 'SHADOW_ACCOUNTING_HASH'; END IF;
 INSERT INTO r20_v2_shadow.events VALUES(s,lr+1,k,req,e->>'hash',event);
 RETURN event;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA r20_v2_shadow FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA r20_v2_shadow FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT USAGE ON SCHEMA r20_v2_shadow TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT SELECT ON ALL TABLES IN SCHEMA r20_v2_shadow TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT EXECUTE ON FUNCTION r20_v2_shadow.commit_event(text,text,text,bigint,text,bigint,text,text,text,text,text) TO r20_lab_shadow;
COMMIT;
