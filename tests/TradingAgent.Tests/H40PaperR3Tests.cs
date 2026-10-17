using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class H40PaperR3Tests
{
    static DateTimeOffset Now=>RiskTests.Now;
    static AccountState Account(){var a=AccountState.Initial("PAPER-H40-R3",100,Now);return a with{Capital=a.Capital! with{Environment="PAPER_TRADING"}};}
    static RiskRequest Request()=>new("F","BUY",12.27m,12.30m,11.59m,1,1,1,1,1,100,1.33m,0,.03228m,.0614m,Now,.03m,
        new("IBKR_PAPER_STOCK_FORWARD","PAPER_TRADING","ODD_LOT",Now,.66m,.67m,true,true,true,true,"LIVE",15),1);
    static RiskEvaluation Eval(RiskRequest? r=null,AccountState? a=null,decimal cash=100,decimal reserved=0,string? parent=null)=>
        H40PaperR3Risk.Evaluate(new(),a??Account(),r??Request(),Now,parent??StockPaperForwardRisk.H40Version,cash,reserved);
    [Fact] public void R3IsThreeDollarsAndOneShare(){var e=Eval();Assert.True(e.Allowed);Assert.Equal(3,e.Budget);Assert.Equal(.03m,e.RiskFraction);Assert.Equal(1,e.Quantity);Assert.Equal(2.14868m,e.EstimatedLoss);}
    [Fact] public void SameOriginalTargetStillFailsEconomicGate()=>Assert.Equal("COST_EXCEEDS_POTENTIAL_PROFIT",Eval(Request() with{Execution=Request().Execution! with{TakeProfit=12.96m}}).Reason);
    [Fact] public void CannotRemoveTargetToMasqueradeAsDiagnostic()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{TakeProfit=null}}).Allowed);
    [Fact] public void ProductiveHalfPercentUntouched()=>Assert.Equal("RISK_EXCEEDS_POLICY",RiskEngine.Evaluate(new(),Account(),Request(),Now).Reason);
    [Fact] public void OriginalTwoPercentScopeCannotAdmitR3()=>Assert.False(H40PaperTrialRisk.Evaluate(new(),Account(),Request(),Now,StockPaperForwardRisk.H40Version,100,0).Allowed);
    [Theory][InlineData(.02)][InlineData(.05)][InlineData(.10)][InlineData(.15)]
    public void NoAutomaticPercentageEscalation(decimal fraction)=>Assert.False(Eval(Request() with{ProposedRisk=fraction}).Allowed);
    [Fact] public void FeesAndGapTogetherMustFitThree()=>Assert.False(Eval(Request() with{AdverseGapPerUnit=2}).Allowed);
    [Fact] public void CapUnverifiedFullMinimaCannotFit()=>Assert.False(Eval(Request() with{CommissionFixedRoundTrip=3.08m,Execution=Request().Execution! with{OpeningCommission=1.54m,ClosingCommission=1.54m}}).Allowed);
    [Fact] public void CostsCannotBeDropped()=>Assert.False(Eval(Request() with{CommissionFixedRoundTrip=0}).Allowed);
    [Fact] public void NoMillionDollarCapital()=>Assert.False(Eval(cash:1000000).Allowed);
    [Fact] public void NoBrokerBuyingPowerSizing()=>Assert.False(Eval(Request() with{AvailableMargin=1000000}).Allowed);
    [Fact] public void FeesInsideHundredDollars()=>Assert.False(Eval(Request() with{Bid=98.99m,Ask=99,Stop=98.99m,Execution=Request().Execution! with{TakeProfit=105}}).Allowed);
    [Theory][InlineData(0)][InlineData(2)][InlineData(.5)]
    public void ExactlyOneWholeShare(decimal q)=>Assert.False(Eval(Request() with{MaximumQuantity=q}).Allowed);
    [Fact] public void FordOnly()=>Assert.False(Eval(Request() with{Instrument="SPY"}).Allowed);
    [Fact] public void LongOnly()=>Assert.False(Eval(Request() with{Side="SELL"}).Allowed);
    [Fact] public void NoLeveragedMargin()=>Assert.False(Eval(Request() with{MarginRate=.5m}).Allowed);
    [Fact] public void LiveCannotUseThisScope()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Environment="LIVE_TRADING"}}).Allowed);
    [Fact] public void UnknownExecutionEvidenceBlocks()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{CostsReliable=false}}).Allowed);
    [Fact] public void DelayedBlocks()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{QuoteStatus="DELAYED"}}).Allowed);
    [Fact] public void StaleBlocks()=>Assert.False(Eval(Request() with{MarketAt=Now.AddMinutes(-1)}).Allowed);
    [Fact] public void UnknownEffectivePermissionBlocks()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{BrokerPermitsEntry=false}}).Allowed);
    [Fact] public void CumulativeBudgetRemainsTwenty()=>Assert.False(Eval(a:Account() with{Capital=Account().Capital! with{CumulativeRealizedLoss=20}}).Allowed);
    [Fact] public void PendingPositionCannotBeIgnored()=>Assert.False(Eval(a:Account() with{ReservationId="pending"}).Allowed);
    [Fact] public void OriginalParentVersionIsRequired()=>Assert.False(Eval(parent:"new-version").Allowed);
    [Fact] public void VariantHasIndependentIdentity(){Assert.NotEqual(StockPaperForwardRisk.H40Version,H40PaperR3Risk.VariantVersion);Assert.Equal(64,H40PaperR3Risk.VariantVersion.Length);}
}
