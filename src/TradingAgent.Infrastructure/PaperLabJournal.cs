using System.Text.Json;
using System.Text.RegularExpressions;
using Npgsql;
using TradingAgent.Core;

namespace TradingAgent.Infrastructure;

public sealed record LabJournalSnapshot(long Revision,JsonElement? State);
public sealed class PaperLabJournal(string connectionString)
{
    private static AccountState? Strategy(JsonElement state) =>
        state.TryGetProperty("strategy_account",out var a) ? a.Deserialize<AccountState>(new JsonSerializerOptions(Evidence.Json) {
            NumberHandling=System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString }) : null;

    private static void PreserveStrategy(JsonElement? previous,JsonElement state)
    {
        var next=Strategy(state);var old=previous is null ? null : Strategy(previous.Value);
        if(next?.PaperContinuation is not null && (!PaperRiskProfile.HistoryConsistent(next) ||
            next.PolicyVersion!=PaperRiskProfile.Experimental || next.Capital?.Environment!="PAPER_TRADING" ||
            next.Capital.InitialCapital!=100 || next.Capital.LossAllowance!=20))
            throw new InvalidOperationException("LAB_STRATEGY_HISTORY_INVALID");
        if(old?.PaperContinuation is not null)
        {
            if(next?.PaperContinuation is null || next.Capital is null || old.Capital is null ||
                next.At<old.At || next.Capital.CumulativeRealizedLoss<old.Capital.CumulativeRealizedLoss ||
                old.PaperContinuation.Results?.Any(r=>!((next.PaperContinuation.Results??[]).Contains(r)))==true ||
                old.PaperContinuation.CancelledIds?.Any(id=>!(next.PaperContinuation.CancelledIds??[]).Contains(id))==true ||
                old.PaperContinuation.PendingId is string pending && next.PaperContinuation.PendingId!=pending &&
                    !(next.PaperContinuation.Results??[]).Any(r=>r.Id==pending) &&
                    !(next.PaperContinuation.CancelledIds??[]).Contains(pending) ||
                old.Halts.Any(h=>!next.Halts.Contains(h)))
                throw new InvalidOperationException("LAB_STRATEGY_HISTORY_RESET_FORBIDDEN");
        }
        else if(next?.PaperContinuation is not null && old?.Capital is { } capital &&
            (capital.RealizedNetPnl!=0 || capital.RealizedCosts!=0 || capital.ConsumedLoss!=0 ||
             old.ReservationId is not null || old.OpenPositions.Length+old.PendingOrders.Length>0 || old.Halts.Length>0))
            throw new InvalidOperationException("LAB_STRATEGY_HISTORY_MIGRATION_REQUIRED");
    }
    private static void Scope(string account)
    {if(!Regex.IsMatch(account,"^PAPER-[a-f0-9]{16}$"))throw new ArgumentException("INVALID_LAB_SCOPE");}
    private static void PreserveDiagnostics(JsonElement? previous,JsonElement state)
    {
        if(!state.TryGetProperty("orders",out var orders))return;
        if(orders.EnumerateObject().Count(o=>o.Value.TryGetProperty("category",out var c) && c.GetString()=="PAPER_DIAGNOSTIC")>1)
            throw new InvalidOperationException("LAB_SINGLE_DIAGNOSTIC_ONLY");
        if(previous is null || !previous.Value.TryGetProperty("orders",out var oldOrders))return;
        foreach(var old in oldOrders.EnumerateObject().Where(o=>o.Value.TryGetProperty("category",out var c) && c.GetString()=="PAPER_DIAGNOSTIC"))
        {
            if(!orders.TryGetProperty(old.Name,out var next))throw new InvalidOperationException("LAB_DIAGNOSTIC_HISTORY_RESET_FORBIDDEN");
            foreach(var field in new[]{"intent","session_id","category","contract_id","client_id","order_ids","quantity","entry","stop","target","payload","sent_at","reserve",
                "first_open_fill_received_at","close_deadline_at","close_requested_at","close_requested_price","close_requested_quantity"})
                if(old.Value.TryGetProperty(field,out var value) && (!next.TryGetProperty(field,out var updated) || !JsonElement.DeepEquals(value,updated)))
                    throw new InvalidOperationException("LAB_DIAGNOSTIC_INTENT_IMMUTABLE");
            foreach(var field in new[]{"fills","commissions"})
                if(old.Value.TryGetProperty(field,out var values))
                    foreach(var value in values.EnumerateObject())
                        if(!next.TryGetProperty(field,out var updates) || !updates.TryGetProperty(value.Name,out var updated) || !JsonElement.DeepEquals(value.Value,updated))
                            throw new InvalidOperationException("LAB_DIAGNOSTIC_EXECUTION_HISTORY_IMMUTABLE");
            foreach(var field in new[]{"cancel_parent_sent","timeout_close_sent"})
                if(old.Value.TryGetProperty(field,out var sent) && sent.ValueKind==JsonValueKind.True &&
                    (!next.TryGetProperty(field,out var retained) || retained.ValueKind!=JsonValueKind.True))
                    throw new InvalidOperationException("LAB_DIAGNOSTIC_ATTEMPT_RESET_FORBIDDEN");
        }
    }
    private static void PreserveRecovery(JsonElement? previous,JsonElement state)
    {
        if(previous is null)return;
        if(previous.Value.TryGetProperty("recovery_authorizations",out var grants))
            foreach(var used in grants.EnumerateObject())
                if(!state.TryGetProperty("recovery_authorizations",out var retained) || !retained.TryGetProperty(used.Name,out var value) || !JsonElement.DeepEquals(used.Value,value))
                    throw new InvalidOperationException("LAB_RECOVERY_AUTHORIZATION_RESET_FORBIDDEN");
        if(!previous.Value.TryGetProperty("orders",out var orders))return;
        foreach(var old in orders.EnumerateObject())
        {
            if(!old.Value.TryGetProperty("recovery_orders",out var recoveries))continue;
            if(!state.GetProperty("orders").TryGetProperty(old.Name,out var next) || !next.TryGetProperty("recovery_orders",out var kept))
                throw new InvalidOperationException("LAB_RECOVERY_HISTORY_RESET_FORBIDDEN");
            foreach(var recovery in recoveries.EnumerateObject())
                if(!kept.TryGetProperty(recovery.Name,out var value) || !JsonElement.DeepEquals(recovery.Value,value))
                    throw new InvalidOperationException("LAB_RECOVERY_ORDER_IMMUTABLE");
            if(old.Value.TryGetProperty("recovery_order_ids",out var ids))
                foreach(var id in ids.EnumerateArray())
                    if(!next.TryGetProperty("recovery_order_ids",out var updated) || !updated.EnumerateArray().Any(v=>JsonElement.DeepEquals(v,id)))
                        throw new InvalidOperationException("LAB_RECOVERY_HISTORY_RESET_FORBIDDEN");
        }
    }
    public async Task<LabJournalSnapshot> Load(string account,CancellationToken ct=default)
    {
        Scope(account);await using var c=new NpgsqlConnection(connectionString);await c.OpenAsync(ct);
        await using var cmd=new NpgsqlCommand("SELECT revision,payload::text FROM paper_lab.states WHERE account_key=$1",c);
        cmd.Parameters.AddWithValue(account);await using var r=await cmd.ExecuteReaderAsync(ct);
        if(!await r.ReadAsync(ct))return new(0,null);
        return new(r.GetInt64(0),JsonDocument.Parse(r.GetString(1)).RootElement.Clone());
    }
    public async Task<long> Commit(string account,long expected,JsonElement state,JsonElement reason,CancellationToken ct=default)
    {
        Scope(account);
        if(expected<0 || state.GetRawText().Length>4*1024*1024 || reason.GetRawText().Length>1024*1024 ||
            state.GetProperty("environment").GetString()!="PAPER_TRADING" || state.GetProperty("live_enabled").GetBoolean() ||
            state.GetProperty("account_key").GetString()!=account || Regex.IsMatch(state.GetRawText()+reason.GetRawText(),"DU(?:R)?[0-9]{4,}"))
            throw new ArgumentException("INVALID_LAB_STATE");
        await using var c=new NpgsqlConnection(connectionString);await c.OpenAsync(ct);await using var tx=await c.BeginTransactionAsync(ct);
        await using(var mutex=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,74182))",c,tx))
        {mutex.Parameters.AddWithValue(account);await mutex.ExecuteNonQueryAsync(ct);}
        await using(var check=new NpgsqlCommand("SELECT revision,payload::text FROM paper_lab.states WHERE account_key=$1 FOR UPDATE",c,tx))
        {
            check.Parameters.AddWithValue(account);await using var reader=await check.ExecuteReaderAsync(ct);
            var found=await reader.ReadAsync(ct);
            if((found?reader.GetInt64(0):0)!=expected)throw new InvalidOperationException("LAB_JOURNAL_CONFLICT");
            var previous=found?JsonDocument.Parse(reader.GetString(1)).RootElement:(JsonElement?)null;
            PreserveStrategy(previous,state);PreserveDiagnostics(previous,state);PreserveRecovery(previous,state);
        }
        var next=checked(expected+1);
        await using(var write=new NpgsqlCommand("INSERT INTO paper_lab.states(account_key,revision,payload) VALUES($1,$2,$3::jsonb) ON CONFLICT(account_key) DO UPDATE SET revision=$2,payload=$3::jsonb,updated_at=now()",c,tx))
        {write.Parameters.AddWithValue(account);write.Parameters.AddWithValue(next);write.Parameters.AddWithValue(state.GetRawText());await write.ExecuteNonQueryAsync(ct);}
        await using(var audit=new NpgsqlCommand("INSERT INTO paper_lab.events(account_key,revision,payload) VALUES($1,$2,$3::jsonb)",c,tx))
        {audit.Parameters.AddWithValue(account);audit.Parameters.AddWithValue(next);audit.Parameters.AddWithValue(reason.GetRawText());await audit.ExecuteNonQueryAsync(ct);}
        foreach(var item in state.GetProperty("experiences").EnumerateObject())
        {
            var category=item.Value.GetProperty("category").GetString();
            await using var insert=new NpgsqlCommand("INSERT INTO paper_lab.experience(id,account_key,category,payload) VALUES($1,$2,$3,$4::jsonb) ON CONFLICT(id) DO NOTHING",c,tx);
            insert.Parameters.AddWithValue(item.Name);insert.Parameters.AddWithValue(account);insert.Parameters.AddWithValue(category!);insert.Parameters.AddWithValue(item.Value.GetRawText());await insert.ExecuteNonQueryAsync(ct);
            await using var compare=new NpgsqlCommand("SELECT account_key=$2 AND payload=$3::jsonb FROM paper_lab.experience WHERE id=$1",c,tx);
            compare.Parameters.AddWithValue(item.Name);compare.Parameters.AddWithValue(account);compare.Parameters.AddWithValue(item.Value.GetRawText());
            if(await compare.ExecuteScalarAsync(ct) is not true)throw new InvalidOperationException("LAB_EXPERIENCE_CONFLICT");
        }
        await tx.CommitAsync(ct);return next;
    }
}
