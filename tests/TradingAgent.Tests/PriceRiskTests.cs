using System.Text.Json;
using System.Text.Json.Nodes;
using TradingAgent.Api;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Npgsql;
using Xunit;
namespace TradingAgent.Tests;

public class PriceRiskTests
{
    [Theory][InlineData("Compara R1, R5 y R10",false)][InlineData("Dame las comisiones de R5",false)][InlineData("Cuánto arriesga realmente R10",true)][InlineData("R10 Experimental",true)]
    public void LocalSolDoesNotHijackOriginalPortfolioComparisons(string question,bool matches)=>Assert.Equal(matches,PriceRiskChat.Matches(question));
    [Theory][InlineData(0,"RECENT_JOURNAL")][InlineData(121,"STALE")][InlineData(-1,"STALE")]
    public void DashboardDoesNotHideStaleOrFutureHeartbeat(int age,string quality)
    {var now=DateTimeOffset.UtcNow;var s=new JsonObject{["updated_at"]=now.AddSeconds(-age).ToString("O"),["status"]="SHADOW_RUNNING"};PriceRiskFreshness.Apply(s,now);Assert.Equal(quality,s["evidenceQuality"]!.GetValue<string>());}
    static JsonObject Payload(string id)=>JsonSerializer.SerializeToNode(new{experiment=id,scope="R10_PRICE_RISK_EXPERIMENTAL",classification="SIMULATED_SHADOW",live_enabled=false,broker_orders=0,state=new{protocol=new{price_risk_budget_usd="10",initial_capital_usd="100",all_in_loss_cap_usd="15",broker_orders_enabled=false,live_enabled=false},reserved="0",consumed_loss="1",engine_hash="frozen",trades=Array.Empty<object>(),seen=new[]{"one"},active=(object?)null}})!.AsObject();
    static JsonElement Element(JsonNode p)=>JsonSerializer.SerializeToElement(p);
    static ShadowEvent Event(JsonObject p,long rev=1,string previous="")
    {var payload=p.ToJsonString();var material=$"[{rev},{payload},{JsonSerializer.Serialize(previous)}]";return new(rev,payload,previous,Evidence.Hash(material),material);}
    [Theory][InlineData("live_enabled",true)][InlineData("broker_orders",1)][InlineData("classification","BROKER_PAPER_EXECUTION")]
    public void CannotClaimBrokerAuthority(string key,object value){var p=Payload("x");p[key]=JsonSerializer.SerializeToNode(value);Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),null));}
    [Fact]public void CannotEraseLossOnRestart(){var old=Payload("x");var p=old.DeepClone();p["state"]!["consumed_loss"]="0";Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),old.ToJsonString()));}
    [Fact]public void CannotChangeProtocol(){var old=Payload("x");var p=old.DeepClone();p["state"]!["protocol"]!["price_risk_budget_usd"]="15";Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),old.ToJsonString()));}
    [Fact]public void CannotForgetSignal(){var old=Payload("x");var p=old.DeepClone();p["state"]!["seen"]=new JsonArray();Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),old.ToJsonString()));}
    [Fact]public void CannotLosePendingPosition(){var old=Payload("x");old["state"]!["active"]=new JsonObject{["id"]="open"};var p=old.DeepClone();p["state"]!["active"]=null;Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),old.ToJsonString()));}
    [Fact]public void CannotLeverageReserve(){var p=Payload("x");p["state"]!["reserved"]="100.01";Assert.Throws<InvalidDataException>(()=>PriceRiskStore.Validate(Element(p),null));}
    [DatabaseFact]public async Task PersistentRestartCasTamperAndImmutableJournal()
    {
        var connection=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(connection).Migrate();var id="r10-price-"+Guid.NewGuid().ToString("N");var s=new PriceRiskStore(connection);var e=Event(Payload(id));var head=await s.Execute(id,e);
        Assert.Equal(head,await new PriceRiskStore(connection).Execute(id,null));
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.Execute(id,e));
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.Execute(id,Event(Payload(id),2,head.Hash) with{Hash="tampered"}));
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync();await using var cmd=new NpgsqlCommand("DELETE FROM price_risk.events WHERE experiment_id=$1",c);cmd.Parameters.AddWithValue(id);await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [Fact]public async Task RefusesNonPaperDatabase()=>await Assert.ThrowsAsync<InvalidDataException>(()=>new PriceRiskStore("Host=127.0.0.1;Port=5432;Username=other;Database=postgres").Execute("r10-price-"+Guid.NewGuid().ToString("N"),null));
    [Fact]public void SolShowsSeparateEvidenceWithoutInventingFees()
    {
        var p=JsonSerializer.SerializeToElement(new{last_assessment=new{price_risk=".06",estimated_fees=(string?)null,estimated_all_in_loss="4.3",reason="TARGET_DOES_NOT_COVER_COSTS"},status="SHADOW_RUNNING",trades=Array.Empty<object>()});
        var snapshot=JsonSerializer.SerializeToElement(new{prediction=new{}});var r=PriceRiskChat.Respond(new(Guid.NewGuid(),"R10 riesgo"),snapshot,p);
        Assert.Equal("LOCAL_EVIDENCE_ONLY",r["status"]!.GetValue<string>());Assert.Null(r["metrics"]![1]!["value"]);Assert.Equal(0,r["usage"]!["estimatedCostUsd"]!.GetValue<int>());Assert.Contains("Cierres Shadow: 0",r["text"]!.GetValue<string>());
    }
}
