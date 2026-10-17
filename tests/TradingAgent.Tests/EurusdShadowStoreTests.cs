using System.Text.Json;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;
namespace TradingAgent.Tests;

public class EurusdShadowStoreTests
{
    static string Connection=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
    static string Study()=>"eurusd-shadow-"+Guid.NewGuid().ToString("N");
    static ShadowEvent Event(string study,long revision=1,string previous="",bool enabled=false)
    {
        var payload=JsonSerializer.Serialize(new{study_id=study,scope="EURUSD_SHADOW_R1_R5_R10",classification="SIMULATED_SHADOW",
            broker_orders=0,execution_authorized=enabled,live_enabled=false,state=new{loss="1"}});
        var material=$"[{revision},{payload},{JsonSerializer.Serialize(previous)}]";
        return new(revision,payload,previous,Evidence.Hash(material),material);
    }
    static async Task<PostgresStore> Store(){var s=new PostgresStore(Connection);await s.Migrate();return s;}
    [DatabaseFact]public async Task RestartAndReplayPreserveExactEvidence()
    {
        var s=await Store();var study=Study();var a=Event(study);var b=Event(study,2,a.Hash);
        var head=await s.AppendShadow(study,[a,b]);Assert.Equal(2,head.Revision);
        Assert.Equal(head,await new PostgresStore(Connection).AppendShadow(study,[a,b]));
        Assert.Equal(head,await s.AppendShadow(study,[]));
    }
    [DatabaseFact]public async Task GapRollsBackBatch()
    {
        var s=await Store();var study=Study();var a=Event(study);
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendShadow(study,[a,Event(study,3,a.Hash)]));
        Assert.Equal(0,(await s.AppendShadow(study,[])).Revision);
    }
    [DatabaseFact]public async Task HashTamperRejected()
    {
        var s=await Store();var study=Study();await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendShadow(study,[Event(study) with{Hash=new string('a',64)}]));
    }
    [DatabaseFact]public async Task CrossStudyRejected()
    {
        var s=await Store();await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendShadow(Study(),[Event(Study())]));
    }
    [DatabaseFact]public async Task OrderAuthorizationCannotBeStoredAsShadowEvidence()
    {
        var s=await Store();var study=Study();await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendShadow(study,[Event(study,enabled:true)]));
    }
    [DatabaseFact]public async Task ChangedReplayRejected()
    {
        var s=await Store();var study=Study();await s.AppendShadow(study,[Event(study)]);
        var a=Event(study);var material=a.Material.Replace("\"1\"","\"2\"");
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendShadow(study,[a with{Material=material,Payload=a.Payload.Replace("\"1\"","\"2\""),Hash=Evidence.Hash(material)}]));
    }
    [DatabaseFact]public async Task DatabaseCannotEraseShadowLoss()
    {
        var s=await Store();var study=Study();await s.AppendShadow(study,[Event(study)]);
        await using var c=new NpgsqlConnection(Connection);await c.OpenAsync();
        await using var cmd=new NpgsqlCommand("DELETE FROM research_shadow.events WHERE study_id=$1",c);cmd.Parameters.AddWithValue(study);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
}
