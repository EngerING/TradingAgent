using System.Text.Json;
using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;

public class PaperRiskProfileTests
{
    private static readonly DateTimeOffset Now = RiskTests.Now;
    private static AccountState Account() => AccountState.Initial("PAPER-TEST",100,Now) with {
        Capital = new VirtualCapital(100,Environment:"PAPER_TRADING") };
    private static RiskRequest Request() => RiskTests.Request() with {
        ProposedRisk=null, CommissionFixedRoundTrip=.10m,
        Execution=RiskTests.Execution with {Environment="PAPER_TRADING", Mode="ODD_LOT", QuoteStatus="LIVE",
            OpeningCommission=.05m, ClosingCommission=.05m,
            EquivalentRealAccount=new(1,1,.1m,1,true,true,true)} };
    private static PaperRiskProfileStudy Study(AccountState? account=null, RiskRequest? request=null,
        RiskPolicy? policy=null) => PaperRiskProfile.Study(PaperRiskProfile.Experimental,policy??new(),
            account??Account(),request??Request(),Now,"IBKR","StrategyPaper",false);

    [Fact] public void SeparateInactiveProfileUsesNewDailyPolicyWithoutChangingConservative()
    {
        var conservative=new RiskPolicy(); var candidate=PaperRiskProfile.Candidate(conservative);
        Assert.Equal(conservative,candidate with {Version=conservative.Version,
            OrdinaryRisk=conservative.OrdinaryRisk,MaximumRisk=conservative.MaximumRisk});
        var result=Study(); Assert.Equal(10,result.OperationCeiling);
        Assert.Equal(10,result.Evaluation.Budget);
        Assert.False(result.Active); Assert.False(result.ExecutionAuthorized); Assert.False(result.LiveEnabled);
        Assert.Equal(.0025m,conservative.OrdinaryRisk); Assert.Equal(.005m,conservative.MaximumRisk);
    }
    [Fact] public void TenDollarTotalIncludesEveryCostAndStopOnce()
    {
        var result=Study().Evaluation;
        Assert.True(result.Allowed); Assert.Equal(10,result.Budget);
        Assert.True(result.EstimatedLoss<=10);
        Assert.Equal(result.EstimatedLoss,result.Feasibility!.StopLoss+result.Commissions+
            result.SpreadCost+result.SlippageCost+result.AdverseLoss);
        Assert.True(result.Commissions>0 && result.SpreadCost>0 && result.SlippageCost>0 && result.AdverseLoss>0);
        Assert.True(result.NominalExposure<=100); Assert.True(result.RequiredMargin<=100);
    }
    [Fact] public void CostAboveTenCannotBeAdmitted()
    {
        var r=Request(); r=r with {CommissionFixedRoundTrip=11,
            Execution=r.Execution! with {OpeningCommission=6,ClosingCommission=5}};
        Assert.Equal("COST_EXCEEDS_RISK_BUDGET",Study(request:r).Evaluation.Reason);
    }
    [Theory][InlineData("costs")][InlineData("closing")][InlineData("margin")][InlineData("contract")]
    public void EssentialUnknownDataBlocks(string field)
    {
        var r=Request(); var f=r.Execution!;
        f=field switch {"costs"=>f with{CostsReliable=false},"closing"=>f with{ClosingCommission=null},
            "margin"=>f with{MarginReliable=false},_=>f with{ContractReliable=false}};
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Study(request:r with{Execution=f}).Evaluation.Reason);
    }
    [Theory][InlineData("LIVE_TRADING","StrategyPaper","IBKR",false)]
    [InlineData("PAPER_TRADING","ExecutionDiagnostics","IBKR",false)]
    [InlineData("PAPER_TRADING","StrategyPaper","OTHER",false)]
    [InlineData("PAPER_TRADING","StrategyPaper","IBKR",true)]
    public void NeverCrossesBrokerModeOrLiveBoundary(string environment,string mode,string broker,bool live)
    {
        var a=Account() with{Capital=Account().Capital! with{Environment=environment}};
        Assert.Throws<ArgumentException>(()=>PaperRiskProfile.Study(PaperRiskProfile.Experimental,new(),a,
            Request(),Now,broker,mode,live));
    }
    [Fact] public void OrdinaryServicesCannotLoadExperimentalPolicyEvenFromJson()
    {
        var p=PaperRiskProfile.Candidate(new());
        var copy=JsonSerializer.Deserialize<RiskPolicy>(JsonSerializer.Serialize(p))!;
        Assert.Throws<ArgumentException>(()=>copy.Validate());
        Assert.Throws<ArgumentException>(()=>RiskEngine.Evaluate(copy,Account(),Request(),Now));
        Assert.Throws<ArgumentException>(()=>ExecutionFeasibilityAnalyzer.Analyze(copy,Account(),Request(),10,Now));
    }
    [Fact] public void LossOfTenConsumesBudgetAndTwoRealizedLossesExhaustItAfterRestart()
    {
        var a=PaperRiskProfile.Reserve(Account(),Request(),"first",Now,new());
        a=PaperRiskProfile.Settle(a,"first",-10,4,true,Now,new());
        Assert.Equal(90,a.Equity); Assert.Equal(10,a.Capital!.ConsumedLoss); Assert.Equal(10,a.Capital.RemainingLoss);
        Assert.Equal(9,Study(a).OperationCeiling);
        Assert.Equal("DAILY_FIRST_LOSS_STOP",Study(a).Evaluation.Reason);
        a=JsonSerializer.Deserialize<AccountState>(JsonSerializer.Serialize(a))!;
        // Observed second loss, not authorization to enter another $10 trade at equity $90.
        var tomorrow=Now.AddDays(1);
        a=PaperRiskProfile.Mark(a,tomorrow,new());
        var request=Request() with {MarketAt=tomorrow,Execution=Request().Execution! with {At=tomorrow}};
        a=PaperRiskProfile.Reserve(a,request,"second",tomorrow,new());
        // Adverse observed result may exceed the $9 reservation; settlement still accounts for it.
        a=PaperRiskProfile.Settle(a,"second",-10,4,true,tomorrow,new());
        Assert.Equal(80,a.Equity); Assert.Equal(20,a.Capital!.ConsumedLoss); Assert.Equal(0,a.Capital.RemainingLoss);
        Assert.Contains("CUMULATIVE_LOSS_LIMIT",a.Halts);
        Assert.Equal("CUMULATIVE_LOSS_LIMIT",Study(a).Evaluation.Reason);
        Assert.Equal(0,a.Capital!.RemainingLoss); Assert.Equal("HALT",Study(a).Evaluation.Decision);
    }
    [Fact] public void PendingOrdersRemainIntactAndPreventEntries()
    {
        var a=Account() with{ReservationId="existing",PendingOrders=[new(.5m,50,5)]};
        var before=JsonSerializer.Serialize(a);
        Assert.Equal("POSITION_LIMIT",Study(a).Evaluation.Reason);
        Assert.Equal(before,JsonSerializer.Serialize(a));
    }
    [Fact] public void InsufficientRemainingBudgetRejectsMinimumAndDoesNotInventFunds()
    {
        var a=Account(); var c=a.Capital! with{CumulativeRealizedLoss=19.95m,RealizedGrossPnl=-19.95m};
        a=a with{Capital=c,Equity=c.Equity,PaperContinuation=new(DateOnly.FromDateTime(Now.UtcDateTime),
            Results:[new("old",-19.95m,0,DateOnly.FromDateTime(Now.AddDays(-1).UtcDateTime))])};
        Assert.Equal(.05m,Study(a).Evaluation.Budget);
        Assert.False(Study(a).Evaluation.Allowed);
    }
    [Fact] public void ExcessRiskStaleQuoteAndBrokerMinimumStillBlock()
    {
        Assert.Equal("RISK_EXCEEDS_POLICY",Study(request:Request() with{ProposedRisk=.1001m}).Evaluation.Reason);
        Assert.Equal("DATA_STALE",Study(request:Request() with{MarketAt=Now.AddMinutes(-1)}).Evaluation.Reason);
        Assert.False(Study(request:Request() with{MinQuantity=20000}).Evaluation.Allowed);
    }
    [Fact] public void LargerLeverageOrAllocationCannotCreateCandidate()
    {
        Assert.Throws<ArgumentException>(()=>PaperRiskProfile.Candidate(new(MaxLeverage:2)));
        Assert.Throws<ArgumentException>(()=>PaperRiskProfile.Candidate(new(AllocatedCapital:200)));
    }
}
