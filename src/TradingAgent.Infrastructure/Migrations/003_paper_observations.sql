-- Read-only broker observations, isolated by internal Paper identity.
CREATE TABLE paper_observations (
 id text PRIMARY KEY,
 account_id text NOT NULL CHECK (account_id LIKE 'PAPER-%'),
 kind text NOT NULL CHECK (kind IN ('status','account','positions','contract','quote','event')),
 occurred_at timestamptz NOT NULL,
 payload jsonb NOT NULL
);
CREATE INDEX paper_observations_latest_idx ON paper_observations (account_id,kind,occurred_at DESC);
