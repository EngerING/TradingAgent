using System.Text.Json;
using Npgsql;
using TradingAgent.Core;

namespace TradingAgent.Infrastructure;

public sealed partial class PostgresStore
{
    public async Task<int> SavePaper(PaperEnvelope envelope,string expectedAccount,DateTimeOffset now,CancellationToken ct=default)
    {
        var data=PaperData.Validate(envelope,expectedAccount,now);
        await using var c=await Open(ct);await using var tx=await c.BeginTransactionAsync(ct);
        var inserted=0;
        if(envelope.Kind=="candles")
        {
            foreach(var bar in PaperData.Read<PaperCandle[]>(data))
            {
                var id=$"{expectedAccount}:IBKR:MIDPOINT:EURUSD:{bar.Minutes}:{bar.OpenedAt.ToUnixTimeSeconds()}";
                var payload=JsonSerializer.Serialize(bar,PaperData.Json);
                await using var cmd=new NpgsqlCommand("INSERT INTO market_candles(id,account_id,instrument,timeframe,occurred_at,payload) VALUES($1,$2,'EUR/USD',$3,$4,$5::jsonb) ON CONFLICT(account_id,instrument,timeframe,occurred_at) DO NOTHING",c,tx);
                cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(expectedAccount);cmd.Parameters.AddWithValue(bar.Minutes);
                cmd.Parameters.AddWithValue(bar.OpenedAt);cmd.Parameters.AddWithValue(payload);inserted+=await cmd.ExecuteNonQueryAsync(ct);
                await using var check=new NpgsqlCommand("SELECT payload=$5::jsonb FROM market_candles WHERE account_id=$1 AND instrument=$2 AND timeframe=$3 AND occurred_at=$4",c,tx);
                check.Parameters.AddWithValue(expectedAccount);check.Parameters.AddWithValue("EUR/USD");check.Parameters.AddWithValue(bar.Minutes);
                check.Parameters.AddWithValue(bar.OpenedAt);check.Parameters.AddWithValue(payload);
                if(await check.ExecuteScalarAsync(ct) is not true)throw new InvalidDataException("CONFLICTING_PAPER_CANDLE");
            }
        }
        else
        {
            var id=Evidence.Hash($"{expectedAccount}|{envelope.Kind}|{envelope.ReceivedAt:O}|{data.GetRawText()}");
            await using var cmd=new NpgsqlCommand("INSERT INTO paper_observations(id,account_id,kind,occurred_at,payload) VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT(id) DO NOTHING",c,tx);
            cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(expectedAccount);cmd.Parameters.AddWithValue(envelope.Kind);
            cmd.Parameters.AddWithValue(envelope.ReceivedAt);cmd.Parameters.AddWithValue(data.GetRawText());inserted=await cmd.ExecuteNonQueryAsync(ct);
        }
        await tx.CommitAsync(ct);return inserted;
    }

    public async Task<PaperEnvelope?> LatestPaper(string account,string kind,CancellationToken ct=default)
    {
        await using var c=await Open(ct);
        await using var cmd=new NpgsqlCommand("SELECT occurred_at,payload::text FROM paper_observations WHERE account_id=$1 AND kind=$2 ORDER BY occurred_at DESC,id DESC LIMIT 1",c);
        cmd.Parameters.AddWithValue(account);cmd.Parameters.AddWithValue(kind);
        await using var reader=await cmd.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct))return null;
        using var doc=JsonDocument.Parse(reader.GetString(1));
        return new(kind,account,reader.GetFieldValue<DateTimeOffset>(0),doc.RootElement.Clone());
    }

    public async Task<IReadOnlyList<PaperCandle>> PaperCandles(string account,int minutes,int limit=500,CancellationToken ct=default)
    {
        if(minutes is not (15 or 60 or 240) || limit is <1 or >2000)throw new ArgumentException("INVALID_SERIES_QUERY");
        await using var c=await Open(ct);
        await using var cmd=new NpgsqlCommand("SELECT payload::text FROM market_candles WHERE account_id=$1 AND instrument='EUR/USD' AND timeframe=$2 ORDER BY occurred_at DESC LIMIT $3",c);
        cmd.Parameters.AddWithValue(account);cmd.Parameters.AddWithValue(minutes);cmd.Parameters.AddWithValue(limit);
        await using var reader=await cmd.ExecuteReaderAsync(ct);var rows=new List<PaperCandle>();
        while(await reader.ReadAsync(ct))rows.Add(JsonSerializer.Deserialize<PaperCandle>(reader.GetString(0),PaperData.Json)??throw new InvalidDataException("MISSING_CANDLE"));
        rows.Reverse();return rows;
    }
}
