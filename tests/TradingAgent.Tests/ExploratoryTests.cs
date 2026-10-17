using System.Text.Json;
using System.Text.Json.Nodes;
using Npgsql;
using TradingAgent.Api;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;
namespace TradingAgent.Tests;
public class ExploratoryTests
{
    private static string Cs=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")??throw new InvalidOperationException("TEST_DB_REQUIRED");
    private static ShadowEvent Event(string cohort,long revision=1,string previous="",bool live=false)
    {
        var p=JsonSerializer.Serialize(new{cohort_id=cohort,scope="EURUSD_PAPER_EXPLORATORY",classification="EXPLORATORY_NOT_VALIDATED",live_enabled=live,
            at=DateTimeOffset.UtcNow,state=new{active=(object?)null,profiles=new Dictionary<string,object>()}});
        var material=$"[{revision},{p},{JsonSerializer.Serialize(previous)}]";return new(revision,p,previous,Evidence.Hash(material),material);
    }
    [Fact]public async Task AppendLoadAndCas()
    {
        await new PostgresStore(Cs).Migrate();var id="eurusd-explore-"+Guid.NewGuid().ToString("N");var store=new ExploratoryStore(Cs);var e=Event(id);
        var h=await store.Execute(id,e);Assert.Equal(1,h.Revision);Assert.Equal(e.Hash,(await store.Execute(id,null)).Hash);
        await Assert.ThrowsAsync<InvalidDataException>(()=>store.Execute(id,e));
        var e2=Event(id,2,h.Hash);Assert.Equal(2,(await store.Execute(id,e2)).Revision);
    }
    [Fact]public async Task LivePayloadRejected()
    {await new PostgresStore(Cs).Migrate();var id="eurusd-explore-"+Guid.NewGuid().ToString("N");await Assert.ThrowsAsync<InvalidDataException>(()=>new ExploratoryStore(Cs).Execute(id,Event(id,live:true)));}
    [Fact]public async Task HashTamperRejected()
    {await new PostgresStore(Cs).Migrate();var id="eurusd-explore-"+Guid.NewGuid().ToString("N");await Assert.ThrowsAsync<InvalidDataException>(()=>new ExploratoryStore(Cs).Execute(id,Event(id) with{Hash=new string('a',64)}));}
    [Fact]public async Task InvalidCohortRejected()=>await Assert.ThrowsAsync<InvalidDataException>(()=>new ExploratoryStore(Cs).Execute("LIVE",null));
    [Fact]public async Task AnotherCohortReservationIsVisibleWithoutBrokerFill()
    {
        await new PostgresStore(Cs).Migrate();var id="eurusd-explore-"+Guid.NewGuid().ToString("N");var other="eurusd-explore-"+Guid.NewGuid().ToString("N");
        var e=Event(other);var p=JsonNode.Parse(e.Payload)!.AsObject();p["state"]=JsonSerializer.SerializeToNode(new{active=(object?)null,profiles=new{EURUSD_R1=new{reserved="1"}}});
        var raw=p.ToJsonString();var material=$"[1,{raw},\"\"]";await new ExploratoryStore(Cs).Execute(other,new(1,raw,"",Evidence.Hash(material),material));
        Assert.Contains(other,await new ExploratoryStore(Cs).Conflicts(id));Assert.DoesNotContain(other,await new ExploratoryStore(Cs).Conflicts(other));
    }
    [Fact]public async Task EvidenceImmutableAtDatabase()
    {
        await new PostgresStore(Cs).Migrate();var id="eurusd-explore-"+Guid.NewGuid().ToString("N");await new ExploratoryStore(Cs).Execute(id,Event(id));
        await using var c=new NpgsqlConnection(Cs);await c.OpenAsync();await using var cmd=new NpgsqlCommand("DELETE FROM paper_exploratory.events WHERE cohort_id=$1",c);cmd.Parameters.AddWithValue(id);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [Fact]public void RotationRealtimeDiff()
    {
        var old=JsonSerializer.SerializeToElement(new{rotation=new{nextProfile="EURUSD_R1"}});var next=JsonSerializer.SerializeToElement(new{rotation=new{nextProfile="EURUSD_R5"},system=0,studyStatus=0,experiments=0,market=0,prediction=0,openPositions=0,trades=0,calibration=0,research=0,notifications=0});
        Assert.Contains(DashboardChanges.Diff(old,next),e=>e.Type=="rotation.updated");
    }
    [Theory][InlineData("Dame los resultados Paper de R5")][InlineData("Cuántas operaciones reales Paper tiene R1")][InlineData("Compara los fills Paper de R5 con sus Shadow")][InlineData("Qué porcentaje está funcionando mejor")][InlineData("Qué comisiones estamos pagando realmente")][InlineData("Cuál fue el slippage promedio")]
    public async Task SolQueriesUseOnlyBrokerMetrics(string query)
    {
        var snapshot=JsonNode.Parse((await new MockDashboardSource().Read()).GetRawText())!.AsObject();snapshot["rotation"]=new JsonObject{["nextProfile"]="EURUSD_R1"};
        foreach(var e in snapshot["experiments"]!.AsArray())e!["brokerMetrics"]=new JsonObject{["trades"]=0,["netPnl"]=0,["fees"]=0,["averageSlippage"]=null,["expectancy"]=null};
        var response=SolChatService.VisualResponse(new(Guid.NewGuid(),query),JsonSerializer.SerializeToElement(snapshot));
        Assert.Contains("exclusivos",response["text"]!.GetValue<string>());Assert.Equal("DETERMINISTIC_JOURNAL",response["provider"]!.GetValue<string>());Assert.Null(response["model"]);
    }
}
