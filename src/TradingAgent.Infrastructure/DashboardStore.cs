using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed record DashboardEnvelope(JsonElement? Head,JsonElement? Observation,long Revision,bool? Emergency,JsonElement[] Quotes,JsonElement? Exploratory=null,JsonElement[]? Kronos=null,JsonElement? PriceRisk=null,JsonElement? AggressiveGrowth=null);
public sealed class DashboardStore(string connection)
{
    private async Task<NpgsqlConnection> Open(CancellationToken ct)
    {
        var config=new NpgsqlConnectionStringBuilder(connection);
        if(config.Host!="127.0.0.1" || config.Port is not (55432 or 55433) ||
            config.Username is not ("paper_lab_app" or "trading_test"))throw new InvalidOperationException("DASHBOARD_PAPER_DATABASE_REQUIRED");
        var c=new NpgsqlConnection(config.ConnectionString);await c.OpenAsync(ct);return c;
    }
    public async Task<DashboardEnvelope> Snapshot(string? study,CancellationToken ct)
    {
        if(study is not null && !Regex.IsMatch(study,"^eurusd-shadow-[a-f0-9]{32}$"))throw new ArgumentException("INVALID_STUDY");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead,ct);
        await using(var ro=new NpgsqlCommand("SET TRANSACTION READ ONLY",c,tx))await ro.ExecuteNonQueryAsync(ct);
        JsonElement? head=null,observation=null;long revision=0;
        // Revision is the durable head within each cohort. Decode timestamps only
        // on those heads, never on every large historical state in the journal.
        await using(var cmd=new NpgsqlCommand("WITH heads AS MATERIALIZED (SELECT DISTINCT ON (study_id) study_id,revision,payload FROM research_shadow.events WHERE ($1::text IS NULL OR study_id=$1) ORDER BY study_id,revision DESC) SELECT study_id,revision,payload FROM heads ORDER BY (payload::jsonb->>'at') DESC,revision DESC LIMIT 1",c,tx))
        {
            cmd.Parameters.AddWithValue((object?)study??DBNull.Value);await using var rows=await cmd.ExecuteReaderAsync(ct);
            if(await rows.ReadAsync(ct)){study=rows.GetString(0);revision=rows.GetInt64(1);head=JsonSerializer.Deserialize<JsonElement>(rows.GetString(2));}
        }
        if(study is not null)
        {
            await using var cmd=new NpgsqlCommand("SELECT payload FROM research_shadow.events WHERE study_id=$1 AND payload::jsonb->>'event'='COMMON_MARKET_OPPORTUNITY_EVALUATED' ORDER BY revision DESC LIMIT 1",c,tx);
            cmd.Parameters.AddWithValue(study);if(await cmd.ExecuteScalarAsync(ct) is string data)observation=JsonSerializer.Deserialize<JsonElement>(data);
        }
        var quotes=new List<JsonElement>();
        if(study is not null)
        {
            await using var cmd=new NpgsqlCommand("SELECT payload::jsonb->'details'->'quote' FROM research_shadow.events WHERE study_id=$1 AND payload::jsonb->>'event'='COMMON_MARKET_OPPORTUNITY_EVALUATED' ORDER BY revision DESC LIMIT 500",c,tx);
            cmd.Parameters.AddWithValue(study);await using var rows=await cmd.ExecuteReaderAsync(ct);while(await rows.ReadAsync(ct))if(!rows.IsDBNull(0))quotes.Add(JsonSerializer.Deserialize<JsonElement>(rows.GetString(0)));
        }
        bool? emergency=null;
        await using(var cmd=new NpgsqlCommand("SELECT bool_or((payload->>'emergency')::boolean) FROM paper_lab.states",c,tx))
        {if(await cmd.ExecuteScalarAsync(ct) is bool value)emergency=value;}
        JsonElement? exploratory=null;
        await using(var cmd=new NpgsqlCommand("SELECT payload FROM paper_exploratory.events ORDER BY (payload::jsonb->>'at') DESC,revision DESC LIMIT 1",c,tx))
        {if(await cmd.ExecuteScalarAsync(ct) is string data)exploratory=JsonSerializer.Deserialize<JsonElement>(data);}
        JsonElement? priceRisk=null;
        await using(var cmd=new NpgsqlCommand("WITH heads AS MATERIALIZED (SELECT DISTINCT ON (experiment_id) experiment_id,revision,payload FROM price_risk.events ORDER BY experiment_id,revision DESC) SELECT payload FROM heads ORDER BY (payload::jsonb->>'at') DESC,revision DESC LIMIT 1",c,tx))
        {if(await cmd.ExecuteScalarAsync(ct) is string data)priceRisk=JsonSerializer.Deserialize<JsonElement>(data);}
        JsonElement? aggressiveGrowth=null;
        await using(var cmd=new NpgsqlCommand("SELECT payload FROM aggressive_growth.events WHERE payload::jsonb->'state'->>'run_kind'='FORWARD' ORDER BY (payload::jsonb->>'at') DESC,revision DESC LIMIT 1",c,tx))
        {if(await cmd.ExecuteScalarAsync(ct) is string data)aggressiveGrowth=JsonSerializer.Deserialize<JsonElement>(data);}
        await tx.CommitAsync(ct);
        JsonElement[] kronos=[];
        try{kronos=await new KronosStore(connection).Read(ct,compact:true);}
        catch(Exception e) when(e is NpgsqlException or InvalidDataException or JsonException)
        {kronos=[JsonSerializer.SerializeToElement(new{kind="STATUS",payload=new{status="KRONOS_UNAVAILABLE",at=DateTimeOffset.UtcNow,reason="KRONOS_PERSISTENCE_UNAVAILABLE_OR_INVALID"}})];} // Optional predictor cannot take down the dashboard.
        return new(head,observation,revision,emergency,quotes.ToArray(),exploratory,kronos,priceRisk,aggressiveGrowth);
    }
    public async Task<JsonElement?> FindResponse(string session,Guid id,CancellationToken ct)
    {
        await using var c=await Open(ct);await using var cmd=new NpgsqlCommand("SELECT payload FROM dashboard_chat.events WHERE session_id=$1 AND request_id=$2 AND kind='RESPONSE'",c);
        cmd.Parameters.AddWithValue(session);cmd.Parameters.AddWithValue(id);
        return await cmd.ExecuteScalarAsync(ct) is string p?JsonSerializer.Deserialize<JsonElement>(p):null;
    }
    public async Task<bool> Reserve(string session,Guid id,decimal budget,decimal cost,JsonElement request,CancellationToken ct)
    {
        if(!Regex.IsMatch(session,"^sol-ui-[a-f0-9]{32}$") || budget is <0 or >1 || cost<=0)throw new ArgumentException("SOL_BUDGET_INVALID");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,38417))",c,tx))
        {guard.Parameters.AddWithValue(session);await guard.ExecuteNonQueryAsync(ct);}
        await using(var cmd=new NpgsqlCommand("SELECT count(*),COALESCE(sum((payload::jsonb->>'reservedUsd')::numeric),0),bool_or(request_id=$2),min((payload::jsonb->>'budgetUsd')::numeric),count(*) FILTER(WHERE NOT EXISTS(SELECT 1 FROM dashboard_chat.events d WHERE d.session_id=e.session_id AND d.request_id=e.request_id AND d.kind='RESPONSE') OR EXISTS(SELECT 1 FROM dashboard_chat.events d WHERE d.session_id=e.session_id AND d.kind='FAILED')) FROM dashboard_chat.events e WHERE session_id=$1 AND kind='RESERVED'",c,tx))
        {
            cmd.Parameters.AddWithValue(session);cmd.Parameters.AddWithValue(id);await using var r=await cmd.ExecuteReaderAsync(ct);await r.ReadAsync(ct);
            if(r.GetInt64(0)>=10 || r.GetDecimal(1)+cost>budget || !r.IsDBNull(2)&&r.GetBoolean(2) || !r.IsDBNull(3)&&r.GetDecimal(3)!=budget || r.GetInt64(4)>0)return false;
        }
        var payload=JsonSerializer.Serialize(new{reservedUsd=cost,budgetUsd=budget,requestHash=Evidence.Hash(request.GetRawText()),noRetry=true});
        await Insert(c,tx,session,id,"RESERVED",payload,ct);await tx.CommitAsync(ct);return true;
    }
    public async Task Audit(string session,Guid id,string kind,JsonElement payload,CancellationToken ct)
    {
        if(!Regex.IsMatch(session,"^sol-ui-[a-f0-9]{32}$") || kind is not ("RESPONSE" or "BLOCKED" or "FAILED"))throw new ArgumentException("SOL_AUDIT_SCOPE_REQUIRED");
        await using var c=await Open(ct);await Insert(c,null,session,id,kind,payload.GetRawText(),ct);
    }
    private static async Task Insert(NpgsqlConnection c,NpgsqlTransaction? tx,string session,Guid id,string kind,string payload,CancellationToken ct)
    {
        await using var cmd=new NpgsqlCommand("INSERT INTO dashboard_chat.events(session_id,request_id,kind,payload,event_hash) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",c,tx);
        cmd.Parameters.AddWithValue(session);cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(kind);cmd.Parameters.AddWithValue(payload);cmd.Parameters.AddWithValue(Evidence.Hash(payload));await cmd.ExecuteNonQueryAsync(ct);
    }
}
