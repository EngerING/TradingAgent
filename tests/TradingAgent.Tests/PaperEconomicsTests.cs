using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class PaperEconomicsTests
{
    static AccountState Account()=>AccountState.Initial("PAPER-TEST",100,RiskTests.Now) with {Capital=new(100,Environment:"PAPER_TRADING")};
    static RiskRequest Request()=>RiskTests.Request() with {Instrument="EUR/USD",Side="BUY",Bid=1.12m,Ask=1.12005m,
        Stop=1.118m,MinQuantity=.01m,QuantityStep=.01m,Multiplier=1,QuoteToAccountFx=1,
        CommissionFixedRoundTrip=4,CommissionPerUnitRoundTrip=0,SlippagePerUnit=.00045m,AdverseGapPerUnit=.00005m,
        Execution=RiskTests.Execution with {Environment="PAPER_TRADING",OpeningCommission=2,ClosingCommission=2,TakeProfit=1.12305m}};
    [Fact] public void HypotheticalSizesDoNotRelaxOneTimesOperationalRecommendation()
    {
        var result=RiskEngine.StudyPaperEconomics(Account(),Request());
        Assert.Equal(10,result.Budget);Assert.Equal(0,result.RecommendedQuantity);
        Assert.False(result.ExecutionAuthorized);Assert.False(result.LiveEnabled);
        var first=result.Sizes.Single(s=>s.Scenario=="FIRST_STRICTLY_POSITIVE_TARGET");
        Assert.True(first.NetAtTargetUsd>0);Assert.True(first.ExposureMultiple>1);Assert.True(first.OddLot);
        Assert.False(first.WithinOneTimesExposure);
    }
    [Fact] public void FeesSpreadSlippageAndGapAreIncludedAndRiskQuantityFloors()
    {
        var r=Request();var result=RiskEngine.StudyPaperEconomics(Account(),r);
        var maximum=result.Sizes.Single(s=>s.Scenario=="MAXIMUM_RISK_QUANTITY");
        Assert.True(maximum.TotalLossAtStopUsd<=10);
        Assert.True(maximum.TotalLossAtStopUsd+.01m*result.UnitRisk>10);
        Assert.Equal(4+maximum.Quantity*(.00005m+.00045m),maximum.CostsUsd);
        Assert.Equal(maximum.StopLossUsd+maximum.CostsUsd+maximum.Quantity*.00005m,maximum.TotalLossAtStopUsd);
        Assert.Equal(maximum.NotionalUsd/100,maximum.ExposureMultiple);
    }
    [Fact] public void ConsumedLossRemainsAnIndependentBudgetEvenWithProfits()
    {
        var a=Account();a=a with {Equity=107,Capital=a.Capital! with {RealizedGrossPnl=7,CumulativeRealizedLoss=19}};
        var result=RiskEngine.StudyPaperEconomics(a,Request());Assert.Equal(1,result.Budget);Assert.Equal(0,result.RecommendedQuantity);
        Assert.DoesNotContain(result.Sizes,s=>s.Scenario=="MAXIMUM_RISK_QUANTITY");
    }
    [Fact] public void LiveAndMillionDollarAccountCannotEnterPaperStudy()
    {
        var a=Account();Assert.Throws<ArgumentException>(()=>RiskEngine.StudyPaperEconomics(a with {Equity=1000000},Request()));
        Assert.Throws<ArgumentException>(()=>RiskEngine.StudyPaperEconomics(a with {Capital=a.Capital! with {Environment="LIVE_TRADING"}},Request()));
    }
    [Fact] public void NoPositiveUnitProfitCannotInventBreakevenQuantity()
    {
        var r=Request();r=r with {Execution=r.Execution! with {TakeProfit=1.12010m}};
        var result=RiskEngine.StudyPaperEconomics(Account(),r);
        Assert.DoesNotContain(result.Sizes,s=>s.Scenario=="FIRST_STRICTLY_POSITIVE_TARGET");Assert.Equal(0,result.RecommendedQuantity);
    }
}
