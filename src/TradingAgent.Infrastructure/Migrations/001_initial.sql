CREATE TABLE account_states (
 account_id text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
-- Append-only research evidence. Indexed fields permit selective retrieval without loading payloads.
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['broker_accounts','market_candles','market_snapshots','strategies',
 'strategy_versions','backtest_runs','backtest_trades','trading_decisions','risk_policies',
 'risk_evaluations','equity_snapshots','strategy_approvals','system_events'] LOOP
  EXECUTE format('CREATE TABLE %I (id text PRIMARY KEY, account_id text NOT NULL,
    instrument text NOT NULL DEFAULT '''', timeframe integer NOT NULL DEFAULT 0,
    occurred_at timestamptz NOT NULL, payload jsonb NOT NULL,
    CHECK (timeframe IN (0,15,60,240)))', name);
  EXECUTE format('CREATE INDEX %I ON %I (instrument,timeframe,occurred_at)',name||'_series_idx',name);
  EXECUTE format('CREATE INDEX %I ON %I (account_id,occurred_at)',name||'_account_idx',name);
 END LOOP;
END $$;
CREATE UNIQUE INDEX strategy_version_unique ON strategy_versions
 ((payload->>'strategyId'), ((payload->>'version')::integer));
CREATE UNIQUE INDEX candle_unique ON market_candles (account_id,instrument,timeframe,occurred_at);
CREATE FUNCTION reject_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'IMMUTABLE_EVIDENCE: append a new version/event'; END $$;
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['strategy_versions','strategy_approvals','risk_policies',
 'trading_decisions','risk_evaluations','backtest_runs','backtest_trades','equity_snapshots'] LOOP
  EXECUTE format('CREATE TRIGGER evidence_immutable BEFORE UPDATE OR DELETE ON %I
    FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation()', name);
 END LOOP;
END $$;
CREATE TABLE daily_market_stats (
 account_id text NOT NULL, instrument text NOT NULL, timeframe integer NOT NULL, day date NOT NULL,
 samples bigint NOT NULL, low numeric NOT NULL, high numeric NOT NULL,
 mean_close numeric NOT NULL, volume numeric NULL,
 PRIMARY KEY(account_id,instrument,timeframe,day)
);
