using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class PaperDataTests
{
    private static readonly DateTimeOffset Now=DateTimeOffset.UtcNow;
    private static PaperEnvelope Envelope(string kind,object data,string account="PAPER-test")=>
        new(kind,account,Now,JsonSerializer.SerializeToElement(data,PaperData.Json));
    private static PaperCandle Candle(int minutes=15)=>new(Now.AddDays(-1),minutes,1.1m,1.2m,1m,1.15m,null,null);
    private static PaperQuote Quote(string type="FROZEN",int marketType=2)=>new("EUR/USD",1.1m,1.1002m,null,.0002m,
        Now,Now,Now,"IBKR_TWS",type,marketType,null,false,null);

    [Fact] public void UnknownAccountAndUnknownFieldsFailClosed()
    {
        var envelope=Envelope("positions",Array.Empty<PaperPosition>());
        Assert.Throws<InvalidDataException>(()=>PaperData.Validate(envelope,"PAPER-other",Now));
        using var doc=JsonDocument.Parse("{\"code\":\"IBKR_354\",\"account\":\"DU123\"}");
        Assert.Throws<JsonException>(()=>PaperData.Validate(envelope with{Kind="event",Data=doc.RootElement},"PAPER-test",Now));
    }
    [Fact] public void FrozenDelayedAndRealtimeObservationsCannotAuthorizeOrders()
    {
        foreach(var (kind,value) in new[]{("REALTIME",1),("FROZEN",2),("DELAYED",3),("FROZEN",4)})
        {
            var quote=Quote(kind,value);PaperData.Validate(Envelope("quote",quote),"PAPER-test",Now);
            Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("quote",quote with{Executable=true}),"PAPER-test",Now));
        }
        Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("quote",Quote("REALTIME",2)),"PAPER-test",Now));
    }
    [Fact] public void IncompleteCrossedOrFutureQuotesAreRejected()
    {
        foreach(var quote in new[]{Quote() with{Ask=null},Quote() with{Ask=1.0m},Quote() with{Spread=1m},Quote() with{ReceivedAt=Now.AddMinutes(1)}})
            Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("quote",quote),"PAPER-test",Now));
        var unavailable=Quote("UNAVAILABLE",0) with{Bid=null,Ask=null,Spread=null,BidReceivedAt=null,AskReceivedAt=null};
        PaperData.Validate(Envelope("quote",unavailable),"PAPER-test",Now);
    }
    [Fact] public void ClosedValidatedOhlcAndNullForexVolumeRequired()
    {
        PaperData.Validate(Envelope("candles",new[]{Candle()}),"PAPER-test",Now);
        foreach(var candle in new[]{Candle() with{Volume=1},Candle() with{High=1},Candle() with{OpenedAt=Now},Candle() with{Minutes=5}})
            Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("candles",new[]{candle}),"PAPER-test",Now));
        Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("candles",new[]{Candle(),Candle()}),"PAPER-test",Now));
        // Native session offsets are retained; no synthetic UTC re-bucketing.
        PaperData.Validate(Envelope("candles",new[]{Candle(240)}),"PAPER-test",Now);
    }
    [Fact] public void MonetaryValuesAndCurrencyLabelsRemainSeparate()
    {
        var rows=new[]{new PaperBalanceValue("Currency","USD","USD"),new("NetLiquidation","1000000","USD"),
            new("TotalCashValue","1000000","USD"),new("AvailableFunds","1000000","USD")};
        var account=new PaperAccount("USD",rows,Now);
        PaperData.Validate(Envelope("account",account),"PAPER-test",Now);
        Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("account",account with{Values=rows.Skip(1).ToArray()}),"PAPER-test",Now));
        Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("account",account with{Values=[rows[0],rows[1] with{Value="NaN"},rows[2],rows[3]]}),"PAPER-test",Now));
        Assert.Equal(100,new RiskPolicy().AllocatedCapital);Assert.Equal(20,new RiskPolicy().CumulativeLossLimit);
    }
    [Fact] public void ConnectionCannotClaimLiveOrMissingVerification()
    {
        var status=new PaperConnection("CONNECTED",true,7497,73,226,"10.50.2",true,false,false,null);
        PaperData.Validate(Envelope("status",status),"PAPER-test",Now);
        foreach(var invalid in new[]{status with{AccountVerified=false},status with{Port=7496},status with{ReadOnly=false},
            status with{LiveEnabled=true},status with{OrdersSupported=true}})
            Assert.Throws<InvalidDataException>(()=>PaperData.Validate(Envelope("status",invalid),"PAPER-test",Now));
    }
    [DatabaseFact] public async Task CandlePersistenceDeduplicatesAndSurvivesNewStore()
    {
        var connection=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
        var store=new PostgresStore(connection);await store.Migrate();await store.VerifySchema();var account="PAPER-TEST-"+Guid.NewGuid();
        foreach(var minutes in new[]{15,60,240})
        {
            var envelope=Envelope("candles",new[]{Candle(minutes)},account);
            Assert.Equal(1,await store.SavePaper(envelope,account,Now));Assert.Equal(0,await store.SavePaper(envelope,account,Now));
            var recovered=new PostgresStore(connection);Assert.Equal(Candle(minutes),Assert.Single(await recovered.PaperCandles(account,minutes)));
            await Assert.ThrowsAsync<InvalidDataException>(()=>store.SavePaper(Envelope("candles",new[]{Candle(minutes) with{Close=1.16m}},account),account,Now));
            Assert.Equal(Candle(minutes),Assert.Single(await recovered.PaperCandles(account,minutes)));
        }
    }
    [DatabaseFact] public async Task SnapshotAndEventsPersistWithPaperIsolation()
    {
        var store=new PostgresStore(Environment.GetEnvironmentVariable("TRADING_TEST_DB")!);await store.Migrate();
        var account="PAPER-TEST-"+Guid.NewGuid();var quote=Envelope("quote",Quote(),account);
        Assert.Equal(1,await store.SavePaper(quote,account,Now));Assert.Equal(0,await store.SavePaper(quote,account,Now));
        var snapshot=await store.LatestPaper(account,"quote");Assert.NotNull(snapshot);
        Assert.Equal(Quote(),PaperData.Read<PaperQuote>(snapshot!.Data));
        Assert.Null(await store.LatestPaper("SIM-PAPER","quote"));
        await store.SavePaper(Envelope("event",new PaperEvent("IBKR_354"),account),account,Now);
        Assert.NotNull(await store.LatestPaper(account,"event"));
    }
}
