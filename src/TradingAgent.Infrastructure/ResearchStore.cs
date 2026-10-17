using System.Text.Json;
using Npgsql;
using TradingAgent.Core;

namespace TradingAgent.Infrastructure;

public sealed partial class PostgresStore
{
    public async Task<Dictionary<string,JsonElement[]>> ResearchOriginals(string account,CancellationToken ct=default)
    {
        if(!account.StartsWith("PAPER-",StringComparison.Ordinal))throw new ArgumentException("PAPER_DATA_SOURCE_REQUIRED");
        await using var c=await Open(ct);
        await using var cmd=new NpgsqlCommand("SELECT timeframe,payload::text FROM market_candles WHERE account_id=$1 AND instrument='EUR/USD' ORDER BY timeframe,occurred_at LIMIT 30001",c);
        cmd.Parameters.AddWithValue(account);var rows=new Dictionary<string,List<JsonElement>>{{"15",[]},{"60",[]},{"240",[]}};
        await using var reader=await cmd.ExecuteReaderAsync(ct);var count=0;
        while(await reader.ReadAsync(ct))
        {
            if(++count>30000)throw new InvalidDataException("RESEARCH_DATASET_TOO_LARGE");
            using var doc=JsonDocument.Parse(reader.GetString(1));rows[reader.GetInt32(0).ToString()].Add(doc.RootElement.Clone());
        }
        return rows.ToDictionary(p=>p.Key,p=>p.Value.ToArray());
    }

    public async Task SaveResearch(string id,string account,DateTimeOffset at,JsonElement input,JsonElement analysis,
        StrategyVersion[] strategies,ResearchBacktestResult[] backtests,CancellationToken ct=default,JsonElement? validationEvidence=null)
    {
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        // Originals are append-only evidence. The normalized series is a different payload, never an UPDATE of broker candles.
        await Put(c,tx,"market_snapshots",id+":originals",account,"EUR/USD",0,at,input.GetRawText(),ct);
        await Put(c,tx,"market_snapshots",id+":analysis",account,"EUR/USD",0,at,analysis.GetRawText(),ct);
        if(validationEvidence is JsonElement extension)
            await Put(c,tx,"market_snapshots",id+":extended-validation",account,"EUR/USD",15,at,extension.GetRawText(),ct);
        foreach(var strategy in strategies)
        {
            strategy.Validate();
            await Put(c,tx,"strategies",strategy.StrategyId,account,"EUR/USD",0,at,Serialize(new{strategy.StrategyId,state="CANDIDATE_RESEARCH_ONLY"}),ct);
            await Put(c,tx,"strategy_versions",strategy.Hash,account,"EUR/USD",0,at,Serialize(strategy),ct);
        }
        foreach(var backtest in backtests)
        {
            await Put(c,tx,"backtest_runs",id+":"+backtest.StrategyId,account,"EUR/USD",15,at,Serialize(backtest),ct);
            for(var i=0;i<backtest.Assessments.Length;i++)
            {
                var decision=backtest.Assessments[i];var key=id+":"+backtest.StrategyId+":decision:"+i;
                await Put(c,tx,"trading_decisions",key,account,"EUR/USD",15,decision.Signal.SignalAt,Serialize(decision),ct);
                if(decision.Risk is not null)await Put(c,tx,"risk_evaluations",key,account,"EUR/USD",15,decision.Signal.EntryAt!.Value,Serialize(decision.Risk),ct);
            }
            for(var i=0;i<backtest.Trades.Length;i++)
                await Put(c,tx,"backtest_trades",id+":"+backtest.StrategyId+":trade:"+i,account,"EUR/USD",15,
                    backtest.Trades[i].ExitAt,Serialize(backtest.Trades[i]),ct);
        }
        await tx.CommitAsync(ct);
    }
}
