-- Executed only as identity_migration_owner in an explicitly marked disposable database.
REVOKE ALL ON SCHEMA app_security FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app_security REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE app_security.settings (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), policy_version integer NOT NULL CHECK(policy_version=1),
 security_domain uuid NOT NULL CHECK(security_domain <> '00000000-0000-0000-0000-000000000000'), bootstrapped boolean NOT NULL DEFAULT false
);
INSERT INTO app_security.settings VALUES(true,1,gen_random_uuid(),false);
CREATE TABLE app_security.app_users (
 app_user_id uuid PRIMARY KEY CHECK(app_user_id <> '00000000-0000-0000-0000-000000000000'),
 identity_issuer text NOT NULL CHECK(length(identity_issuer) BETWEEN 9 AND 2048 AND identity_issuer ~ '^https://[^[:space:]?#@]+$'),
 identity_subject uuid NOT NULL CHECK(identity_subject <> '00000000-0000-0000-0000-000000000000'),
 status text NOT NULL CHECK(status IN ('INVITED','ACTIVE','DISABLED')), authz_version bigint NOT NULL DEFAULT 1 CHECK(authz_version>0),
 contact_email text CHECK(length(contact_email)<=320), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(identity_issuer,identity_subject)
);
CREATE TABLE app_security.role_permissions (
 policy_version integer NOT NULL CHECK(policy_version=1), role_name text NOT NULL CHECK(role_name IN ('Viewer','Researcher','Operator','Administrator')),
 capability text NOT NULL CHECK(capability IN ('Read','ManageResearch','Supervise','ManageSecurity')),
 PRIMARY KEY(policy_version,role_name,capability)
);
INSERT INTO app_security.role_permissions VALUES
 (1,'Viewer','Read'),(1,'Researcher','Read'),(1,'Researcher','ManageResearch'),
 (1,'Operator','Read'),(1,'Operator','Supervise'),(1,'Administrator','Read'),(1,'Administrator','ManageSecurity');
CREATE TABLE app_security.user_roles (
 grant_id uuid PRIMARY KEY, app_user_id uuid NOT NULL REFERENCES app_security.app_users,
 role_name text NOT NULL CHECK(role_name IN ('Viewer','Researcher','Operator','Administrator')),
 granted_by uuid NOT NULL REFERENCES app_security.app_users, granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL, revoked_at timestamptz, revoked_by uuid REFERENCES app_security.app_users,
 CHECK(expires_at>granted_at), CHECK((revoked_at IS NULL)=(revoked_by IS NULL)), CHECK(revoked_at IS NULL OR revoked_at>=granted_at)
);
CREATE UNIQUE INDEX role_active_unique ON app_security.user_roles(app_user_id,role_name) WHERE revoked_at IS NULL;
CREATE INDEX role_actor ON app_security.user_roles(granted_by);
CREATE INDEX role_revoker ON app_security.user_roles(revoked_by);
CREATE TABLE app_security.resource_grants (
 grant_id uuid PRIMARY KEY, app_user_id uuid NOT NULL REFERENCES app_security.app_users,
 resource_kind text NOT NULL CHECK(resource_kind IN ('Account','Study','Experiment','Strategy','Platform')),
 resource_id uuid NOT NULL CHECK(resource_id <> '00000000-0000-0000-0000-000000000000'),
 environment text NOT NULL CHECK(environment IN ('Paper','Live')),
 capability text NOT NULL CHECK(capability IN ('Read','ManageResearch','Supervise','ManageSecurity')),
 granted_by uuid NOT NULL REFERENCES app_security.app_users, granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL, revoked_at timestamptz, revoked_by uuid REFERENCES app_security.app_users,
 CHECK(expires_at>granted_at), CHECK((revoked_at IS NULL)=(revoked_by IS NULL)), CHECK(revoked_at IS NULL OR revoked_at>=granted_at),
 CHECK((capability='ManageSecurity')=(resource_kind='Platform'))
);
CREATE UNIQUE INDEX resource_active_unique ON app_security.resource_grants(app_user_id,resource_kind,resource_id,environment,capability) WHERE revoked_at IS NULL;
CREATE INDEX resource_actor ON app_security.resource_grants(granted_by);
CREATE INDEX resource_revoker ON app_security.resource_grants(revoked_by);
CREATE TABLE app_security.web_sessions (
 session_audit_id uuid PRIMARY KEY, reference_hash bytea NOT NULL UNIQUE CHECK(octet_length(reference_hash)=32),
 app_user_id uuid NOT NULL REFERENCES app_security.app_users, identity_issuer text NOT NULL, identity_subject uuid NOT NULL,
 provider_session_id uuid NOT NULL CHECK(provider_session_id <> '00000000-0000-0000-0000-000000000000'),
 assurance_level integer NOT NULL CHECK(assurance_level IN (1,2)), verified_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), expires_at timestamptz NOT NULL, idle_until timestamptz NOT NULL,
 revoked_at timestamptz, authz_version bigint NOT NULL CHECK(authz_version>0), row_version bigint NOT NULL DEFAULT 1 CHECK(row_version>0),
 encrypted_access_token bytea CHECK(encrypted_access_token IS NULL), encrypted_refresh_token bytea CHECK(encrypted_refresh_token IS NULL),
 token_key_id text CHECK(token_key_id IS NULL),
 FOREIGN KEY(identity_issuer,identity_subject) REFERENCES app_security.app_users(identity_issuer,identity_subject),
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '12 hours'),
 CHECK(idle_until<=expires_at AND idle_until>created_at), CHECK(verified_at<=created_at AND verified_at>=created_at-interval '5 minutes')
);
CREATE INDEX session_by_user ON app_security.web_sessions(app_user_id);
CREATE TABLE app_security.security_audit_events (
 event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor_id uuid REFERENCES app_security.app_users,
 action text NOT NULL CHECK(action IN ('Bootstrap','OwnerScope','Register','Status','GrantRole','GrantResource','RevokeRole','RevokeResource','SessionCreate','SessionTouch','SessionRevoke','Authorize')),
 resource_id uuid, outcome text NOT NULL CHECK(outcome IN ('Success','Denied','Conflict')),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(), correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
 policy_version integer NOT NULL DEFAULT 1 CHECK(policy_version=1), session_audit_id uuid REFERENCES app_security.web_sessions
);
CREATE INDEX audit_actor ON app_security.security_audit_events(actor_id);
CREATE INDEX audit_session ON app_security.security_audit_events(session_audit_id);
CREATE FUNCTION app_security.immutable_history() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app_security AS $$
BEGIN
 IF TG_TABLE_NAME='app_users' THEN
  IF (NEW.app_user_id,NEW.identity_issuer,NEW.identity_subject,NEW.created_at) IS DISTINCT FROM
     (OLD.app_user_id,OLD.identity_issuer,OLD.identity_subject,OLD.created_at) OR NEW.authz_version<OLD.authz_version THEN
   RAISE EXCEPTION 'identity immutable' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME IN ('user_roles','resource_grants') THEN
  IF (to_jsonb(NEW)-'revoked_at'-'revoked_by') IS DISTINCT FROM (to_jsonb(OLD)-'revoked_at'-'revoked_by') OR
    OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL THEN RAISE EXCEPTION 'grant immutable' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='web_sessions' THEN
  IF (to_jsonb(NEW)-'idle_until'-'revoked_at'-'row_version') IS DISTINCT FROM (to_jsonb(OLD)-'idle_until'-'revoked_at'-'row_version') OR
     OLD.revoked_at IS NOT NULL OR NEW.row_version<>OLD.row_version+1 THEN RAISE EXCEPTION 'session immutable' USING ERRCODE='23514'; END IF;
 ELSE RAISE EXCEPTION 'append only' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER user_identity_immutable BEFORE UPDATE ON app_security.app_users FOR EACH ROW EXECUTE FUNCTION app_security.immutable_history();
CREATE TRIGGER role_immutable BEFORE UPDATE ON app_security.user_roles FOR EACH ROW EXECUTE FUNCTION app_security.immutable_history();
CREATE TRIGGER resource_immutable BEFORE UPDATE ON app_security.resource_grants FOR EACH ROW EXECUTE FUNCTION app_security.immutable_history();
CREATE TRIGGER session_immutable BEFORE UPDATE ON app_security.web_sessions FOR EACH ROW EXECUTE FUNCTION app_security.immutable_history();
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON app_security.security_audit_events FOR EACH STATEMENT EXECUTE FUNCTION app_security.immutable_history();
REVOKE ALL ON ALL TABLES IN SCHEMA app_security FROM PUBLIC;
GRANT USAGE ON SCHEMA app_security TO web_security_runtime,identity_session_issuer,identity_access_admin,identity_security_reader;
GRANT SELECT ON app_security.role_permissions TO identity_security_reader;
