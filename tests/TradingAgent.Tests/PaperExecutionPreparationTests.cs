using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class PaperExecutionPreparationTests
{
    private static readonly DateTimeOffset Now=new(2026,10,4,12,0,0,TimeSpan.Zero);
    private static PaperPreparationChecks Checks=>new("PAPER_TRADING",false,true,true,Now,Now.AddHours(24),true,true,false,true,true,true,true);
    [Fact] public void AllReadinessFlagsStillCannotEnableTransmissionOrLive()
    {
        var r=PaperExecutionPreparation.Check("DUR12343784",["DUR12343784"],Checks,Now);
        Assert.True(r.IdentityMatches);Assert.Equal(new[]{"E0_EXECUTION_DISABLED"},r.Blockers);
        Assert.False(r.TransmissionEnabled);Assert.False(r.LiveEnabled);
        var live=PaperExecutionPreparation.Check("DUR12343784",["DUR12343784"],Checks with {Environment="LIVE",LiveEnabled=true},Now);
        Assert.Contains("LIVE_DISABLED",live.Blockers);Assert.False(live.TransmissionEnabled);
    }
    [Fact] public void SameSuffixAndMultipleAccountsNeverSatisfyExactIdentity()
    {
        Assert.False(PaperExecutionPreparation.Check("DUR12343784",["DUR99993784"],Checks,Now).IdentityMatches);
        Assert.False(PaperExecutionPreparation.Check("DUR12343784",["DUR12343784","DU23456789"],Checks,Now).IdentityMatches);
        var r=PaperExecutionPreparation.Check("DUR12343784",["DUR99993784"],Checks,Now);
        Assert.DoesNotContain("DUR",System.Text.Json.JsonSerializer.Serialize(r));
    }
    [Fact] public void ReadOnlyAttestationIsNotExecutionApprovalAndRestartRequiresReconciliation()
    {
        var c=Checks with {IndependentExecutionAuthorization=false,Reconciled=false,EmergencyStopped=true,ProtectiveOrdersVerified=false};
        var r=PaperExecutionPreparation.Check("DU12345678",["DU12345678"],c,Now);
        Assert.Contains("SEPARATE_MANUAL_EXECUTION_AUTHORIZATION_REQUIRED",r.Blockers);
        Assert.Contains("RECONCILIATION_REQUIRED",r.Blockers);Assert.Contains("EMERGENCY_STOP",r.Blockers);
        Assert.Contains("POSITION_PROTECTION_REQUIRED",r.Blockers);
        Assert.Contains("READ_ONLY_PAPER_ATTESTATION_INVALID",PaperExecutionPreparation.Check("DU12345678",["DU12345678"],Checks,Now.AddHours(24)).Blockers);
    }
    [Fact] public void IntentKeysAreStableUnambiguousAndSeparateSidesVersionsAccounts()
    {
        var i=new PaperIntentReference("PAPER-0123456789abcdef","v1","signal:1",12087792,"BUY");
        Assert.Equal(i.IdempotencyKey,(i with {}).IdempotencyKey);
        Assert.NotEqual(i.IdempotencyKey,(i with {Side="SELL"}).IdempotencyKey);
        Assert.NotEqual(i.IdempotencyKey,(i with {StrategyVersion="v2"}).IdempotencyKey);
        Assert.NotEqual(i.IdempotencyKey,(i with {InternalAccountKey="PAPER-fedcba9876543210"}).IdempotencyKey);
        Assert.NotEqual((i with {StrategyVersion="a:b",SignalKey="c"}).IdempotencyKey,(i with {StrategyVersion="a",SignalKey="b:c"}).IdempotencyKey);
        Assert.Throws<ArgumentException>(()=>(i with {InternalAccountKey="DU12345678"}).IdempotencyKey);
    }
}
