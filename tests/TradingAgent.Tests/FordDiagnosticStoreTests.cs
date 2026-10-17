using System.Text.Json;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;
namespace TradingAgent.Tests;
public class FordDiagnosticStoreTests
{
    static string Connection=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
    static string Trial()=>"ford-diag-"+Guid.NewGuid().ToString("N");
    static FordDiagnosticEvent Event(string trial,long revision=1,string previous="",string scope=FordDiagnosticRisk.R10Scope)
    {
        var payload=JsonSerializer.Serialize(new{state=new{trial_id=trial,binding_id="test-binding",scope,
            environment="PAPER_TRADING",classification="EXECUTION_DIAGNOSTICS",strategy_version=(string?)null,
            intent=(string?)null,reservation="0"},details=new{}});
        var at=RiskTests.Now.ToString("O");var material=$"[{revision},{JsonSerializer.Serialize(at)},\"TEST\",{payload},{JsonSerializer.Serialize(previous)}]";
        return new(revision,at,"TEST",payload,previous,Evidence.Hash(material),material);
    }
    static async Task<PostgresStore> Store(){var s=new PostgresStore(Connection);await s.Migrate();return s;}
    [DatabaseFact]public async Task ReplayAndRestartPersistExactChain()
    {
        var s=await Store();var trial=Trial();var a=Event(trial);var b=Event(trial,2,a.Hash);
        var h=await s.AppendFordDiagnostic(trial,"test-binding",FordDiagnosticRisk.R10Scope,[a,b]);
        Assert.Equal(2,h.Revision);Assert.Equal(h,await new PostgresStore(Connection).AppendFordDiagnostic(trial,"test-binding",FordDiagnosticRisk.R10Scope,[a,b]));
        Assert.Equal(h,await s.AppendFordDiagnostic(trial,"test-binding",FordDiagnosticRisk.R10Scope,[]));
    }
    [DatabaseFact]public async Task GapRollsBackWholeBatch()
    {
        var s=await Store();var trial=Trial();var a=Event(trial);
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendFordDiagnostic(trial,"test-binding",FordDiagnosticRisk.R10Scope,[a,Event(trial,3,a.Hash)]));
        Assert.Equal(0,(await s.AppendFordDiagnostic(trial,"test-binding",FordDiagnosticRisk.R10Scope,[])).Revision);
    }
    [DatabaseFact]public async Task HashTamperRejected()
    {
        var s=await Store();var t=Trial();await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendFordDiagnostic(t,"test-binding",FordDiagnosticRisk.R10Scope,[Event(t) with{Hash=new string('a',64)}]));
    }
    [DatabaseFact]public async Task CrossProfileRejected()
    {
        var s=await Store();var t=Trial();await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendFordDiagnostic(t,"test-binding",FordDiagnosticRisk.Scope,[Event(t)]));
    }
    [DatabaseFact]public async Task DatabaseCannotEraseLossEvidence()
    {
        var s=await Store();var t=Trial();await s.AppendFordDiagnostic(t,"test-binding",FordDiagnosticRisk.R10Scope,[Event(t)]);
        await using var c=new NpgsqlConnection(Connection);await c.OpenAsync();
        await using var cmd=new NpgsqlCommand("DELETE FROM paper_lab.ford_diagnostic_events WHERE trial_id=$1",c);cmd.Parameters.AddWithValue(t);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [DatabaseFact]public async Task ChangingReplayRejected()
    {
        var s=await Store();var t=Trial();await s.AppendFordDiagnostic(t,"test-binding",FordDiagnosticRisk.R10Scope,[Event(t)]);
        var changed=Event(t) with{At=RiskTests.Now.AddDays(1).ToString("O")};
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.AppendFordDiagnostic(t,"test-binding",FordDiagnosticRisk.R10Scope,[changed]));
    }
}
