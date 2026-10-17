using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class H40PaperTrialTests
{
    static DateTimeOffset Now=>RiskTests.Now;
    static AccountState Account(){var a=AccountState.Initial("PAPER-H40-TRIAL",100,Now);return a with{Capital=a.Capital! with{Environment="PAPER_TRADING"}};}
    static RiskRequest Request()=>new("F","BUY",10,10.01m,9.8m,1,1,1,1,1,100,.2m,0,.02m,.05m,Now,.02m,
        new("IBKR_PAPER_SUPERVISED","PAPER_TRADING","ODD_LOT",Now,.1m,.1m,true,true,true,true,"LIVE",12),1);
    static RiskEvaluation Eval(RiskRequest? r=null,AccountState? a=null,string? version=null,decimal cash=100,decimal reserve=0)=>
        H40PaperTrialRisk.Evaluate(new(),a??Account(),r??Request(),Now,version??StockPaperForwardRisk.H40Version,cash,reserve);
    [Fact] public void ExperimentalCalculationDoesNotAlterProductivePolicy()
    {var p=new RiskPolicy();Assert.True(Eval().Allowed);Assert.Equal(.005m,p.MaximumRisk);Assert.Equal("RISK_EXCEEDS_POLICY",RiskEngine.Evaluate(p,Account(),Request(),Now).Reason);p.Validate();}
    [Fact] public void OriginalTwoPercentRemainsAndTenIsOnlyOuterCeiling(){Assert.Equal(2,Eval().Budget);Assert.Equal(.02m,Eval().RiskFraction);}
    [Fact] public void OneWholeShareWithCashOnly(){var v=Eval();Assert.Equal(1,v.Quantity);Assert.Equal(v.NominalExposure,v.RequiredMargin);}
    [Theory][InlineData(.005)][InlineData(.03)][InlineData(.10)][InlineData(.15)]
    public void CannotTurnCeilingIntoRiskIncrease(decimal r)=>Assert.False(Eval(Request() with{ProposedRisk=r}).Allowed);
    [Theory][InlineData("SELL","F")][InlineData("BUY","SPY")][InlineData("BUY","EUR/USD")]
    public void PaperFordLongOnly(string side,string symbol)=>Assert.False(Eval(Request() with{Side=side,Instrument=symbol}).Allowed);
    [Fact] public void UnknownModelVersionDenied()=>Assert.False(Eval(version:"H40").Allowed);
    [Fact] public void LiveDenied()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Environment="LIVE_TRADING"}}).Allowed);
    [Fact] public void BrokerMillionDenied()=>Assert.False(Eval(cash:1000000).Allowed);
    [Fact] public void BrokerMarginNotUsedAsCapital()=>Assert.False(Eval(Request() with{AvailableMargin=1000000}).Allowed);
    [Fact] public void FractionalSharesDenied()=>Assert.False(Eval(Request() with{MinQuantity=.01m}).Allowed);
    [Fact] public void LeveragedMarginDenied()=>Assert.False(Eval(Request() with{MarginRate=.5m}).Allowed);
    [Fact] public void LargerTrialDenied()=>Assert.False(Eval(Request() with{MaximumQuantity=2}).Allowed);
    [Fact] public void PendingAllocationRespected()=>Assert.False(Eval(reserve:100).Allowed);
    [Fact] public void UncertainCostDenied()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{CostsReliable=false}}).Allowed);
    [Fact] public void NoEffectivePermissionDenied()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{BrokerPermitsEntry=false}}).Allowed);
    [Fact] public void DelayedDenied()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{QuoteStatus="DELAYED"}}).Allowed);
    [Fact] public void StaleDenied()=>Assert.False(Eval(Request() with{MarketAt=Now.AddMinutes(-1)}).Allowed);
    [Fact] public void PendingResultDenied()=>Assert.False(Eval(a:Account() with{ReservationId="pending"}).Allowed);
    [Fact] public void CumulativeBudgetCannotBeReset()=>Assert.False(Eval(a:Account() with{Capital=Account().Capital! with{CumulativeRealizedLoss=20}}).Allowed);
    [Fact] public void FeesCannotBeOmitted()=>Assert.False(Eval(Request() with{CommissionFixedRoundTrip=0}).Allowed);
    [Fact] public void UnprofitableTargetStillDenied()=>Assert.Equal("COST_EXCEEDS_POTENTIAL_PROFIT",Eval(Request() with{Execution=Request().Execution! with{TakeProfit=10.02m}}).Reason);
    [Fact] public void PaperPortfolioOnly()=>Assert.False(Eval(a:Account() with{Capital=Account().Capital! with{Environment="SIMULATION"}}).Allowed);
}
