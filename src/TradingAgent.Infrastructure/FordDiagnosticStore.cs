using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed record FordDiagnosticEvent(long Revision,string At,string Kind,string Payload,string Previous,string Hash,string Material);
public sealed record FordDiagnosticHead(long Revision,string Hash);
public sealed partial class PostgresStore
{
    public async Task<FordDiagnosticHead> AppendFordDiagnostic(string trial,string binding,string scope,
        FordDiagnosticEvent[] events,CancellationToken ct=default)
    {
        if(!Regex.IsMatch(trial,"^ford-diag-[a-f0-9]{32}$") || string.IsNullOrWhiteSpace(binding) || binding.Length>100 ||
            scope is not (FordDiagnosticRisk.Scope or FordDiagnosticRisk.R10Scope) || events.Length>50)
            throw new InvalidDataException("FORD_DIAGNOSTIC_EVIDENCE_SCOPE_REQUIRED");
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var permissions=new NpgsqlCommand("SELECT has_table_privilege(current_user,'paper_lab.ford_diagnostic_events','SELECT') AND has_table_privilege(current_user,'paper_lab.ford_diagnostic_events','INSERT')",c,tx))
            if(await permissions.ExecuteScalarAsync(ct) is not true)throw new InvalidDataException("FORD_DIAGNOSTIC_EVIDENCE_PERMISSIONS_REQUIRED");
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,73165))",c,tx))
        {guard.Parameters.AddWithValue(trial);await guard.ExecuteNonQueryAsync(ct);}
        var head=new FordDiagnosticHead(0,"");
        await using(var read=new NpgsqlCommand("SELECT revision,event_hash FROM paper_lab.ford_diagnostic_events WHERE trial_id=$1 ORDER BY revision DESC LIMIT 1",c,tx))
        {read.Parameters.AddWithValue(trial);await using var rows=await read.ExecuteReaderAsync(ct);if(await rows.ReadAsync(ct))head=new(rows.GetInt64(0),rows.GetString(1));}
        foreach(var e in events)
        {
            using var payload=JsonDocument.Parse(e.Payload);using var material=JsonDocument.Parse(e.Material);
            var state=payload.RootElement.GetProperty("state");var m=material.RootElement;
            if(e.Revision<1 || e.Revision>20000 || e.Kind.Length>100 || e.Material.Length>512000 ||
                Evidence.Hash(e.Material)!=e.Hash || m.GetArrayLength()!=5 || m[0].GetInt64()!=e.Revision ||
                m[1].GetString()!=e.At || m[2].GetString()!=e.Kind || m[3].GetRawText()!=e.Payload || m[4].GetString()!=e.Previous ||
                state.GetProperty("trial_id").GetString()!=trial || state.GetProperty("binding_id").GetString()!=binding ||
                state.GetProperty("scope").GetString()!=scope || state.GetProperty("environment").GetString()!="PAPER_TRADING" ||
                state.GetProperty("classification").GetString()!="EXECUTION_DIAGNOSTICS" ||
                state.GetProperty("strategy_version").ValueKind!=JsonValueKind.Null)
                throw new InvalidDataException("FORD_DIAGNOSTIC_EVIDENCE_INTEGRITY_FAILURE");
            if(e.Revision<=head.Revision)
            {
                await using var check=new NpgsqlCommand("SELECT event_hash,binding_id,scope FROM paper_lab.ford_diagnostic_events WHERE trial_id=$1 AND revision=$2",c,tx);
                check.Parameters.AddWithValue(trial);check.Parameters.AddWithValue(e.Revision);
                await using var rows=await check.ExecuteReaderAsync(ct);
                if(!await rows.ReadAsync(ct) || rows.GetString(0)!=e.Hash || rows.GetString(1)!=binding || rows.GetString(2)!=scope)
                    throw new InvalidDataException("FORD_DIAGNOSTIC_EVIDENCE_REPLAY_CONFLICT");
                continue;
            }
            if(e.Revision!=head.Revision+1 || e.Previous!=head.Hash)throw new InvalidDataException("FORD_DIAGNOSTIC_EVIDENCE_CHAIN_GAP");
            await using var insert=new NpgsqlCommand("INSERT INTO paper_lab.ford_diagnostic_events VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",c,tx);
            insert.Parameters.AddWithValue(trial);insert.Parameters.AddWithValue(e.Revision);insert.Parameters.AddWithValue(binding);
            insert.Parameters.AddWithValue(scope);insert.Parameters.AddWithValue(DateTimeOffset.Parse(e.At).ToUniversalTime());
            insert.Parameters.AddWithValue(e.Kind);insert.Parameters.AddWithValue(e.Payload);insert.Parameters.AddWithValue(e.Previous);insert.Parameters.AddWithValue(e.Hash);
            await insert.ExecuteNonQueryAsync(ct);head=new(e.Revision,e.Hash);
        }
        await tx.CommitAsync(ct);return head;
    }
}
