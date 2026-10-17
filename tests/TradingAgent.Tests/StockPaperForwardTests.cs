using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;

public class StockPaperForwardTests
{
    static DateTimeOffset Now=>RiskTests.Now;
    static RiskPolicy Policy=>new();
    static AccountState Account()
    {
        var a=AccountState.Initial("PAPER-H40",100,Now);
        return a with {Capital=a.Capital! with {Environment="PAPER_TRADING"}};
    }
    static RiskRequest Request()=>new("F","BUY",10,10.01m,9.99m,1,1,1,1,1,100,.02m,0,0,0,Now,.005m,
        new("test-paper-only","PAPER_TRADING","ODD_LOT",Now,.01m,.01m,true,true,true,true,"LIVE",10.2m));
    static RiskEvaluation Evaluate(RiskRequest? r=null,AccountState? a=null,decimal cash=100,decimal reserved=0,string? version=null)=>
        StockPaperForwardRisk.Evaluate(Policy,a??Account(),r??Request(),Now,version??StockPaperForwardRisk.H40Version,cash,reserved);
    [Fact] public void OrdinaryEngineRemainsMandatory()=>Assert.True(Evaluate().Allowed);
    [Theory][InlineData(.02)][InlineData(.03)][InlineData(.05)][InlineData(.10)][InlineData(.15)]
    public void H40AndResearchProfilesCannotRelaxProductiveCeiling(decimal risk)
    {var r=Evaluate(Request() with {ProposedRisk=risk});Assert.False(r.Allowed);Assert.Equal("RISK_EXCEEDS_POLICY",r.Reason);}
    [Theory][InlineData("SELL","F")][InlineData("BUY","EUR/USD")][InlineData("BUY","SPY")]
    public void ScopeIsLongFordOnly(string side,string instrument)=>Assert.Equal("STOCK_FORWARD_SCOPE_REQUIRED",Evaluate(Request() with {Side=side,Instrument=instrument}).Reason);
    [Fact] public void LiveCapitalDenied()=>Assert.False(Evaluate(a:Account() with {Capital=Account().Capital! with{Environment="SIMULATION"}}).Allowed);
    [Fact] public void VersionIsExact()=>Assert.False(Evaluate(version:"H40").Allowed);
    [Fact] public void NoVirtualMillion()=>Assert.False(Evaluate(cash:1000000).Allowed);
    [Fact] public void FullCashMarginRequired()=>Assert.False(Evaluate(Request() with{MarginRate=.5m}).Allowed);
    [Theory][InlineData(.5,1)][InlineData(1,.5)]
    public void FractionalSizingForbidden(decimal minimum,decimal step)=>Assert.False(Evaluate(Request() with{MinQuantity=minimum,QuantityStep=step}).Allowed);
    [Fact] public void RoundTripFeesReservedAtLimitPrice()=>Assert.Equal("STOCK_FORWARD_ALLOCATION_EXCEEDED",Evaluate(cash:1).Reason);
    [Fact] public void PendingCashConsumesAllocation()=>Assert.False(Evaluate(reserved:100).Allowed);
    [Fact] public void UnknownCostsDeny()=>Assert.False(Evaluate(Request() with{Execution=Request().Execution! with{CostsReliable=false}}).Allowed);
    [Fact] public void StaleQuotesDeny()=>Assert.False(Evaluate(Request() with{MarketAt=Now.AddMinutes(-1)}).Allowed);
    [Fact] public void OnePositionLimitPreserved()=>Assert.False(Evaluate(a:Account() with{OpenPositions=[new(.1m,10,10)]}).Allowed);
    [Fact] public void StopAndCumulativeLossBudgetPreserved()=>Assert.False(Evaluate(a:Account() with{Capital=Account().Capital! with{CumulativeRealizedLoss=20}}).Allowed);
    [Fact] public void InvalidReservationsDeny()=>Assert.False(Evaluate(reserved:-1).Allowed);
}
