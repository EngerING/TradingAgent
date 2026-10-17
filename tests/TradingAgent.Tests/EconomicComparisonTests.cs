using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Api;
using Xunit;

namespace TradingAgent.Tests;

public class EconomicComparisonTests
{
    private static readonly DateTimeOffset Now=new(2026,10,4,12,0,0,TimeSpan.Zero);
    private static EconomicEvidence Verified(decimal v)=>new(v,EconomicEvidenceStatus.AccountVerified,"SYNTHETIC_ACCOUNT_EVIDENCE",Now,Now.AddSeconds(30));
    private static EconomicEvidence Unknown=>new(null,EconomicEvidenceStatus.Unknown,"MISSING",Now,Now.AddSeconds(30));
    private static EconomicComparisonInput Input=>new("EUR/USD",50,1,Verified(1),Verified(1),.001m,.02m,
        new(Verified(.01m),"USD",Verified(1)),new(Verified(.02m),"USD",Verified(1)),
        Verified(.0001m),Verified(.0002m),Verified(.0005m),Verified(1),Verified(1),Verified(1),Verified(1));
    private static EconomicComparisonResult Analyze(EconomicComparisonInput input,AccountState? account=null)=>
        EconomicComparison.Analyze(new(),account??AccountState.Initial("SIM-E0-TEST",100,Now),input,Now);

    [Fact] public void ArithmeticIncludesBothFeesSpreadSlippageGapAndBreakEvenOnce()
    {
        var r=Analyze(Input);
        Assert.Equal("VERIFIED_MODEL_ONLY",r.Status);Assert.False(r.ExecutionAuthorized);
        Assert.Equal(50m,r.NominalExposure);Assert.Equal(50m,r.RequiredMargin);
        Assert.Equal(.05m,r.StopLoss);Assert.Equal(.045m,r.TotalCosts);
        Assert.Equal(.12m,r.LossIncludingCostsAndGap);Assert.Equal(.955m,r.PotentialNetProfit);
        Assert.Equal(.0009m,r.BreakEvenPriceDistance);Assert.Equal(9m,r.BreakEvenPips);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",r.RiskGateReason);
    }
    [Fact] public void UnknownClosingCostCannotBecomeZeroButOpeningAloneCanBlockRisk()
    {
        var i=Input with {Opening=new(Verified(2),"USD",Verified(1)),Closing=new(Unknown,null,Verified(1))};
        var r=Analyze(i);Assert.Equal("UNVERIFIED",r.Status);Assert.Null(r.TotalCosts);
        Assert.Null(r.PotentialNetProfit);Assert.Null(r.BreakEvenPriceDistance);Assert.Null(r.LossIncludingCostsAndGap);
        Assert.Contains("COST_EXCEEDS_RISK_BUDGET",r.Reasons);Assert.Equal(2.015m,r.KnownCostLowerBound);
    }
    [Fact] public void PositiveGrossProfitCanHaveNegativeNetAndFeesRejectMaximumRisk()
    {
        var r=Analyze(Input with {Quantity=1,ProposedRisk=.005m,Opening=new(Verified(2),"USD",Verified(1)),Closing=new(Verified(2),"USD",Verified(1))});
        Assert.True(r.PotentialGrossProfit>0);Assert.True(r.PotentialNetProfit<0);
        Assert.Contains("POSITIVE_GROSS_NONPOSITIVE_NET",r.Reasons);Assert.Contains("COST_EXCEEDS_RISK_BUDGET",r.Reasons);
        Assert.Equal(.5m,r.EffectiveBudget);Assert.Equal(.25m,r.OrdinaryBudget);Assert.False(r.ExecutionAuthorized);
    }
    [Fact] public void CommissionCurrenciesRequireConversionEvidence()
    {
        var i=Input with {Opening=new(Verified(.01m),"EUR",Verified(2))};
        Assert.Equal(.02m,Analyze(i).OpeningCommissionUsd);
        var r=Analyze(i with {Opening=i.Opening with {ToUsd=Unknown}});
        Assert.Null(r.OpeningCommissionUsd);Assert.Null(r.TotalCosts);Assert.Equal("UNVERIFIED",r.Status);
        Assert.Throws<ArgumentException>(()=>Analyze(Input with {Opening=new(Verified(1),"USD",Verified(2))}));
        Assert.Throws<ArgumentException>(()=>Analyze(Input with {Opening=new(Verified(1),"INVALID",Verified(1))}));
    }
    [Fact] public void ManualPreviewCannotAuthorizeOrBeExtrapolatedToAnotherQuantity()
    {
        var scoped=Verified(2) with {Status=EconomicEvidenceStatus.ManualEstimate,QuantityScope=100};
        var r=Analyze(Input with {Opening=new(scoped,"USD",Verified(1))});
        Assert.Null(r.OpeningCommissionUsd);Assert.Equal("UNVERIFIED",r.Status);Assert.False(r.ExecutionAuthorized);
        Assert.Equal(2,Analyze(Input with {Quantity=100,Opening=new(scoped,"USD",Verified(1))}).OpeningCommissionUsd);
    }
    [Fact] public void ExpiredEvidenceAndUnknownPermissionsFailClosed()
    {
        var r=Analyze(Input with {Price=Verified(1) with {ValidUntil=Now.AddTicks(-1),At=Now.AddSeconds(-30)}});
        Assert.Equal("UNVERIFIED",r.Status);
        Assert.Contains("ACCOUNT_NOT_PERMITTED",Analyze(Input with {AccountPermitted=Verified(0)}).Reasons);
        Assert.Equal("UNVERIFIED",Analyze(Input with {AccountPermitted=Unknown}).Status);
    }
    [Fact] public void MinimumStepAndVirtualCapitalAreIndependentOfPaperFunds()
    {
        Assert.Contains("BELOW_MINIMUM_QUANTITY",Analyze(Input with {MinimumQuantity=Verified(20000)}).Reasons);
        Assert.Contains("INVALID_QUANTITY_INCREMENT",Analyze(Input with {Quantity=50.5m,QuantityStep=Verified(1)}).Reasons);
        var r=Analyze(Input with {Quantity=1_000_000});
        Assert.Contains("VIRTUAL_CAPITAL_INSUFFICIENT",r.Reasons);Assert.Contains("VIRTUAL_MARGIN_INSUFFICIENT",r.Reasons);
        Assert.Equal(100,r.Capital);Assert.Equal(20,r.LossAllowance);
    }
    [Fact] public void ExistingHaltsReservationsAndReducedBudgetsRemainEffective()
    {
        var a=AccountState.Initial("SIM-E0-TEST",100,Now);
        Assert.Contains("EMERGENCY_TEST",Analyze(Input,a.Halt("EMERGENCY_TEST")).Reasons);
        Assert.Contains("POSITION_LIMIT",Analyze(Input,a with {ReservationId="synthetic"}).Reasons);
        var reduced=Analyze(Input,a with {LossStreak=3});Assert.Equal(.125m,reduced.EffectiveBudget);
        Assert.Throws<ArgumentException>(()=>Analyze(Input with {ProposedRisk=.01m}));
        Assert.Throws<ArgumentException>(()=>Analyze(Input,AccountState.Initial("SIM-BAD",1_000_000,Now)));
    }
    [Fact] public void OtherInstrumentUsesMultiplierAndDoesNotReportForexPips()
    {
        var r=Analyze(Input with {Instrument="SYNTHETIC-OTHER",Multiplier=2,Quantity=10});
        Assert.Equal(20,r.NominalExposure);Assert.Equal(.02m,r.StopLoss);Assert.Null(r.BreakEvenPips);
        Assert.False(r.ExecutionAuthorized);
    }
    [Fact] public void OfflineStudyKeepsUnknownsScopesAndPolicyWithoutVerifiedAlternatives()
    {
        var path=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"../../../../../config/economic-study.json"));
        var before=File.ReadAllText(path);
        var result=EconomicStudyRunner.Run(new(),path,Now);
        Assert.False(result.GetProperty("connectedToTws").GetBoolean());Assert.False(result.GetProperty("ordersSupported").GetBoolean());
        Assert.Empty(result.GetProperty("accountVerifiedAlternatives").EnumerateArray());
        Assert.Equal(8,result.GetProperty("publicFeeLowerBoundComparisons").GetArrayLength());
        foreach(var row in result.GetProperty("publicFeeLowerBoundComparisons").EnumerateArray())
            Assert.Equal("UNVERIFIED",row.GetProperty("result").GetProperty("status").GetString());
        Assert.Equal(before,File.ReadAllText(path));
    }
}
