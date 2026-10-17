using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed record ShadowEvent(long Revision,string Payload,string Previous,string Hash,string Material);
public sealed record ShadowHead(long Revision,string Hash,string? Payload=null);
public sealed partial class PostgresStore
{
    public async Task<ShadowHead> AppendShadow(string study,ShadowEvent[] events,CancellationToken ct=default)
    {
        if(!Regex.IsMatch(study,"^eurusd-shadow-[a-f0-9]{32}$") || events.Length>20)
            throw new InvalidDataException("SHADOW_SCOPE_REQUIRED");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,93165))",c,tx))
        {guard.Parameters.AddWithValue(study);await guard.ExecuteNonQueryAsync(ct);}
        var head=new ShadowHead(0,"");
        await using(var read=new NpgsqlCommand("SELECT revision,event_hash,payload FROM research_shadow.events WHERE study_id=$1 ORDER BY revision DESC LIMIT 1",c,tx))
        {read.Parameters.AddWithValue(study);await using var rows=await read.ExecuteReaderAsync(ct);if(await rows.ReadAsync(ct))head=new(rows.GetInt64(0),rows.GetString(1),rows.GetString(2));}
        foreach(var e in events)
        {
            using var payload=JsonDocument.Parse(e.Payload);using var material=JsonDocument.Parse(e.Material);
            var p=payload.RootElement;var m=material.RootElement;
            if(e.Revision<1 || e.Material.Length>4000000 || Evidence.Hash(e.Material)!=e.Hash || m.GetArrayLength()!=3 ||
                m[0].GetInt64()!=e.Revision || m[1].GetRawText()!=e.Payload || m[2].GetString()!=e.Previous ||
                p.GetProperty("study_id").GetString()!=study || p.GetProperty("scope").GetString()!="EURUSD_SHADOW_R1_R5_R10" ||
                p.GetProperty("classification").GetString()!="SIMULATED_SHADOW" || p.GetProperty("broker_orders").GetInt32()!=0 ||
                p.GetProperty("execution_authorized").GetBoolean() || p.GetProperty("live_enabled").GetBoolean())
                throw new InvalidDataException("SHADOW_INTEGRITY_FAILURE");
            if(e.Revision<=head.Revision)
            {
                await using var check=new NpgsqlCommand("SELECT event_hash FROM research_shadow.events WHERE study_id=$1 AND revision=$2",c,tx);
                check.Parameters.AddWithValue(study);check.Parameters.AddWithValue(e.Revision);
                if(await check.ExecuteScalarAsync(ct) is not string existing || existing!=e.Hash)throw new InvalidDataException("SHADOW_REPLAY_CONFLICT");
                continue;
            }
            if(e.Revision!=head.Revision+1 || e.Previous!=head.Hash)throw new InvalidDataException("SHADOW_CHAIN_GAP");
            await using var insert=new NpgsqlCommand("INSERT INTO research_shadow.events VALUES($1,$2,$3,$4,$5)",c,tx);
            insert.Parameters.AddWithValue(study);insert.Parameters.AddWithValue(e.Revision);insert.Parameters.AddWithValue(e.Payload);
            insert.Parameters.AddWithValue(e.Previous);insert.Parameters.AddWithValue(e.Hash);
            await insert.ExecuteNonQueryAsync(ct);head=new(e.Revision,e.Hash,e.Payload);
        }
        await tx.CommitAsync(ct);return head;
    }
}
