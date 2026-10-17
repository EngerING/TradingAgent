using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.ResearchLab;
using Xunit;

namespace TradingAgent.Tests;

public class ExposureStudyTests
{
    private static readonly DateTimeOffset At=new(2026,8,4,12,0,0,TimeSpan.Zero);
    private static ResearchSignal Signal(decimal stop=.002m,decimal target=.005m)=>
        new("pullback","BUY",At,At,1.12m,stop,target,[],JsonSerializer.SerializeToElement(new{}));
    private static ResearchCosts Costs(decimal spread=.00005m)=>new(spread,2,2,0,.00045m,.00005m,.01m,.01m,1,"SIMULATION_ONLY");
    private static ExposureAssumptions Assumptions(decimal exposure=20,decimal margin=.05m,decimal annual=.1m,decimal days=1)
        =>new(exposure,margin,margin,annual,days);
    private static PaperCandle Bar(DateTimeOffset at,decimal low=1.12m,decimal high=1.12m,decimal open=1.12m)
        =>new(at,15,open,high,low,open,null,null);

    [Theory][InlineData(1)][InlineData(2)][InlineData(5)][InlineData(10)][InlineData(15)][InlineData(20)]
    public void EveryExposureFundsMarginAndEntireLossWithOnlyVirtualEquity(int exposure)
    {
        var x=SimulationSizer.Size(new(),Signal(),Costs(),.15m,Assumptions(exposure));
        Assert.True(x.Quantity>0);Assert.True(x.Notional<=100*exposure);
        Assert.True(x.TotalRisk<=15);
        Assert.True(Math.Max(x.InitialMarginRequired,x.MaintenanceMarginAtStop)+x.TotalRisk<=100);
        Assert.Equal(x.StopLoss+x.Commission+x.Spread+x.Slippage+x.GapReserve+x.FinancingReserve,x.TotalRisk);
        Assert.False(x.ExecutionAuthorized);Assert.False(x.LiveEnabled);Assert.True(x.OddLot);
    }
    [Fact] public void AllIntegerRisksAndPriorFractionalRatesRemainWithinFifteenPercent()
    {
        foreach(var rate in ExposureAssumptions.Rates)
        {
            var x=SimulationSizer.Size(new(),Signal(),Costs(),rate,Assumptions());
            Assert.True(x.TotalRisk<=100*rate);Assert.False(x.ExecutionAuthorized);
        }
        Assert.Equal(17,ExposureAssumptions.Rates.Count);
        Assert.Contains(.04m,ExposureAssumptions.Rates);Assert.Contains(.075m,ExposureAssumptions.Rates);
        Assert.Contains(.125m,ExposureAssumptions.Rates);
    }
    [Fact] public void UnknownScopeCannotInventMoreLeverageOrUseBrokerMargin()
    {
        Assert.Throws<ArgumentException>(()=>Assumptions(30).Validate(.15m));
        Assert.Throws<ArgumentException>(()=>Assumptions().Validate(.16m));
        Assert.Throws<ArgumentException>(()=>Assumptions(margin:.03m).Validate(.15m));
        var favorable=SimulationSizer.Size(new(),Signal(),Costs(),.15m,Assumptions(margin:.025m));
        Assert.True(favorable.Notional<=2000);Assert.False(favorable.ExecutionAuthorized);
        Assert.Throws<ArgumentException>(()=>Assumptions(annual:0,days:1).Validate(.15m));
    }
    [Fact] public void BiggerExposureCannotBypassMarginOrNegativeTarget()
    {
        var ten=SimulationSizer.Size(new(),Signal(target:.001m),Costs(),.15m,Assumptions(10,margin:.10m));
        var twenty=SimulationSizer.Size(new(),Signal(target:.001m),Costs(),.15m,Assumptions(20,margin:.10m));
        Assert.Equal(ten.Quantity,twenty.Quantity);Assert.False(twenty.ConditionalAdmissible);
        Assert.True(twenty.Notional<1000);
    }
    [Fact] public void MinimumRoundsAboveFeeThresholdAndStillIsNotPermission()
    {
        var a=Assumptions();var s=Signal();var c=Costs();var m=ExposureStudy.Minimum(s,c,a)!;
        Assert.True(m.NetTarget>0);Assert.True(m.WithinFifteenPercent);Assert.False(m.ExecutionAuthorized);
        var unit=s.TakeProfitDistance-c.Spread-c.Slippage-c.AdverseGap-
            (s.EntryMidpoint!.Value+c.Spread/2)*a.AnnualFinancingRate*a.FinancingReserveDays/360;
        Assert.True((m.Quantity-.01m)*unit-4<=0);
        Assert.Equal(0,m.Quantity%.01m);
    }
    [Fact] public void SurplusOrGeometryFailureHasNoFiniteUsefulExposure()
    {
        Assert.Null(ExposureStudy.Minimum(Signal(target:.0004m),Costs(),Assumptions()));
        Assert.Null(ExposureStudy.Minimum(Signal(stop:.00001m),Costs(),Assumptions()));
    }
    [Fact] public void FinancingReserveRaisesThresholdAndActualCostUsesCalendarDuration()
    {
        var s=Signal();var c=Costs();var without=ExposureStudy.Minimum(s,c,Assumptions(annual:0,days:0))!;
        var with=ExposureStudy.Minimum(s,c,Assumptions())!;
        Assert.True(with.Quantity>without.Quantity);Assert.True(with.TotalRisk>without.TotalRisk);
        Assert.Equal(1,Assumptions().Financing(3600,At,At.AddDays(1)));
        Assert.Throws<ArgumentException>(()=>Assumptions().Financing(100,At,At.AddSeconds(-1)));
    }
    [Fact] public void FundingOverrunDoesNotChangeOriginalExitRulesOrDisappearFromAudit()
    {
        var bars=new[]{Bar(At),Bar(At.AddDays(5),high:1.126m)};
        var r=ProgressiveRiskSimulation.Run("pullback",bars,[Signal()],[],Costs(),.15m,Assumptions());
        var t=Assert.Single(r.Trades);
        Assert.Equal("TAKE_PROFIT",t.Trade.Reason);Assert.True(t.FinancingReserveExceeded);
        Assert.True(t.FinancingCost>t.Size.FinancingReserve);Assert.Equal(1,r.Metrics.FinancingReserveExceedances);
        Assert.Equal(t.Trade.GrossPnl-t.Size.Commission-t.Size.Spread-t.Size.Slippage-t.FinancingCost,t.Trade.NetPnl);
    }
    [Fact] public void GapRiskBreachIsReportedAndPendingManagementDoesNotStopWithEntries()
    {
        var bars=new[]{Bar(At),Bar(At.AddMinutes(15),.95m,.95m,.95m),Bar(At.AddDays(1))};
        var r=ProgressiveRiskSimulation.Run("pullback",bars,[Signal(),Signal() with {EntryAt=At.AddDays(1),SignalAt=At.AddDays(1)}],
            [],Costs(),.15m,Assumptions());
        Assert.True(Assert.Single(r.Trades).RiskBudgetBreached);Assert.True(r.Metrics.RiskBudgetBreaches>0);
        Assert.True(r.Metrics.LossBudgetExhausted);Assert.True(r.Metrics.CapitalExhausted);
        Assert.Equal("CUMULATIVE_LOSS_LIMIT",r.Rejections.Single().Key);
        Assert.Null(r.Ledger.PendingId);Assert.False(r.ExecutionAuthorized);
    }
}
