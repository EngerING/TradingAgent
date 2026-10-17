-- TEST cluster only; not an operational migration and never journal011.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^r20_v2_test_[a-f0-9]{32}$' OR current_user<>'trading_test'
 OR inet_server_port()<>55432 OR inet_server_addr()<>'127.0.0.1'::inet
 OR (SELECT system_identifier::text FROM pg_control_system())<>'7692346685552779632'
 THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS r20_v2_admission;
CREATE TABLE IF NOT EXISTS r20_v2_admission.receipts(
 scope text NOT NULL, request_id text NOT NULL, request_hash text NOT NULL,
 signal_id text NOT NULL, accounting_revision bigint NOT NULL, payload text NOT NULL,
 PRIMARY KEY(scope,request_id),UNIQUE(scope,signal_id));
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='r20_admission_immutable') THEN
 CREATE TRIGGER r20_admission_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON r20_v2_admission.receipts
 FOR EACH STATEMENT EXECUTE FUNCTION r20_v2_test.immutable();
 END IF;
END $$;
-- Called only for an explicit phase-2 binding. Legacy NORMAL receipts stay valid.
CREATE OR REPLACE FUNCTION r20_v2_admission.check_plan(s text,rec jsonb,p jsonb,at_time timestamptz)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE plan jsonb; prep jsonb; active jsonb; v jsonb;
BEGIN
 plan=rec->'executionPlan';
 IF plan IS NULL THEN RETURN; END IF;
 SELECT payload::jsonb INTO prep FROM r20_v2_config.preparations WHERE scope=s ORDER BY revision DESC LIMIT 1;
 SELECT payload::jsonb INTO active FROM r20_v2_config.events WHERE scope=s
 AND payload::jsonb->>'lifecycle'='ACTIVATED_FOR_SHADOW' ORDER BY revision DESC LIMIT 1;
 v=prep->'profile'->'values';
 IF prep->>'lifecycle' IS DISTINCT FROM 'VALIDO'
 OR prep->'profile'->>'configuration_hash' IS DISTINCT FROM plan->>'preparationHash'
 OR prep->'profile'->>'purpose' IS DISTINCT FROM plan->>'purpose'
 OR COALESCE(plan->>'purpose','') NOT IN ('NORMAL','TECHNICAL_VALIDATION')
 OR v->>'environment' IS DISTINCT FROM 'SHADOW'
 OR at_time<(prep->'profile'->>'effective_from')::timestamptz
 OR at_time>=(prep->'profile'->>'effective_until')::timestamptz
 OR (v->>'allocation_usd')::numeric IS DISTINCT FROM (plan->>'allocation_usd')::numeric
 OR (v->>'requested_allocation_leverage')::numeric IS DISTINCT FROM (plan->>'requested_allocation_leverage')::numeric
 OR (v->>'logical_capital_usd')::numeric IS DISTINCT FROM (p->>'capital_base_usd')::numeric
 OR (v->>'risk_per_trade_pct')::numeric IS DISTINCT FROM (p->>'risk_per_trade_pct')::numeric
 OR (v->>'daily_loss_limit_pct')::numeric IS DISTINCT FROM (p->>'daily_loss_limit_pct')::numeric
 OR (v->>'max_open_positions')::integer IS DISTINCT FROM (p->>'max_open_positions')::integer
 OR active->>'contextHash' IS DISTINCT FROM plan->>'contextHash'
 OR NOT EXISTS(SELECT 1 FROM r20_v2_shadow.permissions WHERE scope=s
   AND payload::jsonb->'plan' IS NOT DISTINCT FROM plan-'contextHash'
   AND payload::jsonb->>'contextHash'=plan->>'contextHash'
   AND at_time>=(payload::jsonb->>'start')::timestamptz AND at_time<(payload::jsonb->>'end')::timestamptz)
 THEN RAISE EXCEPTION 'BOUND_SHADOW_PLAN_REQUIRED'; END IF;
 IF (rec->'assessment'->>'exposure')::numeric>(plan->>'allocation_usd')::numeric*(plan->>'requested_allocation_leverage')::numeric
 OR (rec->'assessment'->>'initial_margin')::numeric+(rec->'assessment'->>'estimated_costs')::numeric>(plan->>'allocation_usd')::numeric
 THEN RAISE EXCEPTION 'PLAN_ALLOCATION_LIMIT'; END IF;
END $$;
CREATE OR REPLACE FUNCTION r20_v2_admission.reserve(s text,k text,req text,r bigint,prev text,
 cr bigint,ch text,profile text,body text,receipt text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE duplicate r20_v2_admission.receipts; h r20_v2_test.events; c r20_v2_config.events;
 active r20_v2_config.events; b jsonb; p jsonb; old jsonb; d jsonb; od jsonb; a jsonb;
 answer json; total_risk numeric; cost numeric; pending numeric; budget numeric; eq numeric;
 new_risk jsonb; new_cost jsonb; worst numeric;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(s,0));
 SELECT * INTO duplicate FROM r20_v2_admission.receipts WHERE scope=s AND request_id=k;
 IF FOUND THEN
   IF duplicate.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN duplicate.payload;
 END IF;
 IF EXISTS(SELECT 1 FROM r20_v2_admission.receipts WHERE scope=s AND signal_id=receipt::jsonb->'signal'->>'signal_id')
 THEN RAISE EXCEPTION 'SIGNAL_ALREADY_RESERVED'; END IF;
 SELECT * INTO h FROM r20_v2_test.events WHERE scope_id=s ORDER BY revision DESC LIMIT 1;
 SELECT * INTO c FROM r20_v2_config.events WHERE scope=s ORDER BY revision DESC LIMIT 1;
 IF r IS DISTINCT FROM h.revision OR prev IS DISTINCT FROM h.event_hash THEN RAISE EXCEPTION 'CAS_CONFLICT'; END IF;
 IF cr IS DISTINCT FROM c.revision OR ch IS DISTINCT FROM c.event_hash THEN RAISE EXCEPTION 'CONFIG_CAS_CONFLICT'; END IF;
 SELECT * INTO active FROM r20_v2_config.events WHERE scope=s AND payload::jsonb->>'lifecycle'='ACTIVATED_FOR_SHADOW' ORDER BY revision DESC LIMIT 1;
 IF active.revision IS NULL OR active.payload::jsonb->'profile' IS DISTINCT FROM profile::jsonb THEN RAISE EXCEPTION 'PROFILE_REQUIRED'; END IF;
 b=body::jsonb;p=profile::jsonb;old=h.payload::jsonb;d=b->'daily';od=old->'daily';a=receipt::jsonb->'assessment';
 PERFORM r20_v2_admission.check_plan(s,receipt::jsonb,p,(d->>'at')::timestamptz);
 IF b->'profile' IS DISTINCT FROM p OR (d->>'at')::timestamptz<(p->>'effective_from')::timestamptz
 OR (d->>'at')::timestamptz>=(p->>'effective_until')::timestamptz
 OR d->>'day_id' IS DISTINCT FROM to_char((d->>'at')::timestamptz AT TIME ZONE 'America/Santo_Domingo','YYYY-MM-DD')
 OR d->>'day_id' IS DISTINCT FROM od->>'day_id' THEN RAISE EXCEPTION 'PROFILE_EXPIRED_OR_DAY_UNVERIFIED'; END IF;
 IF (od->>'loss_blocked')::boolean OR jsonb_array_length(od->'operational_blocks')>0
 OR NOT (od->>'inventory_verified')::boolean THEN RAISE EXCEPTION 'DAILY_OR_OPERATIONAL_BLOCK'; END IF;
 IF b->'realized_gross' IS DISTINCT FROM old->'realized_gross'
 OR b->'open_gross' IS DISTINCT FROM old->'open_gross'
 OR d->'open_terms' IS DISTINCT FROM od->'open_terms'
 OR NOT (b->'costs') @> (old->'costs')
 OR jsonb_array_length(b->'costs')<>jsonb_array_length(old->'costs')+1
 OR NOT (d->'pending_terms') @> (od->'pending_terms')
 OR jsonb_array_length(d->'pending_terms')<>jsonb_array_length(od->'pending_terms')+1
 THEN RAISE EXCEPTION 'INVENTORY_OR_RESERVE_MUTATION'; END IF;
 IF jsonb_array_length(d->'open_terms')+jsonb_array_length(d->'pending_terms')>(p->>'max_open_positions')::integer
 THEN RAISE EXCEPTION 'POSITION_LIMIT'; END IF;
 cost=(a->>'estimated_costs')::numeric;
 SELECT x INTO new_cost FROM jsonb_array_elements(b->'costs') x WHERE x->>'cost_id'='reservation-'||k;
 SELECT x INTO new_risk FROM jsonb_array_elements(d->'pending_terms') x WHERE x->>'position_id'=receipt::jsonb->'signal'->>'signal_id';
 SELECT max((x->>'candidate_loss')::numeric) INTO worst FROM jsonb_array_elements(a->'stress') x;
 IF new_cost IS NULL OR new_risk IS NULL OR worst IS NULL
 OR (new_cost->>'amount')::numeric IS DISTINCT FROM cost
 OR new_cost->>'status' IS DISTINCT FROM 'RESERVED' OR new_cost->>'provenance' IS DISTINCT FROM 'ESTIMATED'
 OR (new_risk->>'total_loss')::numeric IS DISTINCT FROM worst-cost OR worst<cost
 OR (a->>'quantity')::numeric<=0 OR (receipt::jsonb->'signal'->>'price')::numeric<=0
 OR (a->>'price_risk')::numeric IS DISTINCT FROM (a->>'quantity')::numeric*(receipt::jsonb->'signal'->>'stop_distance')::numeric
 OR receipt::jsonb->>'requestId' IS DISTINCT FROM k OR receipt::jsonb->>'requestHash' IS DISTINCT FROM req
 THEN RAISE EXCEPTION 'RESERVATION_CERTIFICATE'; END IF;
 SELECT COALESCE(sum((x->>'total_loss')::numeric),0) INTO pending FROM jsonb_array_elements(d->'pending_terms') x;
 eq=(od->>'current_equity')::numeric-cost;
 SELECT LEAST((d->>'budget')::numeric,COALESCE(min((payload::jsonb->>'dailyBudget')::numeric),(d->>'budget')::numeric))
 INTO budget FROM r20_v2_config.events WHERE scope=s AND payload::jsonb->>'day'=d->>'day_id'
 AND payload::jsonb->>'lifecycle'='ACTIVATED_FOR_SHADOW';
 SELECT GREATEST(0,(d->>'reference')::numeric-eq)+pending+
 COALESCE(sum(GREATEST(0,(x->>'current_net')::numeric-(x->>'stressed_net')::numeric)),0)
 INTO total_risk FROM jsonb_array_elements(d->'open_terms') x;
 IF cost IS NULL OR cost<0 OR eq IS DISTINCT FROM (d->>'current_equity')::numeric OR total_risk>budget
 OR pending<0 OR ((a->>'net_target')::numeric<=0 AND COALESCE(receipt::jsonb->'executionPlan'->>'purpose','NORMAL')<>'TECHNICAL_VALIDATION')
 OR (a->>'admitted')::boolean IS DISTINCT FROM true
 OR a->>'profile_hash' IS DISTINCT FROM p->>'configuration_hash'
 OR receipt::jsonb->>'classification' IS DISTINCT FROM 'SYNTHETIC_RESERVATION_ONLY'
 OR receipt::jsonb->'signal'->>'source' IS DISTINCT FROM 'SYNTHETIC_TEST_ONLY'
 THEN RAISE EXCEPTION 'RESERVATION_BUDGET_OR_CONTRACT'; END IF;
 answer=r20_v2_test.append_state(s,k,r,prev,(p->>'configuration_version')::bigint,p->>'configuration_hash',profile,body);
 IF (answer->>'revision')::bigint IS DISTINCT FROM (receipt::jsonb->>'accountingRevision')::bigint
 OR answer->>'hash' IS DISTINCT FROM receipt::jsonb->>'accountingHash' THEN RAISE EXCEPTION 'RECEIPT_INTEGRITY'; END IF;
 INSERT INTO r20_v2_admission.receipts VALUES(s,k,req,receipt::jsonb->'signal'->>'signal_id',r+1,receipt);
 RETURN receipt;
END $$;
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['r20_lab_reader','r20_lab_profiles','r20_lab_shadow','r20_lab_paper_disabled'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN EXECUTE format('CREATE ROLE %I NOLOGIN',r); END IF;
 END LOOP;
END $$;
ALTER FUNCTION r20_v2_config.append_event(text,bigint,text,text,text,text,text) SECURITY DEFINER;
ALTER FUNCTION r20_v2_config.append_event(text,bigint,text,text,text,text,text) SET search_path=pg_catalog;
REVOKE ALL ON ALL TABLES IN SCHEMA r20_v2_test,r20_v2_config,r20_v2_admission FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA r20_v2_test,r20_v2_config,r20_v2_admission FROM PUBLIC,r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT USAGE ON SCHEMA r20_v2_test,r20_v2_config,r20_v2_admission TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT SELECT ON ALL TABLES IN SCHEMA r20_v2_test,r20_v2_config,r20_v2_admission TO r20_lab_reader,r20_lab_profiles,r20_lab_shadow,r20_lab_paper_disabled;
GRANT EXECUTE ON FUNCTION r20_v2_config.append_event(text,bigint,text,text,text,text,text) TO r20_lab_profiles;
GRANT EXECUTE ON FUNCTION r20_v2_admission.reserve(text,text,text,bigint,text,bigint,text,text,text,text) TO r20_lab_shadow;
COMMIT;
