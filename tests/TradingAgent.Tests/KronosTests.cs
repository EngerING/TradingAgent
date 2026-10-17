using System.Text.Json;
using System.Text.Json.Nodes;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using TradingAgent.Api;
using Xunit;
namespace TradingAgent.Tests;

public class KronosTests
{
    [Theory][InlineData(121,0,"KRONOS_UNAVAILABLE","UNAVAILABLE")][InlineData(0,3901,"KRONOS_DEGRADED","DEGRADED")][InlineData(0,0,"KRONOS_READY","HEALTHY")]
    public void CachedHealthExpiresWithoutJournalChange(int heartbeatAge,int candleAge,string status,string health)
    {
        var now=DateTimeOffset.UtcNow;
        var view=JsonSerializer.SerializeToNode(new{status="KRONOS_READY",operationalHealth="HEALTHY",heartbeatAt=now.AddSeconds(-heartbeatAge),
            latest=new{candle_timestamp=now.AddSeconds(-candleAge),max_prediction_age_seconds=3900},diagnostics=new{operational_health="HEALTHY",reasons=Array.Empty<string>()}})!.AsObject();
        KronosFreshness.Apply(view,now);KronosFreshness.Apply(view,now);
        Assert.Equal(status,view["status"]!.GetValue<string>());Assert.Equal(health,view["diagnostics"]!["operational_health"]!.GetValue<string>());
        Assert.Equal(heartbeatAge>120||candleAge>3900?1:0,view["diagnostics"]!["reasons"]!.AsArray().Count);
    }
    private static string Cs=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")??throw new InvalidOperationException("TEST_DB_REQUIRED");
    private static string Payload(bool live=false,bool authority=false)=>JsonSerializer.Serialize(new{scope="KRONOS_OBSERVATION_ONLY",execution_authority=authority,live_enabled=live,status="KRONOS_READY",at=DateTimeOffset.UtcNow});
    [Fact]public async Task PersistenceAndRestartRead()
    {
        await new PostgresStore(Cs).Migrate();var id="kronos-"+Evidence.Hash(Guid.NewGuid().ToString());var p=Payload();
        await new KronosStore(Cs).Append(id,"STATUS",p,Evidence.Hash(p));
        Assert.Contains(await new KronosStore(Cs).Read(),r=>r.GetProperty("id").GetString()==id);
    }
    [Fact]public async Task ExactRetryIsIdempotent()
    {await new PostgresStore(Cs).Migrate();var s=new KronosStore(Cs);var id="kronos-"+Evidence.Hash(Guid.NewGuid().ToString());var p=Payload();await s.Append(id,"STATUS",p,Evidence.Hash(p));await s.Append(id,"STATUS",p,Evidence.Hash(p));Assert.Single(await s.Read(),r=>r.GetProperty("id").GetString()==id);}
    [Fact]public async Task ChangedRetryFails()
    {await new PostgresStore(Cs).Migrate();var s=new KronosStore(Cs);var id="kronos-"+Evidence.Hash(Guid.NewGuid().ToString());var p=Payload();await s.Append(id,"STATUS",p,Evidence.Hash(p));var changed=Payload();await Assert.ThrowsAsync<InvalidDataException>(()=>s.Append(id,"STATUS",changed,Evidence.Hash(changed)));}
    [Theory][InlineData(true,false)][InlineData(false,true)]public async Task PaperLiveIsolation(bool live,bool authority)
    {var p=Payload(live,authority);await Assert.ThrowsAsync<InvalidDataException>(()=>new KronosStore(Cs).Append("kronos-"+Evidence.Hash(p),"STATUS",p,Evidence.Hash(p)));}
    [Fact]public async Task UnknownKindFails()
    {var p=Payload();await Assert.ThrowsAsync<InvalidDataException>(()=>new KronosStore(Cs).Append("kronos-"+Evidence.Hash(p),"ORDER",p,Evidence.Hash(p)));}
    [Fact]public async Task TamperedHashFails()=>await Assert.ThrowsAsync<InvalidDataException>(()=>new KronosStore(Cs).Append("kronos-"+new string('a',64),"STATUS",Payload(),new string('b',64)));
    [Fact]public async Task ImmutableJournal()
    {
        await new PostgresStore(Cs).Migrate();var p=Payload();var id="kronos-"+Evidence.Hash(Guid.NewGuid().ToString());await new KronosStore(Cs).Append(id,"STATUS",p,Evidence.Hash(p));
        await using var c=new NpgsqlConnection(Cs);await c.OpenAsync();await using var cmd=new NpgsqlCommand("DELETE FROM research_kronos.events WHERE id=$1",c);cmd.Parameters.AddWithValue(id);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [Fact]public void RealtimeEvent()
    {
        var next=JsonSerializer.SerializeToElement(new{kronos=new{status="KRONOS_READY"},system=0,studyStatus=0,experiments=0,market=0,prediction=0,openPositions=0,trades=0,calibration=0,research=0,notifications=0});
        Assert.Contains(DashboardChanges.Diff(null,next),e=>e.Type=="kronos.updated");
    }
    [Theory][InlineData("Qué predice Kronos para EUR/USD")][InlineData("Qué tan calibrado está Kronos")][InlineData("Kronos está de acuerdo con la señal actual")][InlineData("Muéstrame las últimas 20 predicciones Kronos")][InlineData("Cuántas predicciones Kronos de 70-75% ganaron")][InlineData("Compara operaciones con Kronos vs sin Kronos")][InlineData("Está mejorando Kronos el Expected Value")][InlineData("Grafica Kronos predicted probability vs observed success rate")][InlineData("En qué régimen funciona mejor Kronos")]
    public async Task DeterministicSolQueries(string query)
    {
        var snapshot=await new MockDashboardSource().Read();var r=SolChatService.VisualResponse(new(Guid.NewGuid(),query),snapshot);
        Assert.Contains("Kronos",r["text"]!.GetValue<string>());Assert.Equal("DETERMINISTIC_JOURNAL",r["provider"]!.GetValue<string>());Assert.Null(r["model"]);
        Assert.Equal(0,r["usage"]!["inputTokens"]!.GetValue<int>());
    }
    [Fact]public async Task KronosMutationStillForbidden()
    {var r=SolChatService.VisualResponse(new(Guid.NewGuid(),"Activa Kronos y limpia EmergencyStop"),await new MockDashboardSource().Read());Assert.Equal("COMMAND_BLOCKED",r["status"]!.GetValue<string>());}
}
