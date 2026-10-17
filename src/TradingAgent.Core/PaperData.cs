using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TradingAgent.Core;

public sealed record PaperEnvelope(string Kind,string AccountId,DateTimeOffset ReceivedAt,JsonElement Data);
public sealed record PaperConnection(string State,bool AccountVerified,int Port,int ClientId,int? ServerVersion,
    string? SdkVersion,bool ReadOnly,bool LiveEnabled,bool OrdersSupported,string? Reason);
public sealed record PaperBalanceValue(string Tag,string Value,string Currency);
public sealed record PaperAccount(string BaseCurrency,PaperBalanceValue[] Values,DateTimeOffset ReceivedAt);
public sealed record PaperPosition(long ConId,string Symbol,string SecurityType,string Currency,decimal Quantity,decimal AverageCost);
public sealed record PaperContract(long ConId,string Symbol,string Currency,string SecurityType,string Exchange,string ValidExchanges,
    decimal MinTick,string MarketRuleIds,string TradingHours,string LiquidHours,string TimeZone,string OrderTypes,
    decimal? MinimumSize,decimal? SizeIncrement,bool RestrictionsVerified,DateTimeOffset ReceivedAt);
public sealed record PaperQuote(string Instrument,decimal? Bid,decimal? Ask,decimal? Last,decimal? Spread,DateTimeOffset ReceivedAt,
    DateTimeOffset? BidReceivedAt,DateTimeOffset? AskReceivedAt,string Source,string DataType,int MarketDataType,
    DateTimeOffset? SourceTimestamp,bool Executable,string? Reason);
public sealed record PaperCandle(DateTimeOffset OpenedAt,int Minutes,decimal Open,decimal High,decimal Low,decimal Close,decimal? Volume,decimal? Spread);
public sealed record PaperEvent(string Code);

public static class PaperData
{
    public static readonly JsonSerializerOptions Json=new()
    {
        PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow,
        NumberHandling=JsonNumberHandling.AllowReadingFromString
    };
    public static T Read<T>(JsonElement data)=>data.Deserialize<T>(Json)??throw new InvalidDataException("MISSING_PAPER_DATA");
    private static void Require(bool condition){if(!condition)throw new InvalidDataException("INVALID_PAPER_DATA");}
    private static bool Currency(string? value)=>value is {Length:3} && value.All(c=>c is >= 'A' and <= 'Z');
    private static bool Label(string? value,int max=100)=>value is not null && value.Length<=max && !value.Any(char.IsControl);
    private static void Timestamp(DateTimeOffset at,DateTimeOffset now)
    {Require(at!=default && at.Offset==TimeSpan.Zero && at<=now.AddSeconds(5));}

    // Re-serialize known schemas: unknown fields and account numbers cannot enter persistence.
    public static JsonElement Validate(PaperEnvelope e,string expectedAccount,DateTimeOffset now)
    {
        Require(e.AccountId==expectedAccount && expectedAccount.StartsWith("PAPER-",StringComparison.Ordinal));
        Timestamp(e.ReceivedAt,now);Require(e.ReceivedAt>=now.AddMinutes(-5));
        object value=e.Kind switch
        {
            "status"=>Connection(Read<PaperConnection>(e.Data)),
            "account"=>Account(Read<PaperAccount>(e.Data),now),
            "positions"=>Positions(Read<PaperPosition[]>(e.Data)),
            "contract"=>Contract(Read<PaperContract>(e.Data),now),
            "quote"=>Quote(Read<PaperQuote>(e.Data),now),
            "candles"=>Candles(Read<PaperCandle[]>(e.Data),now),
            "event"=>Event(Read<PaperEvent>(e.Data)),
            _=>throw new InvalidDataException("UNKNOWN_PAPER_ENTITY")
        };
        return JsonSerializer.SerializeToElement(value,value.GetType(),Json);
    }
    private static PaperConnection Connection(PaperConnection s)
    {
        Require(s.State is "CONNECTING" or "CONNECTED" or "DISCONNECTED" or "REJECTED" or "DEGRADED");
        Require(s.Port==7497 && s.ClientId>0 && s.ReadOnly && !s.LiveEnabled && !s.OrdersSupported);
        Require(s.State!="CONNECTED" || s.AccountVerified && s.ServerVersion>0);
        Require(s.State is not ("DISCONNECTED" or "REJECTED" or "CONNECTING") || !s.AccountVerified);
        Require(Label(s.SdkVersion,40) && (s.Reason is null || SafeCode(s.Reason)));return s;
    }
    private static PaperAccount Account(PaperAccount a,DateTimeOffset now)
    {
        Timestamp(a.ReceivedAt,now);Require(Currency(a.BaseCurrency) && a.Values is {Length:>0 and <=100});
        foreach(var v in a.Values)
        {
            Require(v.Tag is "NetLiquidation" or "TotalCashValue" or "AvailableFunds" or "BuyingPower" or "ExcessLiquidity" or "Currency" or "CashBalance" or "SettledCash" or "AccruedCash" or "FutureOptionValue" or "FuturesPNL" or "NetLiquidationByCurrency" or "ExchangeRate" or "RealizedPnL" or "UnrealizedPnL" or "TotalCashBalance");
            Require(Currency(v.Currency));
            if(v.Tag=="Currency")Require(v.Value==a.BaseCurrency);
            else Require(decimal.TryParse(v.Value,NumberStyles.Float,CultureInfo.InvariantCulture,out _));
        }
        foreach(var tag in new[]{"NetLiquidation","TotalCashValue","AvailableFunds"})
            Require(a.Values.Count(v=>v.Tag==tag && v.Currency==a.BaseCurrency)==1);
        Require(a.Values.Any(v=>v.Tag=="Currency"));return a;
    }
    private static PaperPosition[] Positions(PaperPosition[] positions)
    {
        Require(positions is {Length:<=1000});
        foreach(var p in positions)Require(p.ConId>0 && Label(p.Symbol,30) && Label(p.SecurityType,10) && Currency(p.Currency));
        Require(positions.Select(p=>p.ConId).Distinct().Count()==positions.Length);return positions;
    }
    private static PaperContract Contract(PaperContract c,DateTimeOffset now)
    {
        Timestamp(c.ReceivedAt,now);
        Require(c.ConId>0 && c.Symbol=="EUR" && c.Currency=="USD" && c.SecurityType=="CASH" && c.Exchange=="IDEALPRO");
        Require(c.MinTick>0 && c.ValidExchanges.Split(',').Contains("IDEALPRO") && !c.RestrictionsVerified);
        Require(Label(c.MarketRuleIds) && Label(c.TradingHours,3000) && Label(c.LiquidHours,3000) && Label(c.TimeZone) && Label(c.OrderTypes,500));
        Require(c.MinimumSize is null or >0 && c.SizeIncrement is null or >0);return c;
    }
    private static PaperQuote Quote(PaperQuote q,DateTimeOffset now)
    {
        Timestamp(q.ReceivedAt,now);Require(q.Instrument=="EUR/USD" && q.Source=="IBKR_TWS" && !q.Executable);
        Require(q.DataType is "REALTIME" or "DELAYED" or "FROZEN" or "UNAVAILABLE");
        Require(q.MarketDataType is >=0 and <=4 && (q.Last is null or >0));
        if(q.Reason is not null)Require(SafeCode(q.Reason));
        if(q.DataType=="UNAVAILABLE")Require(q.Bid is null && q.Ask is null && q.Spread is null);
        else
        {
            Require(q.Bid>0 && q.Ask>=q.Bid && q.Spread==q.Ask-q.Bid && q.BidReceivedAt is not null && q.AskReceivedAt is not null);
            Timestamp(q.BidReceivedAt!.Value,now);Timestamp(q.AskReceivedAt!.Value,now);
            Require((q.DataType,q.MarketDataType) is ("REALTIME",1) or ("FROZEN",2) or ("DELAYED",3) or ("FROZEN",4));
        }
        if(q.SourceTimestamp is not null)Timestamp(q.SourceTimestamp.Value,now);return q;
    }
    private static PaperCandle[] Candles(PaperCandle[] candles,DateTimeOffset now)
    {
        Require(candles is {Length:<=10000});
        PaperCandle? previous=null;
        foreach(var c in candles)
        {
            Timestamp(c.OpenedAt,now);Require(c.Minutes is 15 or 60 or 240 && c.OpenedAt.AddMinutes(c.Minutes)<=now);
            Require(c.Open>0 && c.High>=Math.Max(c.Open,Math.Max(c.Close,c.Low)) && c.Low>0 && c.Low<=Math.Min(c.Open,Math.Min(c.Close,c.High)) && c.Close>0);
            Require(c.Volume is null && c.Spread is null); // MIDPOINT Forex, no volume invention
            if(previous is not null)Require(c.Minutes==previous.Minutes && c.OpenedAt>=previous.OpenedAt.AddMinutes(previous.Minutes));
            previous=c;
        }
        return candles;
    }
    private static bool SafeCode(string code)=>code.Length is >0 and <=80 && code.All(c=>char.IsAsciiLetterUpper(c)||char.IsAsciiDigit(c)||c=='_');
    private static PaperEvent Event(PaperEvent e){Require(SafeCode(e.Code));return e;}
}
