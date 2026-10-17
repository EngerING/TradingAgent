using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class CapitalTests
{
    // Isolate cumulative controls; production retains its stricter daily/weekly/drawdown limits.
    public static RiskPolicy IsolatedPolicy => new(DailyLimit: .9m, WeeklyLimit: .9m,
        DrawdownLimit: .9m, PreventiveDrawdown: .8m, PreventiveLossStreak: 100, MaxLeverage: 10);

    [Theory][InlineData(100, "NORMAL", 1)][InlineData(95, "REVIEW", 1)]
    [InlineData(90, "REDUCED", .5)][InlineData(85, "RESTRICTED", .25)][InlineData(80, "SUSPENDED", 0)]
    public void ConfigurableProtectionLevels(decimal equity, string level, decimal factor)
    {
        var protection = IsolatedPolicy.Protection(equity);
        Assert.Equal(level, protection.Level); Assert.Equal(factor, protection.RiskFactor);
        var state = RiskTests.Account().Mark(equity, RiskTests.Now, IsolatedPolicy);
        var result = RiskEngine.Evaluate(IsolatedPolicy, state, RiskTests.Request(), RiskTests.Now);
        Assert.Equal(level, result.CapitalLevel);
        if(equity == 80) Assert.Equal("HALT", result.Decision);
        else { Assert.True(result.Allowed); Assert.Equal(equity * .0025m * factor, result.Budget); }
    }

    [Fact] public void FiveWinnersCompoundFromOneAllocationTo150()
    {
        var state = RiskTests.Account(); var first = RiskEngine.Evaluate(IsolatedPolicy, state, RiskTests.Request(), RiskTests.Now);
        for(var i=0; i<5; i++) state = state.Settle(10, .01m, RiskTests.Now, IsolatedPolicy);
        var last = RiskEngine.Evaluate(IsolatedPolicy, state, RiskTests.Request(), RiskTests.Now);
        Assert.Equal(150, state.Equity); Assert.Equal(100, state.Capital!.InitialCapital);
        Assert.Equal(.375m, last.Budget); Assert.True(last.Quantity > first.Quantity);
        Assert.Equal(20, state.Capital.RemainingLoss); Assert.Equal(.05m, state.Capital.TradingCosts);
        Assert.Equal(50, state.Capital.RealizedNetPnl);
    }

    [Fact] public void FiveLossesReducePositionProportionally()
    {
        var state=RiskTests.Account(); decimal previous=decimal.MaxValue;
        for(var i=0; i<5; i++)
        {
            var result=RiskEngine.Evaluate(IsolatedPolicy,state,RiskTests.Request(),RiskTests.Now);
            Assert.True(result.Allowed); Assert.Equal(state.Equity*.0025m,result.Budget);
            Assert.True(result.Quantity <= previous); previous=result.Quantity;
            state=state.Settle(-.25m,.01m,RiskTests.Now,IsolatedPolicy);
        }
        Assert.Equal(98.75m,state.Equity); Assert.Equal(1.25m,state.Capital!.ConsumedLoss);
    }

    [Fact] public void GainsDoNotReplenishCumulativeLossAllowance()
    {
        var state=RiskTests.Account().Settle(50,0,RiskTests.Now,IsolatedPolicy);
        for(var i=0;i<5;i++) state=state.Settle(-4,0,RiskTests.Now,IsolatedPolicy);
        Assert.Equal(130,state.Equity); Assert.Equal(20,state.Capital!.ConsumedLoss);
        Assert.Contains("CUMULATIVE_LOSS_LIMIT",state.Halts);
        Assert.Equal("HALT",RiskEngine.Evaluate(IsolatedPolicy,state,RiskTests.Request(),RiskTests.Now).Decision);
    }

    [Fact] public void FeesCanTurnGrossWinnerIntoBudgetLoss()
    {
        var capital=new VirtualCapital(100).Settle(-3,4);
        Assert.Equal(1,capital.RealizedGrossPnl); Assert.Equal(-3,capital.RealizedNetPnl);
        Assert.Equal(97,capital.Equity); Assert.Equal(3,capital.ConsumedLoss);
        var expenses=capital with {TransferCosts=25}; Assert.Equal(97,expenses.Equity);
        Assert.Equal(-28,expenses.EconomicResult);
    }

    [Fact] public void FloatingLossCostsAndRemainingPositionRiskAreNotDoubleCounted()
    {
        var capital=new VirtualCapital(100).Settle(-5,1).Mark(82,2);
        Assert.Equal(-11,capital.UnrealizedGrossPnl); Assert.Equal(-13,capital.UnrealizedNetPnl);
        Assert.Equal(18,capital.ConsumedLoss); Assert.Equal(2,capital.RemainingLoss);
        var state=RiskTests.Account() with {Capital=capital,Equity=82,PendingOrders=[new(2,10,1)]};
        Assert.Equal("CUMULATIVE_LOSS_RESERVED",RiskEngine.Evaluate(IsolatedPolicy,state,RiskTests.Request(),RiskTests.Now).Reason);
        state=state with {PendingOrders=[],OpenPositions=[new(2,10,1)]};
        Assert.Equal("CUMULATIVE_LOSS_RESERVED",RiskEngine.Evaluate(IsolatedPolicy,state,RiskTests.Request(),RiskTests.Now).Reason);
    }

    [Fact] public void ProjectedEntryCannotExceedRemainingAllowance()
    {
        var state=RiskTests.Account().Mark(80.01m,RiskTests.Now,IsolatedPolicy);
        var result=RiskEngine.Evaluate(IsolatedPolicy,state,RiskTests.Request(),RiskTests.Now);
        Assert.True(result.Allowed); Assert.Equal(.01m,result.Budget);
        Assert.True(state.Capital!.ConsumedLoss+result.EstimatedLoss<=20);
    }

    [Fact] public void OvershootIsRecordedAndDayChangeDoesNotResume()
    {
        var state=RiskTests.Account().Settle(-21,2,RiskTests.Now,IsolatedPolicy);
        state=state.Mark(79,RiskTests.Now.AddDays(1),IsolatedPolicy);
        Assert.Equal(79,state.Equity); Assert.Equal(21,state.Capital!.ConsumedLoss);
        Assert.Contains("CUMULATIVE_LOSS_LIMIT",state.Halts);
    }

    [Fact] public void MissingOrInconsistentAllocationBlocksEntry()
    {
        Assert.Equal("VIRTUAL_CAPITAL_REQUIRED",RiskEngine.Evaluate(IsolatedPolicy,RiskTests.Account() with{Capital=null},RiskTests.Request(),RiskTests.Now).Reason);
        Assert.Equal("VIRTUAL_CAPITAL_MISMATCH",RiskEngine.Evaluate(IsolatedPolicy,RiskTests.Account() with{Equity=1_000_000},RiskTests.Request(),RiskTests.Now).Reason);
        Assert.Throws<ArgumentException>(()=>(IsolatedPolicy with{RestrictEquity=79}).Validate());
    }

    [DatabaseFact] public async Task AllocationLossAndStopSurviveReinitializationAndNewStore()
    {
        var connection=System.Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
        var store=new PostgresStore(connection);await store.Migrate();
        var id="SIM-CAPITAL-"+Guid.NewGuid();var policy=IsolatedPolicy with{Version=id};
        var initial=AccountState.Initial(id,100,RiskTests.Now);await store.Initialize(initial,policy);
        var strategy=new StrategyVersion(id,"Capital fixture",1,"EUR/USD","15","test","stop",.001m,.002m,1000,"simulation","{}");
        await store.Save("strategy_versions",strategy.Hash,id,strategy,RiskTests.Now);
        var cmd=new DecisionCommand(id,id,strategy.Hash,RiskTests.Request(),"London",new(),"{}");
        await store.Evaluate(cmd,policy,RiskTests.Now);
        await store.Settle(id,id,-21,2,"{}",policy,RiskTests.Now.AddSeconds(1));
        await store.EmergencyStop(id,RiskTests.Now.AddSeconds(2));
        var recovered=new PostgresStore(connection);await recovered.Initialize(initial,policy);
        var state=await recovered.State(id);Assert.Equal(79,state.Equity);Assert.Equal(21,state.Capital!.ConsumedLoss);
        Assert.Equal(2,state.Capital.RealizedCosts);Assert.Contains("EMERGENCY_STOP",state.Halts);
        Assert.Contains("CUMULATIVE_LOSS_LIMIT",state.Halts);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>recovered.Initialize(initial,policy with{Version=id+"-new"}));
        await Assert.ThrowsAsync<ArgumentException>(()=>recovered.Initialize(AccountState.Initial(id+"-million",1_000_000,RiskTests.Now),policy));
    }

    [DatabaseFact] public async Task FloatingValuationPreservesReservationAndSettlesWithoutDoubleCounting()
    {
        var connection=System.Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
        var store=new PostgresStore(connection);await store.Migrate();var id="SIM-FLOAT-"+Guid.NewGuid();
        var policy=IsolatedPolicy with{Version=id};await store.Initialize(AccountState.Initial(id,100,RiskTests.Now),policy);
        var strategy=new StrategyVersion(id,"Floating",1,"EUR/USD","15","test","stop",.001m,.002m,1000,"simulation","{}");
        await store.Save("strategy_versions",strategy.Hash,id,strategy,RiskTests.Now);
        await store.Evaluate(new(id,id,strategy.Hash,RiskTests.Request(),"London",new(),"{}"),policy,RiskTests.Now);
        await store.ValuePosition(id,id,id,-20,.2m,1,policy,RiskTests.Now.AddSeconds(1));
        var recovered=new PostgresStore(connection);
        await recovered.ValuePosition(id,id,id,-20,.2m,1,policy,RiskTests.Now.AddSeconds(2));
        var state=await recovered.State(id);Assert.Equal(80,state.Equity);Assert.Equal(id,state.ReservationId);
        Assert.Single(state.OpenPositions);Assert.Equal(1,state.OpenPositions[0].RemainingLoss);
        Assert.Equal(-19.8m,state.Capital!.UnrealizedGrossPnl);Assert.Equal(.2m,state.Capital.OpenCosts);
        Assert.Equal(20,state.Capital.ConsumedLoss);Assert.Contains("CUMULATIVE_LOSS_LIMIT",state.Halts);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>recovered.ValuePosition(id,id,id,-19,.2m,1,policy,RiskTests.Now.AddSeconds(2)));
        await recovered.Settle(id,id,-21,.3m,"{}",policy,RiskTests.Now.AddSeconds(3));
        state=await recovered.State(id);Assert.Equal(79,state.Equity);Assert.Equal(21,state.Capital!.ConsumedLoss);
        Assert.Equal(0,state.Capital.UnrealizedNetPnl);Assert.Equal(.3m,state.Capital.TradingCosts);
        Assert.Null(state.ReservationId);Assert.Contains("CUMULATIVE_LOSS_LIMIT",state.Halts);
    }
}
