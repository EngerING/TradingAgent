using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class ExecutionFeasibilityTests
{
    private static RiskEvaluation Evaluate(RiskRequest request,RiskPolicy? policy=null) =>
        RiskEngine.Evaluate(policy??RiskTests.Policy,RiskTests.Account(),request,RiskTests.Now);

    [Fact] public void ObservedTwoDollarEntryWithoutExitEstimateIsIncomplete()
    {
        var request=RiskTests.Request() with {MinQuantity=100,CommissionFixedRoundTrip=2,
            Execution=RiskTests.Execution with {Source="user-observation-paper-preview",Mode="ODD_LOT",OpeningCommission=2,ClosingCommission=null}};
        var result=Evaluate(request);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",result.Reason);Assert.False(result.Allowed);
        Assert.Equal(ExecutionRejection.IncompleteData,result.Feasibility!.Rejection);
    }

    [Fact] public void TwoDollarEntryExceedsEvenMaximumPreservationRisk()
    {
        var request=RiskTests.Request(.005m) with {CommissionFixedRoundTrip=2,
            Execution=RiskTests.Execution with {OpeningCommission=2,ClosingCommission=0}};
        var result=Evaluate(request);Assert.Equal(.5m,result.Budget);
        Assert.Equal("COST_EXCEEDS_RISK_BUDGET",result.Reason);Assert.Equal(ExecutionRejection.ExcessiveCost,result.Feasibility!.Rejection);
    }

    [Fact] public void TwentyThousandMinimumIsRejectedWithoutIncreasingLeverage()
    {
        var p=RiskTests.Policy;var result=Evaluate(RiskTests.Request() with {MinQuantity=20000,Bid=1.1m,Ask=1.1m,SlippagePerUnit=0},p);
        Assert.Equal("MIN_SIZE_EXCEEDS_BUDGET",result.Reason);
        Assert.Equal(ExecutionRejection.MinimumSize,result.Feasibility!.Rejection);Assert.Equal(10,p.MaxLeverage);
    }

    [Fact] public void LargePaperBalanceCannotProvideMarginToVirtualAccount()
    {
        var request=RiskTests.Request() with {Bid=1,Ask=1.00001m,Stop=.99999m,MinQuantity=101,
            AvailableMargin=1_000_000,MarginRate=1,SlippagePerUnit=0,AdverseGapPerUnit=0};
        var result=Evaluate(request);Assert.Equal("VIRTUAL_MARGIN_INSUFFICIENT",result.Reason);
        Assert.Equal(ExecutionRejection.InsufficientMargin,result.Feasibility!.Rejection);
    }

    [Fact] public void NominalExposureIsIndependentOfStopRisk()
    {
        var request=RiskTests.Request() with {Bid=1,Ask=1.00001m,Stop=.99999m,MinQuantity=101,
            AvailableMargin=1_000_000,MarginRate=.01m,SlippagePerUnit=0,AdverseGapPerUnit=0};
        var result=Evaluate(request,new RiskPolicy());Assert.Equal("VIRTUAL_CAPITAL_INSUFFICIENT",result.Reason);
        Assert.Equal(ExecutionRejection.InsufficientCapital,result.Feasibility!.Rejection);
    }

    [Fact] public void HighSpreadIsAnExcessiveCost()
    {
        var result=Evaluate(RiskTests.Request() with{Bid=1,Ask=1.3m,Stop=.9m});
        Assert.Equal("COST_EXCEEDS_RISK_BUDGET",result.Reason);
    }

    [Theory][InlineData("FROZEN")][InlineData("DELAYED")][InlineData("UNKNOWN")]
    public void FrozenAndUnusableQuotesCannotAdmitEntries(string status)
    {
        var result=Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{QuoteStatus=status}});
        Assert.Equal("MARKET_DATA_UNUSABLE",result.Reason);Assert.False(result.Allowed);
    }

    [Fact] public void MissingEvidenceAndUnreliableMarginOrCostsFailClosed()
    {
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Evaluate(RiskTests.Request() with{Execution=null}).Reason);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{MarginReliable=false}}).Reason);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{CostsReliable=false}}).Reason);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{ContractReliable=false}}).Reason);
        Assert.Equal("MARKET_DATA_UNUSABLE",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{At=RiskTests.Now.AddMinutes(-1)}}).Reason);
    }

    [Fact] public void BrokerRestrictionAndLiveInputsCannotBeBypassed()
    {
        Assert.Equal("BROKER_RESTRICTION",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{BrokerPermitsEntry=false}}).Reason);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{Environment="LIVE_TRADING"}}).Reason);
    }

    [Fact] public void UnknownRealAccountIsExplicitlyUnvalidated()
    {
        var result=Evaluate(RiskTests.Request());Assert.True(result.Allowed);
        Assert.Equal("UNVALIDATED_FOR_PRODUCTION",result.Feasibility!.ProductionValidation);
        var real=new RealAccountConstraints(1,1,.1m,10,true,true,true);
        result=Evaluate(RiskTests.Request() with{Bid=1.1m,Ask=1.1m,SlippagePerUnit=0,Execution=RiskTests.Execution with{EquivalentRealAccount=real}});
        Assert.True(result.Allowed);Assert.Equal("KNOWN_REAL_RESTRICTIONS_CHECKED_LIVE_DISABLED",result.Feasibility!.ProductionValidation);
    }

    [Fact] public void KnownRealRestrictionAppliesEvenWhenOtherRequirementsAreMissing()
    {
        var real=new RealAccountConstraints(InstrumentPermitted:false);
        var result=Evaluate(RiskTests.Request() with{Execution=RiskTests.Execution with{EquivalentRealAccount=real}});
        Assert.Equal("REAL_ACCOUNT_RESTRICTION",result.Reason);
        real=new(MinimumQuantity:20000);
        result=Evaluate(RiskTests.Request() with{Bid=1.1m,Ask=1.1m,SlippagePerUnit=0,Execution=RiskTests.Execution with{EquivalentRealAccount=real}});
        Assert.Equal("MIN_SIZE_EXCEEDS_BUDGET",result.Reason);
    }

    [Fact] public void KnownRealMarginIsAppliedToTheVirtualFunds()
    {
        var request=RiskTests.Request() with{Bid=1,Ask=1.00001m,Stop=.99999m,MinQuantity=101,AvailableMargin=1_000_000,
            SlippagePerUnit=0,AdverseGapPerUnit=0,Execution=RiskTests.Execution with{EquivalentRealAccount=new(MarginRate:1)}};
        Assert.Equal("VIRTUAL_MARGIN_INSUFFICIENT",Evaluate(request).Reason);
    }

    [Fact] public void GrossProfitBelowCostsIsRejected()
    {
        var result=Evaluate(RiskTests.Request() with {Execution=RiskTests.Execution with{TakeProfit=1.10011m}});
        Assert.Equal("COST_EXCEEDS_POTENTIAL_PROFIT",result.Reason);
    }

    [Fact] public void FeesSpreadAndSlippageAreChargedExactlyOnceAndSizeRoundsDown()
    {
        var request=RiskTests.Request() with{CommissionFixedRoundTrip=.02m,CommissionPerUnitRoundTrip=.0001m,
            QuantityStep=3,Execution=RiskTests.Execution with{OpeningCommission=.01m,ClosingCommission=.01m,TakeProfit=1.103m}};
        var result=Evaluate(request);Assert.True(result.Allowed);
        var f=result.Feasibility!;Assert.Equal(0,(f.Quantity-1)%3);
        Assert.Equal(.02m+f.Quantity*.0001m,f.Commissions);
        Assert.Equal(f.StopLoss+f.Commissions+f.SpreadCost+f.SlippageCost+f.AdverseLoss,f.EstimatedLoss);
        Assert.True(f.EstimatedLoss<=result.Budget);
        Assert.Equal(f.PotentialGrossProfit-f.Commissions-f.SpreadCost-f.SlippageCost,f.PotentialNetProfit);
    }

    [Fact] public void AnalyzerRejectsAnInjectedRiskBudget()
    {
        var result=ExecutionFeasibilityAnalyzer.Analyze(RiskTests.Policy,RiskTests.Account(),RiskTests.Request(),10,RiskTests.Now);
        Assert.False(result.Allowed);Assert.Equal(ExecutionRejection.ExcessiveRisk,result.Rejection);
    }

    [DatabaseFact] public async Task CostOverrunPersistsNetLossAndHaltsWithoutDoubleCharging()
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;var store=new PostgresStore(conn);await store.Migrate();
        var id="SIM-COST-"+Guid.NewGuid();var p=new RiskPolicy(Version:id,MaxLeverage:10);
        await store.Initialize(AccountState.Initial(id,100,RiskTests.Now),p);
        var strategy=new StrategyVersion(id,"Costs",1,"EUR/USD","15","test","stop",.001m,.002m,1000,"synthetic","{}");
        await store.Save("strategy_versions",strategy.Hash,id,strategy,RiskTests.Now);
        var command=new DecisionCommand(id,id,strategy.Hash,RiskTests.Request(),"London",new(),"{}");
        Assert.True((await store.Evaluate(command,p,RiskTests.Now)).Evaluation.Allowed);
        await store.Settle(id,id,-.3m,.4m,"{}",p,RiskTests.Now.AddSeconds(1));
        var recovered=new PostgresStore(conn);await recovered.Settle(id,id,-.3m,.4m,"{}",p,RiskTests.Now.AddSeconds(2));
        var state=await recovered.State(id);Assert.Equal(99.7m,state.Equity);Assert.Equal(.4m,state.Capital!.RealizedCosts);
        Assert.Equal(.1m,state.Capital.RealizedGrossPnl);Assert.Equal(.3m,state.Capital.ConsumedLoss);
        Assert.Contains("EXECUTION_COST_OVERRUN",state.Halts);
        Assert.NotNull(await recovered.Get<object>("system_events","cost-overrun:"+id));
        var denied=await recovered.Evaluate(command with{Id=id+"-next"},p,RiskTests.Now.AddSeconds(2));
        Assert.False(denied.Evaluation.Allowed);
    }
}
