using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class RiskTests
{
    public static readonly DateTimeOffset Now=new(2026,1,5,12,0,0,TimeSpan.Zero);
    public static ExecutionFacts Execution => new("synthetic-test-fixture","SIMULATION","SIMULATED",Now,0,0,true,true,true,true,"SIMULATED");
    public static RiskRequest Request(decimal? risk=null)=>new("EUR/USD","BUY",1.0999m,1.1001m,1.099m,1,1,1,1,.1m,100,0,0,.0001m,.0002m,Now,risk,Execution);
    public static RiskPolicy Policy=>new(MaxLeverage:10);
    public static AccountState Account()=>AccountState.Initial("SIM-TEST",100,Now);
    [Theory][InlineData(.0025,.25)][InlineData(.005,.50)]
    public void HundredDollarsBudget(decimal fraction,decimal budget)
    {var r=RiskEngine.Evaluate(Policy,Account(),Request(fraction),Now);Assert.True(r.Allowed);Assert.Equal(budget,r.Budget);Assert.True(r.EstimatedLoss<=budget);Assert.NotEqual(r.RequiredMargin,r.EstimatedLoss);}
    [Fact]public void CompoundAndReduceWithoutChangingFraction()
    {var p=CapitalTests.IsolatedPolicy;var low=RiskEngine.Evaluate(p,Account().Mark(98,Now,p),Request(),Now);var high=RiskEngine.Evaluate(p,Account().Mark(110,Now,p),Request(),Now);Assert.Equal(.245m,low.Budget);Assert.Equal(.275m,high.Budget);Assert.True(low.Quantity<high.Quantity);}
    [Fact]public void MaxRiskAttemptDenied()=>Assert.Equal("RISK_EXCEEDS_POLICY",RiskEngine.Evaluate(Policy,Account(),Request(.006m),Now).Reason);
    [Fact]public void IbMinimumDoesNotFitSmallCapital()=>Assert.False(RiskEngine.Evaluate(Policy,Account(),Request() with{MinQuantity=20000},Now).Allowed);
    [Theory][InlineData(99,"DAILY_LIMIT")][InlineData(98,"WEEKLY_LIMIT")][InlineData(95,"DRAWDOWN_LIMIT")]
    public void LimitReachedHalts(decimal equity,string cause)
    {var a=Account().Mark(equity,Now,Policy);Assert.Contains(cause,a.Halts);Assert.Equal("HALT",RiskEngine.Evaluate(Policy,a,Request(),Now).Decision);}
    [Fact]public void FiveLossesAndPrevention()
    {var a=Account();for(int i=1;i<=5;i++)a=(a with{LossStreak=i}).Mark(100-i*.25m,Now,Policy);Assert.Equal(5,a.LossStreak);Assert.Contains("DAILY_LIMIT",a.Halts);var preventive=RiskEngine.Evaluate(Policy,Account() with{LossStreak=3},Request(),Now);Assert.Equal(.00125m,preventive.RiskFraction);}
    [Fact]public void FourthQuarterDollarLossBlocksFifthEntry()
    {var a=Account();for(int i=1;i<=4;i++)a=a.Mark(100-i*.25m,Now,Policy);Assert.Equal("HALT",RiskEngine.Evaluate(Policy,a,Request(),Now).Decision);}
    [Fact]public async Task AiRemainsDisabled()=>await Assert.ThrowsAsync<InvalidOperationException>(()=>new DisabledResearchAi().ProposeAsync(new("fixture",new(),"none",[],Policy),default));
    [Fact]public void OpenRiskAndOnePosition()
    {var a=Account() with{OpenPositions=[new(.1m,20,2)]};var r=RiskEngine.Evaluate(Policy,a,Request(),Now);Assert.Equal(.1m,r.OpenRisk);Assert.Equal("POSITION_LIMIT",r.Reason);}
    [Theory][InlineData(0,1.1)][InlineData(1.2,1.1)]
    public void BadMarketData(decimal bid,decimal ask)=>Assert.Equal("INVALID_INPUT",RiskEngine.Evaluate(Policy,Account(),Request() with{Bid=bid,Ask=ask},Now).Reason);
    [Fact]public void OldAndFutureDataDenied()
    {Assert.Equal("DATA_STALE",RiskEngine.Evaluate(Policy,Account(),Request() with{MarketAt=Now.AddMinutes(-1)},Now).Reason);Assert.Equal("DATA_STALE",RiskEngine.Evaluate(Policy,Account(),Request() with{MarketAt=Now.AddMinutes(1)},Now).Reason);}
    [Fact]public void ExternalFundsCannotIncreaseTheVirtualAllocation()
    {var a=Account().Mark(99,Now,Policy);Assert.Throws<InvalidOperationException>(()=>a.CashFlow(100));Assert.Equal(99,a.Equity);Assert.Contains("DAILY_LIMIT",a.Halts);}
    [Fact]public void LossLimitSurvivesNextDay()=>Assert.Contains("DAILY_LIMIT",Account().Mark(99,Now,Policy).Mark(99,Now.AddDays(1),Policy).Halts);
    [Fact]public void MarginAndLeverageConstrainEvenTightStop()
    {var r=RiskEngine.Evaluate(new(),Account(),Request() with{Stop=1.099899m},Now);Assert.True(r.NominalExposure<=100);Assert.True(r.RequiredMargin<=100);}
    [Fact]public void ModifiedStrategyCannotReuseApproval()
    {var s=new StrategyVersion("s","EMA",1,"EUR/USD","15,60,240","cross","stop",.001m,.002m,100,"closed-bars","{}");var approval=new StrategyApproval(s.Hash,Policy.Version,"PAPER_TRADING","owner",Now,Now.AddDays(1));Assert.True(approval.Matches(s,Policy,Now));Assert.False(approval.Matches(s with{StopDistance=.002m},Policy,Now));Assert.False((approval with{Environment="LIVE_TRADING"}).Matches(s,Policy,Now));}
    [Fact]public void SimilarityExcludesFutureAndOtherInstrument()
    {var old=new Experience("1","a","EUR/USD",Now.AddDays(-1),"London","s",.0025m,"no",true,new(){["rsi"]=50},"{}",0);var future=old with{Id="2",At=Now.AddDays(1)};Assert.Single(ExperienceSimilarity.Find(new(){["rsi"]=51},[old,future],new(){["rsi"]=10},"EUR/USD",Now));}
    [Fact]public void AiCannotInjectOrderOrRiskFields()
    {Assert.Throws<System.Text.Json.JsonException>(()=>ProposalValidator.Parse("{\"hypothesis\":\"x\",\"placeOrder\":true}",Policy));Assert.Throws<ArgumentException>(()=>ProposalValidator.Parse("{\"hypothesis\":\"x\",\"explanation\":\"x\",\"strategyHash\":\"a\",\"proposedRisk\":0.9,\"evidenceIds\":[]}",Policy));}
    [Fact]public async Task BrokerDisconnectAndDrop()
    {var b=new SimulatedBroker(new(),TimeProvider.System);await b.ConnectAsync(default);Assert.Equal(100,(await b.BalanceAsync(default)).Equity);b.FailConnection=true;await Assert.ThrowsAsync<IOException>(()=>b.QuoteAsync("EUR/USD",default));Assert.False(b.Connected);}
    [Fact]public async Task LiveAndUnrecognizedAccountAreRejected()
    {await Assert.ThrowsAsync<InvalidOperationException>(()=>new SimulatedBroker(new(Environment:"LIVE_TRADING"),TimeProvider.System).ConnectAsync(default));await Assert.ThrowsAsync<InvalidOperationException>(()=>new SimulatedBroker(new(AuthorizedAccount:"U123"),TimeProvider.System).ConnectAsync(default));Assert.Throws<InvalidOperationException>(()=>new BrokerOptions(Port:7496).Validate());}
    [Fact]public async Task MissingVolumeRemainsNull()
    {var b=new SimulatedBroker(new(),TimeProvider.System);await b.ConnectAsync(default);foreach(var tf in new[]{15,60,240})Assert.All(await b.HistoryAsync("EUR/USD",tf,default),c=>Assert.Null(c.Volume));await b.DisconnectAsync(default);Assert.False(b.Connected);}
}
