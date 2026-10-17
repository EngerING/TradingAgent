CREATE SCHEMA IF NOT EXISTS paper_lab;
CREATE TABLE paper_lab.states (
 account_key text PRIMARY KEY CHECK(account_key ~ '^PAPER-[a-f0-9]{16}$'),
 revision bigint NOT NULL CHECK(revision > 0),
 payload jsonb NOT NULL CHECK(payload ? 'environment' AND payload ? 'live_enabled' AND payload->>'environment'='PAPER_TRADING' AND payload->>'live_enabled'='false'),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE paper_lab.events (
 account_key text NOT NULL REFERENCES paper_lab.states(account_key),
 revision bigint NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
 payload jsonb NOT NULL, PRIMARY KEY(account_key,revision)
);
CREATE TABLE paper_lab.experience (
 id text PRIMARY KEY, account_key text NOT NULL REFERENCES paper_lab.states(account_key),
 category text NOT NULL CHECK(category IN ('PAPER_DIAGNOSTIC','PAPER_STRATEGY')),
 payload jsonb NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now()
);
