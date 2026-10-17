using System.Text.Json;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using TradingAgent.Core;
namespace TradingAgent.Api;

[Authorize(AuthenticationSchemes="Dashboard")]
public sealed class DashboardHub:Hub { } // Client connections cannot invoke mutating methods.
public sealed record DashboardEvent(long Sequence,string Type,JsonElement Data,DateTimeOffset At);
public static class DashboardChanges
{
    public static IEnumerable<(string Type,JsonElement Data)> Diff(JsonElement? previous,JsonElement next)
    {
        if(next.TryGetProperty("aggressiveGrowth",out var growth) && (previous is null || !previous.Value.TryGetProperty("aggressiveGrowth",out var oldGrowth) || oldGrowth.GetRawText()!=growth.GetRawText()))yield return("aggressiveGrowth.updated",growth);
        if(next.TryGetProperty("priceRisk",out var priceRisk) && (previous is null || !previous.Value.TryGetProperty("priceRisk",out var oldPriceRisk) || oldPriceRisk.GetRawText()!=priceRisk.GetRawText()))yield return("priceRisk.updated",priceRisk);
        if(next.TryGetProperty("rotation",out var rotation) && (previous is null || !previous.Value.TryGetProperty("rotation",out var old) || old.GetRawText()!=rotation.GetRawText()))yield return("rotation.updated",rotation);
        if(next.TryGetProperty("kronos",out var kronos) && (previous is null || !previous.Value.TryGetProperty("kronos",out var kp) || kp.GetRawText()!=kronos.GetRawText()))yield return("kronos.updated",kronos);
        foreach(var (field,type) in new[]{("system","connection.updated"),("studyStatus","study.updated"),("experiments","experiment.updated"),("market","market.quote.updated"),
            ("prediction","prediction.updated"),("openPositions","position.updated"),("trades","trade.completed"),("calibration","research.updated"),("research","journal.updated"),("notifications","notification.updated")})
        {
            var n=next.GetProperty(field);
            if(previous is null || !previous.Value.TryGetProperty(field,out var p) || Evidence.Hash(p.GetRawText())!=Evidence.Hash(n.GetRawText()))yield return(type,n);
        }
    }
}
public sealed class DashboardBroadcaster(IDashboardSource source,IHubContext<DashboardHub> hub,ILogger<DashboardBroadcaster> log):BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        JsonElement? prior=null;long sequence=0;
        using var timer=new PeriodicTimer(TimeSpan.FromSeconds(2));
        do
        {
            try
            {
                var next=await source.Read(ct);
                foreach(var (type,data) in DashboardChanges.Diff(prior,next))await hub.Clients.All.SendAsync("event",new DashboardEvent(++sequence,type,data,DateTimeOffset.UtcNow),ct);
                prior=next;
            }
            catch(OperationCanceledException) when(ct.IsCancellationRequested){break;}
            catch(Exception e)
            {
                log.LogWarning("Dashboard source unavailable: {Type}",e.GetType().Name);
                await hub.Clients.All.SendAsync("event",new DashboardEvent(++sequence,"source.unavailable",JsonSerializer.SerializeToElement(new{status="DATA_UNAVAILABLE"}),DateTimeOffset.UtcNow),ct);
            }
        }while(await timer.WaitForNextTickAsync(ct));
    }
}
