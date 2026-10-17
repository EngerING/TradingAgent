using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed class PriceRiskStore(string connection)
{
    public static void Validate(JsonElement p,string? previous)
    {
        if(p.GetProperty("scope").GetString()!="R10_PRICE_RISK_EXPERIMENTAL" || p.GetProperty("classification").GetString()!="SIMULATED_SHADOW" || p.GetProperty("live_enabled").GetBoolean() || p.GetProperty("broker_orders").GetInt32()!=0)throw new InvalidDataException("SHADOW_ONLY_REQUIRED");
        var s=p.GetProperty("state");var c=s.GetProperty("protocol");
        if(c.GetProperty("price_risk_budget_usd").GetString()!="10" || c.GetProperty("initial_capital_usd").GetString()!="100" || c.GetProperty("all_in_loss_cap_usd").GetString()!="15" || c.GetProperty("broker_orders_enabled").GetBoolean() || c.GetProperty("live_enabled").GetBoolean())throw new InvalidDataException("PRICE_RISK_SCOPE_REQUIRED");
        decimal Number(JsonElement e,string key)=>decimal.Parse(e.GetProperty(key).GetString()!,System.Globalization.CultureInfo.InvariantCulture);
        if(Number(s,"reserved")<0 || Number(s,"reserved")>100 || Number(s,"consumed_loss")<0)throw new InvalidDataException("CAPITAL_SCOPE_REQUIRED");
        if(previous is null)return;
        using var old=JsonDocument.Parse(previous);var before=old.RootElement.GetProperty("state");
        if(c.GetRawText()!=before.GetProperty("protocol").GetRawText() || s.GetProperty("engine_hash").GetString()!=before.GetProperty("engine_hash").GetString() || Number(s,"consumed_loss")<Number(before,"consumed_loss"))throw new InvalidDataException("IMMUTABLE_PROTOCOL_OR_LOSS");
        foreach(var trade in before.GetProperty("trades").EnumerateArray())
            if(!s.GetProperty("trades").EnumerateArray().Any(t=>t.GetRawText()==trade.GetRawText()))throw new InvalidDataException("TRADE_CANNOT_DISAPPEAR");
        foreach(var signal in before.GetProperty("seen").EnumerateArray())
            if(!s.GetProperty("seen").EnumerateArray().Any(t=>t.GetString()==signal.GetString()))throw new InvalidDataException("SIGNAL_CANNOT_RESET");
        var active=before.GetProperty("active");
        if(active.ValueKind!=JsonValueKind.Null && !s.GetProperty("trades").EnumerateArray().Any(t=>t.GetProperty("id").GetString()==active.GetProperty("id").GetString()) && (s.GetProperty("active").ValueKind==JsonValueKind.Null || s.GetProperty("active").GetProperty("id").GetString()!=active.GetProperty("id").GetString()))throw new InvalidDataException("INVENTORY_CANNOT_DISAPPEAR");
    }
    public async Task<ShadowHead> Execute(string experiment,ShadowEvent? e,CancellationToken ct=default)
    {
        if(!Regex.IsMatch(experiment,"^r10-price-[a-f0-9]{32}$"))throw new InvalidDataException("EXPERIMENT_SCOPE_REQUIRED");
        var cfg=new NpgsqlConnectionStringBuilder(connection);
        if(cfg.Host!="127.0.0.1" || cfg.Database!="postgres" || !((cfg.Port==55433 && cfg.Username=="paper_lab_app")||(cfg.Port==55432 && cfg.Username=="trading_test")))throw new InvalidDataException("PAPER_DATABASE_REQUIRED");
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,71010))",c,tx)){guard.Parameters.AddWithValue(experiment);await guard.ExecuteNonQueryAsync(ct);}
        var head=new ShadowHead(0,"");
        await using(var query=new NpgsqlCommand("SELECT revision,event_hash,payload FROM price_risk.events WHERE experiment_id=$1 ORDER BY revision DESC LIMIT 1",c,tx))
        {query.Parameters.AddWithValue(experiment);await using var rows=await query.ExecuteReaderAsync(ct);if(await rows.ReadAsync(ct))head=new(rows.GetInt64(0),rows.GetString(1),rows.GetString(2));}
        if(e is not null)
        {
            using var payload=JsonDocument.Parse(e.Payload);using var material=JsonDocument.Parse(e.Material);var p=payload.RootElement;var m=material.RootElement;
            if(e.Material.Length>4000000 || Evidence.Hash(e.Material)!=e.Hash || m.GetArrayLength()!=3 || m[0].GetInt64()!=e.Revision || m[1].GetRawText()!=e.Payload || m[2].GetString()!=e.Previous || p.GetProperty("experiment").GetString()!=experiment || e.Revision!=head.Revision+1 || e.Previous!=head.Hash)throw new InvalidDataException("PRICE_RISK_INTEGRITY_OR_CAS");
            Validate(p,head.Payload);
            await using var insert=new NpgsqlCommand("INSERT INTO price_risk.events VALUES($1,$2,$3,$4,$5)",c,tx);
            insert.Parameters.AddWithValue(experiment);insert.Parameters.AddWithValue(e.Revision);insert.Parameters.AddWithValue(e.Payload);insert.Parameters.AddWithValue(e.Previous);insert.Parameters.AddWithValue(e.Hash);await insert.ExecuteNonQueryAsync(ct);head=new(e.Revision,e.Hash,e.Payload);
        }
        await tx.CommitAsync(ct);return head;
    }
}
