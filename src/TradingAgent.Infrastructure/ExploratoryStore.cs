using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed class ExploratoryStore(string connection)
{
    public async Task<string[]> Conflicts(string cohort,CancellationToken ct=default)
    {
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync(ct);
        await using var cmd=new NpgsqlCommand("SELECT cohort_id FROM (SELECT DISTINCT ON(cohort_id) cohort_id,payload::jsonb AS p FROM paper_exploratory.events ORDER BY cohort_id,revision DESC) heads WHERE cohort_id<>$1 AND (p->'state'->'active'<>'null'::jsonb OR EXISTS(SELECT FROM jsonb_each(p->'state'->'profiles') v WHERE (v.value->>'reserved')::numeric<>0))",c);
        cmd.Parameters.AddWithValue(cohort);var result=new List<string>();await using var rows=await cmd.ExecuteReaderAsync(ct);while(await rows.ReadAsync(ct))result.Add(rows.GetString(0));return result.ToArray();
    }
    public async Task<ShadowHead> Execute(string cohort, ShadowEvent? e, CancellationToken ct=default)
    {
        if(!Regex.IsMatch(cohort,"^eurusd-explore-[a-f0-9]{32}$"))throw new InvalidDataException("COHORT_SCOPE_REQUIRED");
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,62047))",c,tx))
        {guard.Parameters.AddWithValue(cohort);await guard.ExecuteNonQueryAsync(ct);}
        var head=new ShadowHead(0,"");
        await using(var read=new NpgsqlCommand("SELECT revision,event_hash,payload FROM paper_exploratory.events WHERE cohort_id=$1 ORDER BY revision DESC LIMIT 1",c,tx))
        {read.Parameters.AddWithValue(cohort);await using var rows=await read.ExecuteReaderAsync(ct);if(await rows.ReadAsync(ct))head=new(rows.GetInt64(0),rows.GetString(1),rows.GetString(2));}
        if(e is not null)
        {
            using var payload=JsonDocument.Parse(e.Payload);using var material=JsonDocument.Parse(e.Material);
            var p=payload.RootElement;var m=material.RootElement;
            if(e.Material.Length>4000000 || Evidence.Hash(e.Material)!=e.Hash || m.GetArrayLength()!=3 ||
                m[0].GetInt64()!=e.Revision || m[1].GetRawText()!=e.Payload || m[2].GetString()!=e.Previous ||
                p.GetProperty("cohort_id").GetString()!=cohort || p.GetProperty("scope").GetString()!="EURUSD_PAPER_EXPLORATORY" ||
                p.GetProperty("classification").GetString()!="EXPLORATORY_NOT_VALIDATED" || p.GetProperty("live_enabled").GetBoolean())
                throw new InvalidDataException("EXPLORATORY_INTEGRITY_FAILURE");
            // Ambiguous commits can be verified, never silently replaced or replayed as orders.
            if(e.Revision!=head.Revision+1 || e.Previous!=head.Hash)throw new InvalidDataException("EXPLORATORY_CAS_CONFLICT");
            ExploratoryInvariants.Validate(p,head.Payload);
            await using var insert=new NpgsqlCommand("INSERT INTO paper_exploratory.events VALUES($1,$2,$3,$4,$5)",c,tx);
            insert.Parameters.AddWithValue(cohort);insert.Parameters.AddWithValue(e.Revision);insert.Parameters.AddWithValue(e.Payload);
            insert.Parameters.AddWithValue(e.Previous);insert.Parameters.AddWithValue(e.Hash);await insert.ExecuteNonQueryAsync(ct);
            head=new(e.Revision,e.Hash,e.Payload);
        }
        await tx.CommitAsync(ct);return head;
    }
}
