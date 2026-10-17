using System.Reflection;
using System.Text.Json;
using Npgsql;
using TradingAgent.Core;

namespace TradingAgent.Infrastructure;

public sealed record DecisionCommand(string Id, string AccountId, string StrategyHash, RiskRequest Request,
    string Session, Dictionary<string,decimal> Features, string MarketBeforeJson);
public sealed record StoredDecision(string CommandHash, RiskEvaluation Evaluation, Experience Experience);

public sealed partial class PostgresStore(string connectionString)
{
    private static readonly HashSet<string> Tables = ["broker_accounts","market_candles","market_snapshots",
        "strategies","strategy_versions","backtest_runs","backtest_trades","trading_decisions","risk_policies",
        "risk_evaluations","equity_snapshots","strategy_approvals","system_events"];
    private async Task<NpgsqlConnection> Open(CancellationToken ct)
    { var c = new NpgsqlConnection(connectionString); await c.OpenAsync(ct); return c; }
    private static string Serialize<T>(T value) => JsonSerializer.Serialize(value,Evidence.Json);
    private static T Parse<T>(string json) => JsonSerializer.Deserialize<T>(json,Evidence.Json) ?? throw new InvalidDataException("Missing data");
    public async Task Migrate(CancellationToken ct=default)
    {
        await using var c=await Open(ct); await using var tx=await c.BeginTransactionAsync(ct);
        await using (var cmd=new NpgsqlCommand("SELECT pg_advisory_xact_lock(732941); CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY, checksum text NOT NULL)",c,tx)) await cmd.ExecuteNonQueryAsync(ct);
        var assembly=Assembly.GetExecutingAssembly();
        foreach(var name in assembly.GetManifestResourceNames().Where(x=>x.EndsWith(".sql")).Order())
        {
            using var reader=new StreamReader(assembly.GetManifestResourceStream(name)!); var sql=await reader.ReadToEndAsync(ct); var hash=Evidence.Hash(sql);
            await using var check=new NpgsqlCommand("SELECT checksum FROM schema_migrations WHERE name=$1",c,tx); check.Parameters.AddWithValue(name);
            var existing=await check.ExecuteScalarAsync(ct);
            if(existing is string stored) { if(stored!=hash) throw new InvalidDataException("Migration changed: "+name); continue; }
            await using var run=new NpgsqlCommand(sql,c,tx); await run.ExecuteNonQueryAsync(ct);
            await using var record=new NpgsqlCommand("INSERT INTO schema_migrations VALUES($1,$2)",c,tx); record.Parameters.AddWithValue(name);record.Parameters.AddWithValue(hash);await record.ExecuteNonQueryAsync(ct);
        }
        await tx.CommitAsync(ct);
    }
    public async Task VerifySchema(CancellationToken ct=default)
    {
        await using var c=await Open(ct);
        var assembly=Assembly.GetExecutingAssembly();
        foreach(var name in assembly.GetManifestResourceNames().Where(x=>x.EndsWith(".sql")).Order())
        {
            using var reader=new StreamReader(assembly.GetManifestResourceStream(name)!);
            var hash=Evidence.Hash(await reader.ReadToEndAsync(ct));
            await using var cmd=new NpgsqlCommand("SELECT checksum FROM schema_migrations WHERE name=$1",c);
            cmd.Parameters.AddWithValue(name);
            if(await cmd.ExecuteScalarAsync(ct) is not string stored || stored!=hash)
                throw new InvalidDataException("SCHEMA_MIGRATION_REQUIRED");
        }
    }
    private static async Task Put(NpgsqlConnection c,NpgsqlTransaction? tx,string table,string id,string account,
        string instrument,int timeframe,DateTimeOffset at,string json,CancellationToken ct)
    {
        if(!Tables.Contains(table)) throw new ArgumentException("Unknown entity");
        await using var cmd=new NpgsqlCommand($"INSERT INTO {table}(id,account_id,instrument,timeframe,occurred_at,payload) VALUES($1,$2,$3,$4,$5,$6::jsonb) ON CONFLICT(id) DO NOTHING",c,tx);
        cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(account);cmd.Parameters.AddWithValue(instrument);cmd.Parameters.AddWithValue(timeframe);cmd.Parameters.AddWithValue(at.ToUniversalTime());cmd.Parameters.AddWithValue(json);
        if(await cmd.ExecuteNonQueryAsync(ct)==0)
        {
            await using var compare=new NpgsqlCommand($"SELECT payload=$2::jsonb FROM {table} WHERE id=$1",c,tx);compare.Parameters.AddWithValue(id);compare.Parameters.AddWithValue(json);
            if(await compare.ExecuteScalarAsync(ct) is not true) throw new InvalidOperationException("IDEMPOTENCY_CONFLICT");
        }
    }
    public async Task Save<T>(string table,string id,string account,T value,DateTimeOffset at,string instrument="",int timeframe=0,CancellationToken ct=default)
    { await using var c=await Open(ct);await Put(c,null,table,id,account,instrument,timeframe,at,Serialize(value),ct); }
    public async Task<T?> Get<T>(string table,string id,CancellationToken ct=default)
    {
        if(!Tables.Contains(table))throw new ArgumentException("Unknown entity");
        await using var c=await Open(ct);await using var cmd=new NpgsqlCommand($"SELECT payload::text FROM {table} WHERE id=$1",c);cmd.Parameters.AddWithValue(id);
        return await cmd.ExecuteScalarAsync(ct) is string json ? Parse<T>(json) : default;
    }
    public async Task Initialize(AccountState state,RiskPolicy policy,CancellationToken ct=default)
    {
        policy.Validate();
        if(!state.AccountId.StartsWith("SIM-",StringComparison.Ordinal) || state.Capital is null ||
            state.Capital.Environment!="SIMULATION" || state.Capital.InitialCapital!=policy.AllocatedCapital ||
            state.Capital.LossAllowance!=policy.CumulativeLossLimit || state.Equity!=state.Capital.Equity)
            throw new ArgumentException("INITIAL_ALLOCATION_MISMATCH");
        state=state with {PolicyVersion=policy.Version};
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await Put(c,tx,"risk_policies",policy.Version,"SIM-PAPER","",0,state.At,Serialize(policy),ct);
        await using var cmd=new NpgsqlCommand("INSERT INTO account_states(account_id,payload) VALUES($1,$2::jsonb) ON CONFLICT DO NOTHING",c,tx);
        cmd.Parameters.AddWithValue(state.AccountId);cmd.Parameters.AddWithValue(Serialize(state));await cmd.ExecuteNonQueryAsync(ct);
        var persisted=await ReadState(c,tx,state.AccountId,ct);
        if(persisted.Capital is null || persisted.PolicyVersion!=policy.Version ||
            persisted.Capital.InitialCapital!=state.Capital.InitialCapital || persisted.Capital.LossAllowance!=state.Capital.LossAllowance ||
            persisted.Capital.Environment!=state.Capital.Environment || persisted.Capital.AllocationVersion!=state.Capital.AllocationVersion)
            throw new InvalidOperationException("EXISTING_ALLOCATION_REQUIRES_REVIEW");
        await Put(c,tx,"broker_accounts",state.AccountId,state.AccountId,"",0,state.At,Serialize(new {environment="PAPER_TRADING",simulated=true}),ct);
        await tx.CommitAsync(ct);
    }
    private async Task CheckPolicy(AccountState state,RiskPolicy policy,CancellationToken ct)
    {
        policy.Validate();
        if(state.PolicyVersion!=policy.Version || await Get<RiskPolicy>("risk_policies",policy.Version,ct)!=policy)
            throw new InvalidOperationException("POLICY_NOT_REGISTERED_OR_CHANGED");
    }
    private static async Task<AccountState> ReadState(NpgsqlConnection c,NpgsqlTransaction? tx,string account,CancellationToken ct,bool locked=true)
    {
        await using var cmd=new NpgsqlCommand("SELECT payload::text FROM account_states WHERE account_id=$1"+(locked?" FOR UPDATE":""),c,tx);cmd.Parameters.AddWithValue(account);
        return await cmd.ExecuteScalarAsync(ct) is string json ? Parse<AccountState>(json) : throw new KeyNotFoundException("Unknown simulation account");
    }
    private static async Task WriteState(NpgsqlConnection c,NpgsqlTransaction tx,AccountState a,CancellationToken ct)
    {
        await using var cmd=new NpgsqlCommand("UPDATE account_states SET payload=$2::jsonb,updated_at=now() WHERE account_id=$1",c,tx);
        cmd.Parameters.AddWithValue(a.AccountId);cmd.Parameters.AddWithValue(Serialize(a));await cmd.ExecuteNonQueryAsync(ct);
    }
    public async Task<AccountState> State(string account,CancellationToken ct=default)
    {await using var c=await Open(ct);return await ReadState(c,null,account,ct,false);}
    public async Task<StoredDecision> Evaluate(DecisionCommand command,RiskPolicy policy,DateTimeOffset now,CancellationToken ct=default)
    {
        if(string.IsNullOrWhiteSpace(command.Id)||command.Features is null||string.IsNullOrWhiteSpace(command.Session))throw new ArgumentException("Incomplete decision");
        using var market=JsonDocument.Parse(command.MarketBeforeJson);
        var strategy=await Get<StrategyVersion>("strategy_versions",command.StrategyHash,ct)??throw new ArgumentException("Unknown strategy version");
        strategy.Validate();
        var registered=await Get<RiskPolicy>("risk_policies",policy.Version,ct);
        if(registered!=policy)throw new InvalidOperationException("POLICY_NOT_REGISTERED_OR_CHANGED");
        if(strategy.Hash!=command.StrategyHash||strategy.Instrument!=command.Request.Instrument)throw new ArgumentException("Strategy hash/instrument mismatch");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        var state=await ReadState(c,tx,command.AccountId,ct);
        if(!state.AccountId.StartsWith("SIM-",StringComparison.Ordinal) || state.Capital?.Environment!="SIMULATION")
            throw new InvalidOperationException("SIMULATION_ALLOCATION_REQUIRED");
        if(state.PolicyVersion!=policy.Version)throw new InvalidOperationException("POLICY_CHANGE_REQUIRES_ADMIN_ACTIVATION");
        var commandHash=Evidence.Hash(Serialize(command));
        await using(var check=new NpgsqlCommand("SELECT payload::text FROM trading_decisions WHERE id=$1",c,tx))
        {
            check.Parameters.AddWithValue(command.Id);
            if(await check.ExecuteScalarAsync(ct) is string json)
            {var prior=Parse<StoredDecision>(json);if(prior.CommandHash!=commandHash)throw new InvalidOperationException("IDEMPOTENCY_CONFLICT");return prior;}
        }
        var request=command.Request;
        if(request.Execution is not null)
        {
            var mid=(request.Bid+request.Ask)/2;
            request=request with {Execution=request.Execution with {TakeProfit=request.Side=="BUY"?
                mid+strategy.TakeProfitDistance:mid-strategy.TakeProfitDistance}};
        }
        var result=RiskEngine.Evaluate(policy,state,request,now);
        if(result.Allowed && result.NominalExposure>strategy.MaxExposure)
            result=result with {Decision="DENY",Reason="STRATEGY_EXPOSURE_LIMIT",Quantity=0,NominalExposure=0,RequiredMargin=0};
        if(result.Decision=="HALT")state=state.Halt(result.Reason);
        if(result.Allowed)state=state with {ReservationId=command.Id,OpenPositions=[new(result.EstimatedLoss,result.NominalExposure,result.RequiredMargin)]};
        var experience=new Experience(command.Id,command.AccountId,command.Request.Instrument,now,command.Session,command.StrategyHash,
            command.Request.ProposedRisk??policy.OrdinaryRisk,result.Reason,!result.Allowed,command.Features,command.MarketBeforeJson,
            result.SpreadCost+result.Commissions+result.SlippageCost);
        var stored=new StoredDecision(commandHash,result,experience);
        await Put(c,tx,"trading_decisions",command.Id,command.AccountId,command.Request.Instrument,0,now,Serialize(stored),ct);
        await Put(c,tx,"risk_evaluations",command.Id,command.AccountId,command.Request.Instrument,0,now,Serialize(result),ct);
        await WriteState(c,tx,state,ct);await tx.CommitAsync(ct);return stored;
    }
    public async Task Settle(string account,string decisionId,decimal pnl,decimal observedCosts,string afterJson,RiskPolicy policy,DateTimeOffset now,CancellationToken ct=default)
    {
        if(observedCosts<0)throw new ArgumentException("Negative costs");using var after=JsonDocument.Parse(afterJson);
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);var state=await ReadState(c,tx,account,ct);
        await CheckPolicy(state,policy,ct);
        var decision=await Get<StoredDecision>("trading_decisions",decisionId,ct)??throw new KeyNotFoundException("Decision not found");
        if(decision.Experience.AccountId!=account || !decision.Evaluation.Allowed)throw new InvalidOperationException("No matching accepted simulation");
        var estimatedCosts=decision.Evaluation.Commissions+decision.Evaluation.SpreadCost+decision.Evaluation.SlippageCost;
        var costOverrun=observedCosts>estimatedCosts;
        var outcome=Serialize(new {decisionId,pnl,observedCosts,estimatedCosts,costOverrun,afterJson});
        await using(var check=new NpgsqlCommand("SELECT payload=$2::jsonb FROM market_snapshots WHERE id=$1 AND account_id=$3",c,tx))
        {check.Parameters.AddWithValue("outcome:"+decisionId);check.Parameters.AddWithValue(outcome);check.Parameters.AddWithValue(account);var prior=await check.ExecuteScalarAsync(ct);if(prior is bool same){if(!same)throw new InvalidOperationException("IDEMPOTENCY_CONFLICT");return;}}
        if(state.ReservationId!=decisionId)throw new InvalidOperationException("No matching simulated position");
        state=state.Settle(pnl,observedCosts,now,policy);
        if(costOverrun)
        {
            state=state.Halt("EXECUTION_COST_OVERRUN");
            await Put(c,tx,"system_events","cost-overrun:"+decisionId,account,"",0,now,
                Serialize(new{type="EXECUTION_COST_OVERRUN",decisionId,estimatedCosts,observedCosts}),ct);
        }
        await WriteState(c,tx,state,ct);
        await Put(c,tx,"market_snapshots","outcome:"+decisionId,account,"",0,now,outcome,ct);
        await Put(c,tx,"equity_snapshots","settled:"+decisionId,account,"",0,now,Serialize(state),ct);await tx.CommitAsync(ct);
    }
    public async Task EmergencyStop(string account,DateTimeOffset now,CancellationToken ct=default)
    {
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);var state=await ReadState(c,tx,account,ct);
        await WriteState(c,tx,state.Halt("EMERGENCY_STOP"),ct);
        await Put(c,tx,"system_events",Guid.NewGuid().ToString(),account,"",0,now,Serialize(new{type="EMERGENCY_STOP",protectiveOrdersTouched=false}),ct);await tx.CommitAsync(ct);
    }
    public async Task Mark(string account,string eventId,decimal equity,RiskPolicy policy,DateTimeOffset now,CancellationToken ct=default)
    {
        if(string.IsNullOrWhiteSpace(eventId))throw new ArgumentException("Event ID required");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);var state=await ReadState(c,tx,account,ct);
        await CheckPolicy(state,policy,ct);
        await using(var prior=new NpgsqlCommand("SELECT payload->>'equity' FROM equity_snapshots WHERE id=$1 AND account_id=$2",c,tx))
        {prior.Parameters.AddWithValue(eventId);prior.Parameters.AddWithValue(account);if(await prior.ExecuteScalarAsync(ct) is string value){if(decimal.Parse(value,System.Globalization.CultureInfo.InvariantCulture)!=equity)throw new InvalidOperationException("IDEMPOTENCY_CONFLICT");return;}}
        if(state.ReservationId!=null)throw new InvalidOperationException("Settle the simulated position before manual marks");
        state=state.Mark(equity,now,policy);await WriteState(c,tx,state,ct);
        await Put(c,tx,"equity_snapshots",eventId,account,"",0,now,Serialize(state),ct);await tx.CommitAsync(ct);
    }
    public async Task ObserveRejected(string decisionId,string afterJson,string behaviorChange,DateTimeOffset now,CancellationToken ct=default)
    {
        using var doc=JsonDocument.Parse(afterJson);
        var decision=await Get<StoredDecision>("trading_decisions",decisionId,ct)??throw new KeyNotFoundException("Decision not found");
        if(!decision.Experience.Rejected || now<=decision.Experience.At)throw new ArgumentException("Only later observations of rejected decisions");
        await Save("market_snapshots","outcome:"+decisionId,decision.Experience.AccountId,
            new{decisionId,pnl=(decimal?)null,observedCosts=(decimal?)null,afterJson,behaviorChange},now,decision.Experience.Instrument,ct:ct);
    }
    public async Task ValuePosition(string account,string eventId,string decisionId,decimal unrealizedNetPnl,
        decimal openCosts,decimal remainingRisk,RiskPolicy policy,DateTimeOffset now,CancellationToken ct=default)
    {
        if(string.IsNullOrWhiteSpace(eventId))throw new ArgumentException("Event ID required");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        var state=await ReadState(c,tx,account,ct);await CheckPolicy(state,policy,ct);
        var input=Serialize(new{decisionId,unrealizedNetPnl,openCosts,remainingRisk});
        await using(var prior=new NpgsqlCommand("SELECT payload=$2::jsonb FROM market_snapshots WHERE id=$1 AND account_id=$3",c,tx))
        {
            prior.Parameters.AddWithValue("valuation:"+eventId);prior.Parameters.AddWithValue(input);prior.Parameters.AddWithValue(account);
            if(await prior.ExecuteScalarAsync(ct) is bool same){if(!same)throw new InvalidOperationException("IDEMPOTENCY_CONFLICT");return;}
        }
        if(state.ReservationId!=decisionId || state.Capital?.Environment!="SIMULATION")
            throw new InvalidOperationException("No matching simulated position");
        state=state.ValuePosition(unrealizedNetPnl,openCosts,remainingRisk,now,policy);
        await Put(c,tx,"market_snapshots","valuation:"+eventId,account,"",0,now,input,ct);
        await Put(c,tx,"equity_snapshots","valuation:"+eventId,account,"",0,now,Serialize(state),ct);
        await WriteState(c,tx,state,ct);await tx.CommitAsync(ct);
    }
    public async Task<Experience[]> Experiences(string account,DateTimeOffset before,int count=100,CancellationToken ct=default)
    {
        await using var c=await Open(ct);await using var cmd=new NpgsqlCommand("SELECT d.payload::text, o.payload::text FROM trading_decisions d LEFT JOIN market_snapshots o ON o.id='outcome:'||d.id AND o.occurred_at < $2 WHERE d.account_id=$1 AND d.occurred_at < $2 ORDER BY d.occurred_at DESC LIMIT $3",c);
        cmd.Parameters.AddWithValue(account);cmd.Parameters.AddWithValue(before.ToUniversalTime());cmd.Parameters.AddWithValue(Math.Clamp(count,1,1000));
        var result=new List<Experience>();await using var reader=await cmd.ExecuteReaderAsync(ct);
        while(await reader.ReadAsync(ct))
        {
            var episode=Parse<StoredDecision>(reader.GetString(0)).Experience;
            if(!reader.IsDBNull(1)){using var doc=JsonDocument.Parse(reader.GetString(1));var root=doc.RootElement;episode=episode with{SimulatedPnl=root.GetProperty("pnl").ValueKind==JsonValueKind.Null?null:root.GetProperty("pnl").GetDecimal(),ObservedCosts=root.GetProperty("observedCosts").ValueKind==JsonValueKind.Null?null:root.GetProperty("observedCosts").GetDecimal(),MarketAfterJson=root.GetProperty("afterJson").GetString(),BehaviorChange=root.TryGetProperty("behaviorChange",out var change)?change.GetString():null};}
            result.Add(episode);
        }return result.ToArray();
    }
}
