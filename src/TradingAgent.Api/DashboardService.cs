using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using TradingAgent.Infrastructure;
namespace TradingAgent.Api;

public sealed record DashboardConfiguration(string Root,string? Study,string SolSession,decimal SolBudget)
{
    public static DashboardConfiguration Load()
    {
        var root=Path.GetFullPath(Environment.GetEnvironmentVariable("TRADING_UI_ROOT")??".");
        var budget=decimal.TryParse(Environment.GetEnvironmentVariable("TRADING_SOL_CHAT_BUDGET"),System.Globalization.NumberStyles.Number,System.Globalization.CultureInfo.InvariantCulture,out var b)?b:0;
        if(budget is <0 or >1)throw new InvalidOperationException("SOL_CHAT_BUDGET_INVALID");
        return new(root,Environment.GetEnvironmentVariable("TRADING_UI_STUDY"),"sol-ui-"+Guid.NewGuid().ToString("N"),budget);
    }
}
public interface IDashboardSource { Task<JsonElement> Read(CancellationToken ct=default); }
public sealed class DashboardSource(DashboardStore store,DashboardConfiguration config,PaperFeedService feed):IDashboardSource
{
    private readonly SemaphoreSlim gate=new(1,1);
    private string? prior;private JsonObject? cached;
    public async Task<JsonElement> Read(CancellationToken ct=default)
    {
        await gate.WaitAsync(ct);
        try
        {
            var e=await store.Snapshot(config.Study,ct);
            var research=Path.Combine(config.Root,"artifacts","research","ai-strategy-research","journal.sqlite3");
            var identity=(e.Head?.GetRawText()??"EMPTY")+(e.Exploratory?.GetRawText()??"")+(e.PriceRisk?.GetRawText()??"")+(e.AggressiveGrowth?.GetRawText()??"")+JsonSerializer.Serialize(e.Kronos)+File.GetLastWriteTimeUtc(research).Ticks+File.GetLastWriteTimeUtc(research+"-wal").Ticks;
            if(identity!=prior || cached is null)
            {
                cached=JsonNode.Parse(await Project(e,ct))!.AsObject();prior=identity;
            }
            var view=(JsonObject)cached.DeepClone();var now=DateTimeOffset.UtcNow;
            KronosFreshness.Apply(view["kronos"]?.AsObject(),now);
            PriceRiskFreshness.Apply(view["priceRisk"]?.AsObject(),now);
            AggressiveGrowthFreshness.Apply(view["aggressiveGrowth"]?.AsObject(),now);
            // Re-evaluate quality on every read even when the journal head did not change.
            var market=view["market"]!.AsObject();var at=market["at"]?.GetValue<string>();
            var stale=at is null || !DateTimeOffset.TryParse(at,out var timestamp) || now-timestamp>TimeSpan.FromSeconds(30) || now<timestamp;
            if(stale && at is not null)market["quality"]="STALE";
            if(at is not null && DateTimeOffset.TryParse(at,out var received))market["ageSeconds"]=(now-received).TotalSeconds;
            var shadowConnected=at is not null && !stale && view["studyStatus"]?.GetValue<string>()=="SHADOW_RESEARCH_RUNNING";
            view["at"]=now;
            var emergency=e.Emergency is true || File.Exists(Path.Combine(config.Root,".local","paper-lab.emergency"));
            view["system"]=JsonSerializer.SerializeToNode(new{
                connection="CONNECTED",ibkr=feed.Connected||shadowConnected?"CONNECTED_READ_ONLY":"DATA_UNAVAILABLE",postgres="VERIFIED",
                mode=e.Exploratory is null?"SIMULATED_SHADOW":"EURUSD_PAPER_EXPLORATORY",marketSource="IBKR_PAPER_READ_ONLY",liveEnabled=false,liveState="BLOCKED_BY_BACKEND",
                emergency=emergency?"ACTIVE":e.Emergency is false?"INACTIVE_REPORTED_BY_JOURNAL":"UNKNOWN",
                paperAuto="UI_NOT_AUTHORIZED",accountBinding=File.Exists(Path.Combine(config.Root,".local","ibkr-account-binding.dpapi"))?"PROTECTED_PRESENT":"DATA_UNAVAILABLE",
                sol=string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("OPENAI_API_KEY"))?"LOCAL_EVIDENCE_ONLY":config.SolBudget>0?"CONFIGURED_NOT_VERIFIED":"BUDGET_DISABLED",
                solBudget=config.SolBudget,ordersSupported=false,lastUpdate=now,sourceUpdate=at
            });
            return JsonSerializer.SerializeToElement(view);
        }
        finally{gate.Release();}
    }
    private async Task<string> Project(DashboardEnvelope envelope,CancellationToken ct)
    {
        using var process=new Process{StartInfo=new(Path.Combine(config.Root,".venv","Scripts","python.exe")){
            RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=config.Root}};
        var keep=new[]{"PATH","SystemRoot","TEMP","TMP"};var basics=process.StartInfo.Environment.Where(x=>keep.Contains(x.Key,StringComparer.OrdinalIgnoreCase)).ToArray();
        process.StartInfo.Environment.Clear();foreach(var p in basics)process.StartInfo.Environment[p.Key]=p.Value;
        process.StartInfo.Environment["PYTHONPATH"]=Path.Combine(config.Root,"python");process.StartInfo.Environment["PYTHONIOENCODING"]="utf-8";
        process.StartInfo.ArgumentList.Add("-m");process.StartInfo.ArgumentList.Add("trading_agent.dashboard_projection");
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(15));
        try
        {
            process.Start();var output=process.StandardOutput.ReadToEndAsync(timeout.Token);var errors=process.StandardError.ReadToEndAsync(timeout.Token);
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new{root=config.Root,envelope=new{head=envelope.Head,observation=envelope.Observation,revision=envelope.Revision,quotes=envelope.Quotes,exploratory=envelope.Exploratory,kronos=envelope.Kronos,priceRisk=envelope.PriceRisk,aggressiveGrowth=envelope.AggressiveGrowth}}));process.StandardInput.Close();
            await process.WaitForExitAsync(timeout.Token);var text=await output;await errors;
            if(process.ExitCode!=0 || text.Length>2_000_000)throw new InvalidOperationException("DASHBOARD_SOURCE_UNAVAILABLE");return text;
        }
        finally{if(process.IdSafe()&&!process.HasExited)process.Kill(true);}
    }
}

public static class PriceRiskFreshness
{
    public static void Apply(JsonObject? state,DateTimeOffset now)
    {
        if(state is null)return;
        var fresh=state["updated_at"]?.GetValue<string>() is string at && DateTimeOffset.TryParse(at,out var t) && now>=t && now-t<=TimeSpan.FromSeconds(120);
        state["evidenceQuality"]=fresh?"RECENT_JOURNAL":"STALE";
        if(!fresh && state["status"]?.GetValue<string>()=="SHADOW_RUNNING")state["status"]="SHADOW_HEARTBEAT_STALE";
    }
}
public static class KronosFreshness
{
    // Cached projections cannot keep advertising health after an observer disconnect.
    public static void Apply(JsonObject? view,DateTimeOffset now)
    {
        if(view is null)return;
        var offline=view["heartbeatAt"]?.GetValue<string>() is not string hb || !DateTimeOffset.TryParse(hb,out var hbt) || now<hbt || now-hbt>TimeSpan.FromSeconds(120);
        var stale=view["latest"]?["candle_timestamp"]?.GetValue<string>() is not string at || !DateTimeOffset.TryParse(at,out var timestamp) || now<timestamp || now-timestamp>TimeSpan.FromSeconds(view["latest"]?["max_prediction_age_seconds"]?.GetValue<int>()??3900);
        if(offline){view["status"]="KRONOS_UNAVAILABLE";view["operationalHealth"]="UNAVAILABLE";view["reason"]="OBSERVER_HEARTBEAT_MISSING_OR_STALE";}
        if(stale)
        {
            view["stale"]=true;view["calibrationState"]="CALIBRATION_INSUFFICIENT";
            if(view["status"]?.GetValue<string>()=="KRONOS_READY"){view["status"]="KRONOS_DEGRADED";view["operationalHealth"]="DEGRADED";}
            if(!offline)view["reason"]="PREDICTION_MISSING_OR_STALE";
        }
        if(view["diagnostics"] is JsonObject d)
        {
            d["operational_health"]=view["operationalHealth"]?.DeepClone();
            var reasons=d["reasons"] as JsonArray ?? new JsonArray();
            foreach(var reason in new[]{offline?"OBSERVER_HEARTBEAT_MISSING_OR_STALE":null,stale?"PREDICTION_MISSING_OR_STALE":null})
                if(reason is not null&&!reasons.Any(r=>r?.GetValue<string>()==reason))reasons.Add(reason);
            if(d["reasons"] is null)d["reasons"]=reasons;
        }
    }
}
