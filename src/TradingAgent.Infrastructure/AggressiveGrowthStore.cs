using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;

namespace TradingAgent.Infrastructure;

// This append-only research boundary has no broker or authorization dependencies.
public sealed class AggressiveGrowthStore(string connection)
{
    // Existing ledgers retain observation/Stop/recovery. No new operational V1 IDs.
    public static void EnforceRetirement(int port,long revision,bool append)
    {
        if(port==55433 && revision==0 && append)
            throw new InvalidDataException("R20_V1_NEW_COHORT_RETIRED");
    }
    public static void Validate(JsonElement payload,string? previous)=>AggressiveGrowthInvariants.Validate(payload,previous);

    public async Task<ShadowHead> Execute(string experiment,ShadowEvent? e,CancellationToken ct=default)
    {
        if(!Regex.IsMatch(experiment,"^aggressive-r20-[a-f0-9]{32}$"))throw new InvalidDataException("R20_EXPERIMENT_SCOPE_REQUIRED");
        var cfg=new NpgsqlConnectionStringBuilder(connection);
        if(cfg.Host!="127.0.0.1" || cfg.Database!="postgres" ||
            !((cfg.Port==55433 && cfg.Username=="paper_lab_app")||(cfg.Port==55432 && cfg.Username=="trading_test")))
            throw new InvalidDataException("R20_PAPER_DATABASE_REQUIRED");
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync(ct);
        await using var tx=await c.BeginTransactionAsync(ct);
        await using(var guard=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,72020))",c,tx))
        {guard.Parameters.AddWithValue(experiment);await guard.ExecuteNonQueryAsync(ct);}
        var head=new ShadowHead(0,"");
        await using(var read=new NpgsqlCommand("SELECT revision,event_hash,payload FROM aggressive_growth.events WHERE experiment_id=$1 ORDER BY revision DESC LIMIT 1",c,tx))
        {
            read.Parameters.AddWithValue(experiment);await using var rows=await read.ExecuteReaderAsync(ct);
            if(await rows.ReadAsync(ct))head=new(rows.GetInt64(0),rows.GetString(1),rows.GetString(2));
        }
        EnforceRetirement(cfg.Port,head.Revision,e is not null);
        if(e is not null)
        {
            if(e.Material.Length>8_000_000 || e.Payload.Length>7_000_000)throw new InvalidDataException("R20_JOURNAL_SIZE_LIMIT");
            using var p=JsonDocument.Parse(e.Payload);using var m=JsonDocument.Parse(e.Material);
            if(Evidence.Hash(e.Material)!=e.Hash || m.RootElement.GetArrayLength()!=3 ||
                m.RootElement[0].GetInt64()!=e.Revision || m.RootElement[1].GetRawText()!=e.Payload ||
                m.RootElement[2].GetString()!=e.Previous || p.RootElement.GetProperty("experiment").GetString()!=experiment ||
                e.Revision!=head.Revision+1 || e.Previous!=head.Hash)
                throw new InvalidDataException("R20_INTEGRITY_OR_CAS_CONFLICT");
            Validate(p.RootElement,head.Payload);
            await using var insert=new NpgsqlCommand("INSERT INTO aggressive_growth.events(experiment_id,revision,payload,previous_hash,event_hash) VALUES($1,$2,$3,$4,$5)",c,tx);
            insert.Parameters.AddWithValue(experiment);insert.Parameters.AddWithValue(e.Revision);insert.Parameters.AddWithValue(e.Payload);
            insert.Parameters.AddWithValue(e.Previous);insert.Parameters.AddWithValue(e.Hash);await insert.ExecuteNonQueryAsync(ct);
            head=new(e.Revision,e.Hash,e.Payload);
        }
        await tx.CommitAsync(ct);return head;
    }
}
