-- Explicit maintenance only. Immutable strategy/evaluation evidence is never purged here.
-- Pin candles used by validation datasets via payload.pinned=true before archiving.
CREATE FUNCTION aggregate_and_prune_candles(cutoff timestamptz) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE removed bigint;
BEGIN
 IF cutoff > now() - interval '90 days' THEN RAISE EXCEPTION 'Minimum raw retention is 90 days'; END IF;
 WITH candidates AS MATERIALIZED (
   SELECT * FROM market_candles WHERE occurred_at < date_trunc('day',cutoff AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
    AND coalesce((payload->>'pinned')::boolean,false)=false
 ), aggregated AS (
   INSERT INTO daily_market_stats
   SELECT account_id,instrument,timeframe,(occurred_at AT TIME ZONE 'UTC')::date,count(*),
    min((payload->>'low')::numeric),max((payload->>'high')::numeric),avg((payload->>'close')::numeric),
    CASE WHEN count(payload->>'volume')=count(*) THEN sum((payload->>'volume')::numeric) ELSE NULL END
   FROM candidates GROUP BY account_id,instrument,timeframe,(occurred_at AT TIME ZONE 'UTC')::date
   ON CONFLICT(account_id,instrument,timeframe,day) DO UPDATE SET
    samples=daily_market_stats.samples+excluded.samples,
    low=least(daily_market_stats.low,excluded.low),high=greatest(daily_market_stats.high,excluded.high),
    mean_close=(daily_market_stats.mean_close*daily_market_stats.samples+excluded.mean_close*excluded.samples)
      /(daily_market_stats.samples+excluded.samples),
    volume=CASE WHEN daily_market_stats.volume IS NULL OR excluded.volume IS NULL THEN NULL ELSE daily_market_stats.volume+excluded.volume END
   RETURNING 1
 ) DELETE FROM market_candles WHERE id IN (SELECT id FROM candidates);
 GET DIAGNOSTICS removed=ROW_COUNT;
 RETURN removed;
END $$;
