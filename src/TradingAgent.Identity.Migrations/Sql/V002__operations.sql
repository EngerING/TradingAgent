-- Privileged functions have closed inputs, no dynamic SQL and a fixed trusted search_path.
CREATE FUNCTION app_security.audit(p_actor uuid,p_action text,p_resource uuid,p_outcome text,p_session uuid DEFAULT NULL)
RETURNS void LANGUAGE sql SET search_path=pg_catalog,app_security AS $$
 INSERT INTO app_security.security_audit_events(actor_id,action,resource_id,outcome,session_audit_id)
 VALUES(p_actor,p_action,p_resource,p_outcome,p_session);
$$;
CREATE FUNCTION app_security.session_valid(p_hash bytea,p_now timestamptz)
RETURNS boolean LANGUAGE sql VOLATILE SET search_path=pg_catalog,app_security AS $$
 SELECT EXISTS(SELECT 1 FROM app_security.web_sessions s JOIN app_security.app_users u USING(app_user_id)
 WHERE s.reference_hash=p_hash AND u.status='ACTIVE' AND s.revoked_at IS NULL AND s.authz_version=u.authz_version
 AND s.identity_issuer=u.identity_issuer AND s.identity_subject=u.identity_subject AND s.assurance_level=2
 AND s.expires_at>p_now AND s.idle_until>p_now);
$$;
CREATE FUNCTION app_security.permitted(p_user uuid,p_kind text,p_resource uuid,p_env text,p_cap text,p_now timestamptz)
RETURNS boolean LANGUAGE sql VOLATILE SET search_path=pg_catalog,app_security AS $$
 SELECT EXISTS(SELECT 1 FROM app_security.user_roles r JOIN app_security.role_permissions p ON p.role_name=r.role_name
 WHERE r.app_user_id=p_user AND r.revoked_at IS NULL AND r.expires_at>p_now AND p.policy_version=1 AND p.capability=p_cap)
 AND EXISTS(SELECT 1 FROM app_security.resource_grants g WHERE g.app_user_id=p_user AND g.resource_kind=p_kind
 AND g.resource_id=p_resource AND g.environment=p_env AND g.capability=p_cap AND g.revoked_at IS NULL AND g.expires_at>p_now);
$$;
CREATE FUNCTION app_security.bootstrap(p_issuer text,p_subject uuid) RETURNS uuid
LANGUAGE plpgsql SET search_path=pg_catalog,app_security AS $$
DECLARE v_user uuid:=gen_random_uuid(); v_domain uuid;
BEGIN
 SELECT security_domain INTO v_domain FROM app_security.settings WHERE NOT bootstrapped FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'bootstrap closed' USING ERRCODE='42501'; END IF;
 INSERT INTO app_security.app_users(app_user_id,identity_issuer,identity_subject,status) VALUES(v_user,p_issuer,p_subject,'ACTIVE');
 INSERT INTO app_security.user_roles VALUES(gen_random_uuid(),v_user,'Administrator',v_user,clock_timestamp(),clock_timestamp()+interval '1 year',NULL,NULL);
 INSERT INTO app_security.resource_grants VALUES(gen_random_uuid(),v_user,'Platform',v_domain,'Paper','ManageSecurity',v_user,clock_timestamp(),clock_timestamp()+interval '1 year',NULL,NULL);
 UPDATE app_security.settings SET bootstrapped=true;
 PERFORM app_security.audit(v_user,'Bootstrap',v_domain,'Success'); RETURN v_user;
END $$;
-- Owner-only out-of-band scope initialization. It grants no financial execution capability.
CREATE FUNCTION app_security.owner_scope(p_user uuid,p_env text) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,app_security AS $$
DECLARE v_domain uuid;
BEGIN
 PERFORM 1 FROM app_security.app_users WHERE app_user_id=p_user FOR UPDATE;
 IF p_env IS NULL OR p_env NOT IN ('Paper','Live') OR NOT EXISTS(SELECT 1 FROM app_security.app_users WHERE app_user_id=p_user AND status='ACTIVE')
 OR NOT EXISTS(SELECT 1 FROM app_security.user_roles WHERE app_user_id=p_user AND role_name='Administrator' AND revoked_at IS NULL AND expires_at>clock_timestamp()) THEN
 RAISE EXCEPTION 'invalid scope' USING ERRCODE='42501'; END IF;
 SELECT security_domain INTO v_domain FROM app_security.settings;
 INSERT INTO app_security.resource_grants VALUES(gen_random_uuid(),p_user,'Platform',v_domain,p_env,'ManageSecurity',p_user,clock_timestamp(),clock_timestamp()+interval '1 year',NULL,NULL);
 UPDATE app_security.app_users SET authz_version=authz_version+1,updated_at=clock_timestamp() WHERE app_user_id=p_user;
 UPDATE app_security.web_sessions SET revoked_at=clock_timestamp(),row_version=row_version+1 WHERE app_user_id=p_user AND revoked_at IS NULL;
 PERFORM app_security.audit(p_user,'OwnerScope',v_domain,'Success');
END $$;
CREATE FUNCTION app_security.create_session(p_hash bytea,p_issuer text,p_subject uuid,p_provider uuid,p_aal integer,p_verified timestamptz,p_expiry timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_user app_security.app_users%ROWTYPE; v_now timestamptz; v_id uuid:=gen_random_uuid(); v_end timestamptz; v_idle timestamptz;
BEGIN
 SELECT * INTO v_user FROM app_security.app_users WHERE identity_issuer=p_issuer AND identity_subject=p_subject FOR UPDATE;
 v_now:=clock_timestamp();
 IF NOT FOUND OR p_hash IS NULL OR octet_length(p_hash)<>32 OR p_issuer IS NULL OR p_subject IS NULL OR p_provider IS NULL
 OR p_provider='00000000-0000-0000-0000-000000000000' OR p_aal IS NULL OR p_verified IS NULL OR p_expiry IS NULL
 OR v_user.status<>'ACTIVE' OR p_aal<>2 OR p_verified>v_now OR p_verified<v_now-interval '5 minutes' OR p_expiry<=v_now THEN
 RETURN jsonb_build_object('outcome','Denied'); END IF;
 v_end:=least(p_expiry,v_now+interval '12 hours'); v_idle:=least(v_end,v_now+interval '30 minutes');
 INSERT INTO app_security.web_sessions(session_audit_id,reference_hash,app_user_id,identity_issuer,identity_subject,provider_session_id,assurance_level,verified_at,created_at,expires_at,idle_until,authz_version)
 VALUES(v_id,p_hash,v_user.app_user_id,p_issuer,p_subject,p_provider,p_aal,p_verified,v_now,v_end,v_idle,v_user.authz_version);
 PERFORM app_security.audit(v_user.app_user_id,'SessionCreate',v_id,'Success',v_id);
 RETURN jsonb_build_object('outcome','Success','id',v_id,'user',v_user.app_user_id,'version',1,'expires',v_end,'idle',v_idle);
END $$;
CREATE FUNCTION app_security.authorize(p_hash bytea,p_kind text,p_resource uuid,p_env text,p_cap text)
RETURNS TABLE(allowed boolean,as_of timestamptz) LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_user uuid; v_session uuid; v_now timestamptz; v_allowed boolean:=false;
BEGIN
 SELECT app_user_id,session_audit_id INTO v_user,v_session FROM app_security.web_sessions WHERE reference_hash=p_hash;
 PERFORM 1 FROM app_security.app_users WHERE app_user_id=v_user FOR SHARE;
 v_now:=clock_timestamp();
 IF app_security.session_valid(p_hash,v_now) THEN
 v_allowed:=app_security.permitted(v_user,p_kind,p_resource,p_env,p_cap,v_now); END IF;
 PERFORM app_security.audit(v_user,'Authorize',p_resource,CASE WHEN v_allowed THEN 'Success' ELSE 'Denied' END,v_session);
 RETURN QUERY SELECT v_allowed,v_now;
END $$;
CREATE FUNCTION app_security.self_user(p_hash bytea) RETURNS TABLE(user_id uuid,issuer text,subject uuid,status text,version bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_user uuid;
BEGIN
 SELECT app_user_id INTO v_user FROM app_security.web_sessions WHERE reference_hash=p_hash;
 PERFORM 1 FROM app_security.app_users WHERE app_user_id=v_user FOR SHARE;
 IF app_security.session_valid(p_hash,clock_timestamp()) THEN RETURN QUERY
 SELECT u.app_user_id,u.identity_issuer,u.identity_subject,u.status,u.authz_version FROM app_security.app_users u WHERE u.app_user_id=v_user; END IF;
END $$;
CREATE FUNCTION app_security.session_change(p_hash bytea,p_action text,p_version bigint DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_user uuid; v_session app_security.web_sessions%ROWTYPE; v_now timestamptz; v_result text;
BEGIN
 IF p_action IS NULL OR p_action NOT IN ('SessionTouch','SessionRevoke') THEN RETURN jsonb_build_object('outcome','Denied'); END IF;
 SELECT app_user_id INTO v_user FROM app_security.web_sessions WHERE reference_hash=p_hash;
 PERFORM 1 FROM app_security.app_users WHERE app_user_id=v_user FOR UPDATE;
 SELECT * INTO v_session FROM app_security.web_sessions WHERE reference_hash=p_hash FOR UPDATE;
 v_now:=clock_timestamp();
 IF NOT app_security.session_valid(p_hash,v_now) THEN v_result:='Denied';
 ELSIF p_action='SessionTouch' AND p_version IS DISTINCT FROM v_session.row_version THEN v_result:='Conflict';
 ELSE
 UPDATE app_security.web_sessions SET row_version=row_version+1,
 idle_until=CASE WHEN p_action='SessionTouch' THEN least(expires_at,v_now+interval '30 minutes') ELSE idle_until END,
 revoked_at=CASE WHEN p_action='SessionRevoke' THEN v_now ELSE revoked_at END WHERE reference_hash=p_hash;
 v_result:='Success'; END IF;
 PERFORM app_security.audit(v_user,p_action,v_session.session_audit_id,v_result,v_session.session_audit_id);
 RETURN jsonb_build_object('outcome',v_result,'id',v_session.session_audit_id);
END $$;
CREATE FUNCTION app_security.admin_change(p_hash bytea,p_action text,p_target uuid,p_value text,p_resource uuid,p_kind text,p_env text,p_cap text,p_expires timestamptz,p_issuer text,p_subject uuid,p_email text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_actor uuid; v_session uuid; v_target uuid:=p_target; v_domain uuid; v_now timestamptz; v_id uuid:=gen_random_uuid();
BEGIN
 IF p_action IS NULL OR p_env IS NULL OR p_action NOT IN ('Register','Status','GrantRole','GrantResource','RevokeRole','RevokeResource') OR p_env NOT IN ('Paper','Live') THEN
 RETURN jsonb_build_object('outcome','Denied'); END IF;
 SELECT app_user_id,session_audit_id INTO v_actor,v_session FROM app_security.web_sessions WHERE reference_hash=p_hash;
 IF p_action='RevokeRole' THEN SELECT app_user_id INTO v_target FROM app_security.user_roles WHERE grant_id=p_target;
 ELSIF p_action='RevokeResource' THEN SELECT app_user_id INTO v_target FROM app_security.resource_grants WHERE grant_id=p_target; END IF;
 PERFORM 1 FROM app_security.app_users WHERE app_user_id IN (v_actor,v_target) ORDER BY app_user_id FOR UPDATE;
 v_now:=clock_timestamp(); SELECT security_domain INTO v_domain FROM app_security.settings;
 IF NOT app_security.session_valid(p_hash,v_now) OR NOT EXISTS(SELECT 1 FROM app_security.web_sessions WHERE reference_hash=p_hash AND verified_at>=v_now-interval '5 minutes')
 OR NOT app_security.permitted(v_actor,'Platform',v_domain,p_env,'ManageSecurity',v_now)
 OR (p_action IN ('Status','GrantRole','RevokeRole') AND EXISTS(
   SELECT 1 FROM app_security.resource_grants g WHERE g.app_user_id=v_target AND g.revoked_at IS NULL AND g.expires_at>v_now
   AND NOT app_security.permitted(v_actor,'Platform',v_domain,g.environment,'ManageSecurity',v_now))) THEN
 PERFORM app_security.audit(v_actor,p_action,p_target,'Denied',v_session); RETURN jsonb_build_object('outcome','Denied'); END IF;
 IF p_action='Register' THEN
  INSERT INTO app_security.app_users(app_user_id,identity_issuer,identity_subject,status,contact_email) VALUES(v_id,p_issuer,p_subject,'INVITED',p_email);
 ELSIF v_target IS NULL OR NOT EXISTS(SELECT 1 FROM app_security.app_users WHERE app_user_id=v_target) THEN
  RETURN jsonb_build_object('outcome','Denied');
 ELSIF p_action='Status' THEN
  UPDATE app_security.app_users SET status=p_value WHERE app_user_id=v_target; v_id:=v_target;
 ELSIF p_action='GrantRole' THEN
  UPDATE app_security.user_roles SET revoked_at=v_now,revoked_by=v_actor WHERE app_user_id=v_target AND role_name=p_value AND revoked_at IS NULL AND expires_at<=v_now;
  INSERT INTO app_security.user_roles VALUES(v_id,v_target,p_value,v_actor,v_now,p_expires,NULL,NULL);
 ELSIF p_action='GrantResource' THEN
  IF p_kind='Platform' AND p_resource<>v_domain THEN RETURN jsonb_build_object('outcome','Denied'); END IF;
  UPDATE app_security.resource_grants SET revoked_at=v_now,revoked_by=v_actor WHERE app_user_id=v_target AND resource_kind=p_kind AND resource_id=p_resource AND environment=p_env AND capability=p_cap AND revoked_at IS NULL AND expires_at<=v_now;
  INSERT INTO app_security.resource_grants VALUES(v_id,v_target,p_kind,p_resource,p_env,p_cap,v_actor,v_now,p_expires,NULL,NULL);
 ELSIF p_action='RevokeRole' THEN
  UPDATE app_security.user_roles SET revoked_at=v_now,revoked_by=v_actor WHERE grant_id=p_target AND revoked_at IS NULL;
  IF NOT FOUND THEN RETURN jsonb_build_object('outcome','Denied'); END IF; v_id:=p_target;
 ELSIF p_action='RevokeResource' THEN
  -- Revoking a Live grant requires the actor's Live administration scope too.
  IF NOT EXISTS(SELECT 1 FROM app_security.resource_grants WHERE grant_id=p_target AND environment=p_env) THEN RETURN jsonb_build_object('outcome','Denied'); END IF;
  UPDATE app_security.resource_grants SET revoked_at=v_now,revoked_by=v_actor WHERE grant_id=p_target AND revoked_at IS NULL;
  IF NOT FOUND THEN RETURN jsonb_build_object('outcome','Denied'); END IF; v_id:=p_target;
 END IF;
 IF p_action<>'Register' THEN
 UPDATE app_security.app_users SET authz_version=authz_version+1,updated_at=v_now WHERE app_user_id=v_target;
 UPDATE app_security.web_sessions SET revoked_at=v_now,row_version=row_version+1 WHERE app_user_id=v_target AND revoked_at IS NULL;
 END IF;
 PERFORM app_security.audit(v_actor,p_action,v_id,'Success',v_session);
 RETURN jsonb_build_object('outcome','Success','id',v_id);
END $$;
-- Audit is a global security view. Both environment scopes are required; no identity/contact/token data is returned.
CREATE FUNCTION app_security.read_audit(p_hash bytea,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app_security AS $$
DECLARE v_actor uuid; v_domain uuid; v_now timestamptz; v_events jsonb;
BEGIN
 IF p_limit IS NULL OR p_limit<1 OR p_limit>100 THEN RETURN jsonb_build_object('outcome','Denied'); END IF;
 SELECT app_user_id INTO v_actor FROM app_security.web_sessions WHERE reference_hash=p_hash;
 PERFORM 1 FROM app_security.app_users WHERE app_user_id=v_actor FOR SHARE;
 v_now:=clock_timestamp(); SELECT security_domain INTO v_domain FROM app_security.settings;
 IF NOT app_security.session_valid(p_hash,v_now) OR NOT EXISTS(SELECT 1 FROM app_security.web_sessions WHERE reference_hash=p_hash AND verified_at>=v_now-interval '5 minutes')
 OR NOT app_security.permitted(v_actor,'Platform',v_domain,'Paper','ManageSecurity',v_now)
 OR NOT app_security.permitted(v_actor,'Platform',v_domain,'Live','ManageSecurity',v_now) THEN RETURN jsonb_build_object('outcome','Denied'); END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(e)),'[]'::jsonb) INTO v_events FROM (
 SELECT event_id,action,outcome,occurred_at,correlation_id,policy_version,session_audit_id FROM app_security.security_audit_events ORDER BY occurred_at DESC,event_id DESC LIMIT p_limit) e;
 RETURN jsonb_build_object('outcome','Success','events',v_events);
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_security FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_security.create_session(bytea,text,uuid,uuid,integer,timestamptz,timestamptz) TO identity_session_issuer;
GRANT EXECUTE ON FUNCTION app_security.authorize(bytea,text,uuid,text,text),app_security.self_user(bytea),app_security.session_change(bytea,text,bigint) TO web_security_runtime;
GRANT EXECUTE ON FUNCTION app_security.admin_change(bytea,text,uuid,text,uuid,text,text,text,timestamptz,text,uuid,text) TO identity_access_admin;
GRANT EXECUTE ON FUNCTION app_security.read_audit(bytea,integer) TO identity_access_admin;
