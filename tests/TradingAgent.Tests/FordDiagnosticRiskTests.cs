using TradingAgent.Core;
using Xunit;
namespace TradingAgent.Tests;
public class FordDiagnosticRiskTests
{
    static DateTimeOffset Now=>RiskTests.Now;
    static AccountState Account(){var a=AccountState.Initial("PAPER-FORD-EXECUTION-DIAGNOSTIC",100,Now);return a with{Capital=a.Capital! with{Environment="PAPER_TRADING"}};}
    static RiskRequest Request()=>new("F","BUY",12.28m,12.31m,12.15m,1,1,1,1,1,100,1.33m,0,.03229m,.2458m,Now,.03m,
        new(FordDiagnosticRisk.Scope,"PAPER_TRADING","ODD_LOT",Now,.66m,.67m,true,true,true,true,"LIVE"),1);
    static RiskEvaluation Eval(RiskRequest? r=null,AccountState? a=null,string? scope=null,decimal cash=100,decimal reserved=0)=>
        FordDiagnosticRisk.Evaluate(new(),a??Account(),r??Request(),Now,scope??FordDiagnosticRisk.Scope,cash,reserved);
    [Fact] public void IndependentDiagnosticHasThreeDollarBudget(){var e=Eval();Assert.True(e.Allowed);Assert.Equal(3,e.Budget);Assert.Equal(1,e.Quantity);Assert.Null(e.Feasibility!.PotentialGrossProfit);}
    [Fact] public void CannotPretendToBeH40()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Source="IBKR_PAPER_STOCK_FORWARD"}}).Allowed);
    [Fact] public void H40R3CannotReuseDiagnosticRequest()=>Assert.False(H40PaperR3Risk.Evaluate(new(),Account(),Request(),Now,StockPaperForwardRisk.H40Version,100,0).Allowed);
    [Fact] public void OrdinaryRiskStillRejectsThreePercent()=>Assert.Equal("RISK_EXCEEDS_POLICY",RiskEngine.Evaluate(new(),Account(),Request(),Now).Reason);
    [Fact] public void DiagnosticCannotApproveStrategyProfit()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{TakeProfit=15}}).Allowed);
    [Fact] public void FullMinimaExceedThree()=>Assert.False(Eval(Request() with{CommissionFixedRoundTrip=3.08m,Execution=Request().Execution! with{OpeningCommission=1.54m,ClosingCommission=1.54m}}).Allowed);
    [Fact] public void GapInsideBudget()=>Assert.False(Eval(Request() with{AdverseGapPerUnit=2}).Allowed);
    [Theory][InlineData(.005)][InlineData(.02)][InlineData(.05)][InlineData(.10)]
    public void CannotAutomaticallyChangeRisk(decimal r)=>Assert.False(Eval(Request() with{ProposedRisk=r}).Allowed);
    [Theory][InlineData(0)][InlineData(2)][InlineData(.5)]
    public void OneWholeShareOnly(decimal q)=>Assert.False(Eval(Request() with{MaximumQuantity=q}).Allowed);
    [Fact] public void ShortForbidden()=>Assert.False(Eval(Request() with{Side="SELL"}).Allowed);
    [Fact] public void OtherSymbolForbidden()=>Assert.False(Eval(Request() with{Instrument="SPY"}).Allowed);
    [Fact] public void LiveForbidden()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Environment="LIVE_TRADING"}}).Allowed);
    [Fact] public void NoMillionDollarCash()=>Assert.False(Eval(cash:1000000).Allowed);
    [Fact] public void NoBuyingPowerSizing()=>Assert.False(Eval(Request() with{AvailableMargin=1000000}).Allowed);
    [Fact] public void NoLeverage()=>Assert.False(Eval(Request() with{MarginRate=.5m}).Allowed);
    [Fact] public void NoOmittedFee()=>Assert.False(Eval(Request() with{CommissionFixedRoundTrip=0}).Allowed);
    [Fact] public void NoOmittedGap()=>Assert.False(Eval(Request() with{AdverseGapPerUnit=0}).Allowed);
    [Fact] public void NoOmittedSlippage()=>Assert.False(Eval(Request() with{SlippagePerUnit=0}).Allowed);
    [Fact] public void UnknownCostsVeto()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{CostsReliable=false}}).Allowed);
    [Fact] public void UnknownPermissionVeto()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{BrokerPermitsEntry=false}}).Allowed);
    [Fact] public void DelayedVeto()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{QuoteStatus="DELAYED"}}).Allowed);
    [Fact] public void StaleVeto()=>Assert.False(Eval(Request() with{MarketAt=Now.AddMinutes(-1)}).Allowed);
    [Fact] public void ExistingPositionVeto()=>Assert.False(Eval(a:Account() with{ReservationId="owned"}).Allowed);
    [Fact] public void FeesInsideCapital()=>Assert.False(Eval(Request() with{Bid=99,Ask=99.01m,Stop=98.99m}).Allowed);
    [Fact] public void ScopeRequired()=>Assert.False(Eval(scope:"H40_PAPER_EXPERIMENTAL_R3").Allowed);
    [Fact] public void NoGrantFromCalculation()=>Assert.Equal("ALLOW_SIMULATION",Eval().Decision);
}
