using TradingAgent.Core;
using Xunit;
namespace TradingAgent.Tests;
public class FordDiagnosticR10Tests
{
    static DateTimeOffset Now=>RiskTests.Now;
    static AccountState Account(){var a=AccountState.Initial("PAPER-FORD-EXECUTION-DIAGNOSTIC",100,Now);return a with{Capital=a.Capital! with{Environment="PAPER_TRADING"}};}
    static RiskRequest Request()=>new("F","BUY",12.28m,12.31m,12.15m,1,1,1,1,1,100,3.08m,0,.03229m,.2458m,Now,.10m,
        new(FordDiagnosticRisk.R10Scope,"PAPER_TRADING","ODD_LOT",Now,1.54m,1.54m,true,true,true,true,"LIVE"),1);
    static RiskEvaluation Eval(RiskRequest? r=null,AccountState? a=null,string? scope=null,decimal cash=100,decimal reserved=0)=>
        FordDiagnosticRisk.Evaluate(new(),a??Account(),r??Request(),Now,scope??FordDiagnosticRisk.R10Scope,cash,reserved);
    [Fact]public void FullMinimaAllowedWithinTenOnlyOneShare(){var e=Eval();Assert.True(e.Allowed);Assert.Equal(10,e.Budget);Assert.Equal(1,e.Quantity);Assert.Equal(3.53309m,e.EstimatedLoss);Assert.Equal("ALLOW_SIMULATION",e.Decision);}
    [Fact]public void LegacyScopeCannotSpendTen()=>Assert.False(Eval(scope:FordDiagnosticRisk.Scope).Allowed);
    [Fact]public void LegacySourceCannotSpendTen()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Source=FordDiagnosticRisk.Scope}}).Allowed);
    [Fact]public void ProductiveStillRejectsTen()=>Assert.Equal("RISK_EXCEEDS_POLICY",RiskEngine.Evaluate(new(),Account(),Request(),Now).Reason);
    [Fact]public void H40R3StillCannotUseDiagnostic()=>Assert.False(H40PaperR3Risk.Evaluate(new(),Account(),Request(),Now,StockPaperForwardRisk.H40Version,100,0).Allowed);
    [Theory][InlineData(.03)][InlineData(.15)][InlineData(.20)]public void NoAutomaticBudgetChange(decimal rate)=>Assert.False(Eval(Request() with{ProposedRisk=rate}).Allowed);
    [Fact]public void NoMoreThanOneShare()=>Assert.False(Eval(Request() with{MaximumQuantity=2}).Allowed);
    [Fact]public void NoShort()=>Assert.False(Eval(Request() with{Side="SELL"}).Allowed);
    [Fact]public void NoLeverage()=>Assert.False(Eval(Request() with{MarginRate=.5m}).Allowed);
    [Fact]public void NoMillionDollarSizing()=>Assert.False(Eval(cash:1000000).Allowed);
    [Fact]public void CashIncludesFees()=>Assert.False(Eval(Request() with{Bid=98,Ask=99,Stop=97}).Allowed);
    [Fact]public void GapCanExceedTen()=>Assert.False(Eval(Request() with{AdverseGapPerUnit=8}).Allowed);
    [Fact]public void CostsCannotBeUnknown()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{CostsReliable=false}}).Allowed);
    [Fact]public void CannotApproveStrategyProfit()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{TakeProfit=15}}).Allowed);
    [Fact]public void LiveNeverAllowed()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{Environment="LIVE_TRADING"}}).Allowed);
    [Fact]public void DelayedNeverAllowed()=>Assert.False(Eval(Request() with{Execution=Request().Execution! with{QuoteStatus="DELAYED"}}).Allowed);
    [Fact]public void ExactAccountRequired()=>Assert.False(Eval(a:Account() with{AccountId="PAPER-H40"}).Allowed);
}
