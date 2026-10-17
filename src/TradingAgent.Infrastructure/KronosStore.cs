using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;
namespace TradingAgent.Infrastructure;

public sealed class KronosStore(string connection)
{
    public static void Validate(string kind,JsonElement p)
    {
        if(kind is not ("PREDICTION" or "OUTCOME" or "STATUS" or "EVALUATION") || p.GetRawText().Length>250000 ||
            p.GetProperty("scope").GetString()!="KRONOS_OBSERVATION_ONLY" || p.GetProperty("execution_authority").GetBoolean() || p.GetProperty("live_enabled").GetBoolean())
            throw new InvalidDataException("KRONOS_OBSERVATION_REQUIRED");
        if(kind=="PREDICTION")
        {
            if(p.GetProperty("model").GetString()!="NeoQuasar/Kronos-base" || p.GetProperty("symbol").GetString()!="EUR/USD" ||
                p.GetProperty("timeframe").GetString() is not ("1H" or "15m" or "4H") || p.GetProperty("lookback").GetInt32() is <16 or >512 ||
                p.GetProperty("sample_count").GetInt32() is <2 or >128 || p.TryGetProperty("paths",out _))throw new InvalidDataException("KRONOS_PREDICTION_INVALID");
            foreach(var key in new[]{"model_version","tokenizer_version"})
                if(!Regex.IsMatch(p.GetProperty(key).GetString()!,"^[a-f0-9]{40}$"))throw new InvalidDataException("KRONOS_REVISION_REQUIRED");
            foreach(var key in new[]{"raw_tp_frequency","raw_sl_frequency","neither_frequency","calibrated_probability"})
                if(p.GetProperty(key).ValueKind!=JsonValueKind.Null && (p.GetProperty(key).GetDouble() is <0 or >1))throw new InvalidDataException("KRONOS_PROBABILITY_INVALID");
        }
    }
    private async Task<NpgsqlConnection> Open(CancellationToken ct)
    {
        var ep=new NpgsqlConnectionStringBuilder(connection);
        if(ep.Host!="127.0.0.1" || ep.Database!="postgres" || !((ep.Port==55433&&ep.Username=="paper_lab_app") || (ep.Port==55432&&ep.Username=="trading_test")))throw new InvalidDataException("KRONOS_PAPER_DB_REQUIRED");
        var c=new NpgsqlConnection(connection);await c.OpenAsync(ct);return c;
    }
    public async Task Append(string id,string kind,string payload,string hash,CancellationToken ct=default)
    {
        if(!Regex.IsMatch(id,"^kronos-[a-f0-9]{64}$") || Evidence.Hash(payload)!=hash)throw new InvalidDataException("KRONOS_HASH_REQUIRED");
        using var doc=JsonDocument.Parse(payload);Validate(kind,doc.RootElement);
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var cmd=new NpgsqlCommand("INSERT INTO research_kronos.events(id,kind,payload,event_hash) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",c,tx))
        {cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(kind);cmd.Parameters.AddWithValue(payload);cmd.Parameters.AddWithValue(hash);await cmd.ExecuteNonQueryAsync(ct);}
        await using(var cmd=new NpgsqlCommand("SELECT event_hash,kind FROM research_kronos.events WHERE id=$1",c,tx))
        {cmd.Parameters.AddWithValue(id);await using var r=await cmd.ExecuteReaderAsync(ct);await r.ReadAsync(ct);if(r.GetString(0)!=hash || r.GetString(1)!=kind)throw new InvalidDataException("KRONOS_DUPLICATE_CONFLICT");}
        await tx.CommitAsync(ct);
    }
    public async Task<JsonElement[]> Read(CancellationToken ct=default,bool compact=false)
    {
        await using var c=await Open(ct);var result=new List<JsonElement>();
        var limit=compact?20:2000;
        await using var cmd=new NpgsqlCommand($"SELECT id,kind,payload,event_hash FROM (SELECT *,row_number() OVER(PARTITION BY kind ORDER BY created_at DESC) AS n FROM research_kronos.events) ranked WHERE (kind IN ('PREDICTION','OUTCOME') AND n<={limit}) OR (kind='STATUS' AND n=1) OR (kind='EVALUATION' AND n<={(compact?2:20)}) ORDER BY created_at DESC",c);
        await using(var rows=await cmd.ExecuteReaderAsync(ct))
        {
          while(await rows.ReadAsync(ct))
          {
            var raw=rows.GetString(2);if(Evidence.Hash(raw)!=rows.GetString(3))throw new InvalidDataException("KRONOS_STORED_HASH_MISMATCH");
            result.Add(JsonSerializer.SerializeToElement(new{id=rows.GetString(0),kind=rows.GetString(1),payload=JsonSerializer.Deserialize<JsonElement>(raw)}));
          }
        }
        if(compact)
        {
            await using var count=new NpgsqlCommand("SELECT count(*) FILTER(WHERE kind='PREDICTION'),count(*) FILTER(WHERE kind='OUTCOME') FROM research_kronos.events",c);
            await using var r=await count.ExecuteReaderAsync(ct);await r.ReadAsync(ct);
            result.Add(JsonSerializer.SerializeToElement(new{id="READ_MODEL_TOTALS",kind="READ_MODEL_TOTALS",payload=new{predictions=r.GetInt64(0),evaluated=r.GetInt64(1),window=20,source="POSTGRESQL_COUNT_NOT_PERSISTED_EVENT"}}));
        }
        return result.ToArray();
    }
    public async Task<JsonElement?> Source(string? study,CancellationToken ct=default)
    {
        if(study is not null&&!Regex.IsMatch(study,"^eurusd-shadow-[a-f0-9]{32}$"))throw new InvalidDataException("KRONOS_SHADOW_STUDY_REQUIRED");
        await using var c=await Open(ct);
        await using var cmd=new NpgsqlCommand("SELECT payload,event_hash,revision,previous_hash FROM research_shadow.events WHERE ($1::text IS NULL OR study_id=$1) AND payload::jsonb->>'event'='COMMON_MARKET_OPPORTUNITY_EVALUATED' ORDER BY (payload::jsonb->>'at')::timestamptz DESC LIMIT 1",c);
        cmd.Parameters.AddWithValue((object?)study??DBNull.Value);await using var row=await cmd.ExecuteReaderAsync(ct);
        if(!await row.ReadAsync(ct))return null;
        return JsonSerializer.SerializeToElement(new{payload=JsonSerializer.Deserialize<JsonElement>(row.GetString(0)),hash=row.GetString(1),revision=row.GetInt64(2),previous=row.GetString(3)});
    }
}
