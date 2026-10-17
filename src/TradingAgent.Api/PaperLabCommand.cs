using System.Text.Json;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;

namespace TradingAgent.Api;

// Internal stdin protocol, no HTTP endpoint. Credentials never appear in arguments or responses.
public static class PaperLabCommand
{
    public static async Task Run(RiskPolicy p)
    {
        try
        {
            p.Validate();
            if(p.AllocatedCapital!=100 || p.CumulativeLossLimit!=20 || p.OrdinaryRisk>.0025m || p.MaximumRisk>.005m || p.MaxLeverage>1)
                throw new InvalidOperationException("LAB_STRATEGY_POLICY_CANNOT_BE_RELAXED");
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>5*1024*1024)throw new InvalidDataException();
            using var doc=JsonDocument.Parse(raw);var request=doc.RootElement;
                var operation=request.GetProperty("operation").GetString();
            var options=new JsonSerializerOptions(Evidence.Json){NumberHandling=System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString};
            if(operation=="paper-strategy-registry")
            {
                var cs=Environment.GetEnvironmentVariable("TRADING_DB")??throw new InvalidOperationException("PAPER_REGISTRY_UNAVAILABLE");
                var endpoint=new NpgsqlConnectionStringBuilder(cs);
                if(endpoint.Host!="127.0.0.1" || endpoint.Port is not (55432 or 55433) || endpoint.Username is not ("paper_data" or "trading_test"))
                    throw new InvalidOperationException("PAPER_REGISTRY_SCOPE_REQUIRED");
                var account=request.GetProperty("account_key").GetString()!;
                if(!account.StartsWith("PAPER-",StringComparison.Ordinal))throw new InvalidOperationException("PAPER_REGISTRY_SCOPE_REQUIRED");
                await using var c=new NpgsqlConnection(cs);await c.OpenAsync();
                await using var tx=await c.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead);
                await using(var readOnly=new NpgsqlCommand("SET TRANSACTION READ ONLY",c,tx)){await readOnly.ExecuteNonQueryAsync();}
                await using var cmd=new NpgsqlCommand("SELECT v.id,v.payload::text,s.payload::text FROM strategy_versions v JOIN strategies s ON s.id=v.payload->>'strategyId' AND s.account_id=v.account_id WHERE v.account_id=$1 ORDER BY v.id LIMIT 101",c,tx);
                cmd.Parameters.AddWithValue(account);var rows=new List<object>();
                await using var reader=await cmd.ExecuteReaderAsync();
                while(await reader.ReadAsync())
                {
                    if(rows.Count>=100)throw new InvalidOperationException("PAPER_REGISTRY_AMBIGUOUS");
                    var strategy=JsonSerializer.Deserialize<StrategyVersion>(reader.GetString(1),options)!;strategy.Validate();
                    if(strategy.Hash!=reader.GetString(0))throw new InvalidOperationException("PAPER_REGISTRY_HASH_MISMATCH");
                    using var status=JsonDocument.Parse(reader.GetString(2));
                    rows.Add(new {hash=strategy.Hash,strategy,registration=status.RootElement.Clone()});
                }
                Console.WriteLine(JsonSerializer.Serialize(rows,Evidence.Json));return;
            }
            if(operation=="research-exit")
            {
                var position=request.GetProperty("position").Deserialize<ResearchExitPosition>(options)!;
                var bar=request.GetProperty("bar").Deserialize<PaperCandle>(options)!;
                var exits=request.GetProperty("exits").Deserialize<ResearchExit[]>(options)!;
                var exitDecision=StrategyPaperExitAdapter.Decide(position,bar,request.GetProperty("previousOpenedAt").GetDateTimeOffset(),exits,
                    request.GetProperty("opening").GetBoolean());
                Console.WriteLine(JsonSerializer.Serialize(exitDecision,Evidence.Json));return;
            }
            if(operation=="paper-economic-sweep")
            {
                var strategy=request.GetProperty("strategy").GetString()!;
                var bars=request.GetProperty("bars").Deserialize<PaperCandle[]>(options)!;
                var signals=request.GetProperty("signals").Deserialize<ResearchSignal[]>(options)!;
                var exits=request.GetProperty("exits").Deserialize<ResearchExit[]>(options)!;
                var costs=request.GetProperty("costs").Deserialize<ResearchCosts>(options)!;
                var results=new decimal[]{1,5,10,20,30,50}.Select(exposure=>PaperEconomicSweep.Run(strategy,bars,signals,exits,costs,exposure));
                Console.WriteLine(JsonSerializer.Serialize(results,Evidence.Json));return;
            }
            if(operation=="paper-minimum-sizes")
            {
                var signals=request.GetProperty("signals").Deserialize<ResearchSignal[]>(options)!;
                var costs=request.GetProperty("costs").Deserialize<ResearchCosts>(options)!;
                var minima=signals.Where(s=>s.Reasons.Length==0 && s.EntryAt is not null && s.EntryMidpoint is not null)
                    .Select(s=>new {s.SignalAt,s.Side,Size=RiskEngine.MinimumPaperOpportunitySize(s,costs)});
                Console.WriteLine(JsonSerializer.Serialize(minima,Evidence.Json));return;
            }
            // Pure calculations; only the Python transport's DPAPI grant can authorize an order.
            // Keep the ordinary protocol closed to experimental ledgers.
            if(operation?.StartsWith("experimental-",StringComparison.Ordinal)==true)
            {
                var now=DateTimeOffset.UtcNow;
                var a=operation=="experimental-initial" ? AccountState.Initial("PAPER-STRATEGY",100,now) :
                    request.GetProperty("account").Deserialize<AccountState>(options)!;
                if(operation=="experimental-initial")a=a with {Capital=a.Capital! with {Environment="PAPER_TRADING"}};
                object experimentalResult=operation switch {
                    "experimental-initial" or "experimental-mark"=>PaperRiskProfile.Mark(a,now,p),
                    "experimental-risk"=>PaperRiskProfile.Study(PaperRiskProfile.Experimental,p,a,
                        request.GetProperty("request").Deserialize<RiskRequest>(options)!,now,"IBKR","StrategyPaper",false).Evaluation,
                    "experimental-economics"=>RiskEngine.StudyPaperEconomics(a,request.GetProperty("request").Deserialize<RiskRequest>(options)!),
                    "experimental-reserve"=>PaperRiskProfile.Reserve(a,request.GetProperty("request").Deserialize<RiskRequest>(options)!,
                        request.GetProperty("intent").GetString()!,now,p),
                    "experimental-release-unfilled"=>PaperRiskProfile.ReleaseUnfilled(a,request.GetProperty("intent").GetString()!,now,p),
                    "experimental-settle"=>PaperRiskProfile.Settle(a,request.GetProperty("intent").GetString()!,
                        request.GetProperty("net").Deserialize<decimal>(options),request.GetProperty("fees").Deserialize<decimal>(options),true,now,p),
                    _=>throw new ArgumentException("UNKNOWN_EXPERIMENTAL_OPERATION")};
                Console.WriteLine(JsonSerializer.Serialize(experimentalResult,Evidence.Json));return;
            }
            if(operation=="strategy-initial")
            {
                var initial=AccountState.Initial("PAPER-STRATEGY",100,DateTimeOffset.UtcNow);
                initial=initial with {Capital=initial.Capital! with {Environment="PAPER_TRADING"},PolicyVersion=p.Version};
                Console.WriteLine(JsonSerializer.Serialize(initial,Evidence.Json));return;
            }
            if(operation is "strategy-risk" or "strategy-settle" or "strategy-mark")
            {
                var a=request.GetProperty("account").Deserialize<AccountState>(options)!;
                if(a.Capital?.Environment!="PAPER_TRADING" || a.Capital.InitialCapital!=100 || a.Capital.LossAllowance!=20)
                    throw new InvalidOperationException("STRATEGY_PAPER_ALLOCATION_REQUIRED");
                if(a.PolicyVersion==PaperRiskProfile.Experimental || a.PaperContinuation is not null)
                    throw new InvalidOperationException("PAPER_EXPERIMENTAL_PROFILE_NOT_ACTIVE");
                if(operation=="strategy-settle")
                {
                    var net=request.GetProperty("net").Deserialize<decimal>(options);var fees=request.GetProperty("fees").Deserialize<decimal>(options);
                    Console.WriteLine(JsonSerializer.Serialize(a.Settle(net,fees,DateTimeOffset.UtcNow,p),Evidence.Json));return;
                }
                if(operation=="strategy-mark")
                {Console.WriteLine(JsonSerializer.Serialize(a.Mark(a.Capital.Equity,DateTimeOffset.UtcNow,p),Evidence.Json));return;}
                var r=request.GetProperty("request").Deserialize<RiskRequest>(options)!;
                if(
                    r.Execution?.EquivalentRealAccount?.Complete!=true || r.Execution.Environment!="PAPER_TRADING" || r.Execution.Mode is not ("STANDARD" or "ODD_LOT"))
                    throw new InvalidOperationException("STRATEGY_PAPER_EVIDENCE_REQUIRED");
                Console.WriteLine(JsonSerializer.Serialize(RiskEngine.Evaluate(p,a,r,DateTimeOffset.UtcNow),Evidence.Json));return;
            }
            var connection=Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidOperationException();
            var b=new NpgsqlConnectionStringBuilder(connection);
            if(b.Host!="127.0.0.1" || b.Port is not (55432 or 55433) || b.Username is not ("paper_lab_app" or "trading_test"))
                throw new InvalidOperationException("LAB_DATABASE_SCOPE_REQUIRED");
            var journal=new PaperLabJournal(connection);var key=request.GetProperty("account_key").GetString()!;
            object result=request.GetProperty("operation").GetString() switch
            {
                "load"=>await journal.Load(key),
                "commit"=>new {revision=await journal.Commit(key,request.GetProperty("revision").GetInt64(),request.GetProperty("state"),request.GetProperty("event"))},
                _=>throw new ArgumentException()
            };
            Console.WriteLine(JsonSerializer.Serialize(result,Evidence.Json));
        }
        catch(Exception e)
        {
            var reason=e.Message.Length<=128 && System.Text.RegularExpressions.Regex.IsMatch(e.Message,"^[A-Z][A-Z0-9_]+$") &&
                !System.Text.RegularExpressions.Regex.IsMatch(e.Message,"DU(?:R)?[0-9]{4,}") ? e.Message : "UNEXPECTED_FAILURE";
            Console.WriteLine(JsonSerializer.Serialize(new {error="LAB_COMMAND_FAILED",reason},Evidence.Json));Environment.ExitCode=1;
        }
    }
}
