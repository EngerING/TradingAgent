using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class R20V1RetirementTests
{
    [Fact] public void OperationalNewCohortIsDenied()
        => Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.EnforceRetirement(55433,0,true));
    [Theory][InlineData(0,false)][InlineData(3858,false)][InlineData(3858,true)]
    public void HistoricalReadsAndExistingRecoveryRemainAvailable(long revision,bool append)
        => AggressiveGrowthStore.EnforceRetirement(55433,revision,append);
    [Fact] public void SyntheticTestPreregistrationRemainsIsolated()
        => AggressiveGrowthStore.EnforceRetirement(55432,0,true);
}
