using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace TradingAgent.Infrastructure;

internal static class AggressiveGrowthInvariants
{
    private static decimal Number(JsonElement e,string key)
    {
        if(!e.TryGetProperty(key,out var v)||v.ValueKind!=JsonValueKind.String||
           !decimal.TryParse(v.GetString(),NumberStyles.Float,CultureInfo.InvariantCulture,out var n))
            throw new InvalidDataException("R20_DECIMAL_REQUIRED");
        return n;
    }
    private static void Require(bool valid,string reason)
    {if(!valid)throw new InvalidDataException(reason);}
    public static void Validate(JsonElement p,string? previous)
    {
        try { ValidateState(p,previous); }
        catch(Exception e) when(e is KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException("R20_PAYLOAD_INVALID",e);}
    }
    private static void ValidateState(JsonElement p,string? previous)
    {
        Require(p.GetProperty("scope").GetString()=="AGGRESSIVE_GROWTH_R20" &&
            p.GetProperty("classification").GetString()=="SHADOW_SIMULATED" &&
            !p.GetProperty("live_enabled").GetBoolean() && p.GetProperty("broker_orders").GetInt32()==0,"R20_SHADOW_ONLY");
        var s=p.GetProperty("state");var protocol=s.GetProperty("protocol");
        Require(protocol.GetProperty("profile").GetString()=="AGGRESSIVE_GROWTH_R20" &&
            Number(protocol,"initial_capital_usd")==100 && Number(protocol,"price_risk_fraction")==.20m &&
            Number(protocol,"max_leverage")==10 && Number(protocol,"openai_budget_usd")==0 &&
            !protocol.GetProperty("broker_orders_enabled").GetBoolean() && !protocol.GetProperty("live_enabled").GetBoolean(),"R20_IMMUTABLE_LIMITS");
        Require(s.GetProperty("run_kind").GetString() is "FORWARD" or "HISTORICAL","R20_RUN_KIND_REQUIRED");
        var stopped=s.GetProperty("stop_requested").GetBoolean();
        var updated=s.GetProperty("updated_at").GetDateTimeOffset();
        Require(updated>=s.GetProperty("started_at").GetDateTimeOffset(),"R20_TIME_CANNOT_REWIND");
        foreach(var k in new[]{"engine_hash","strategy_version"})
            Require(Regex.IsMatch(s.GetProperty(k).GetString()??"","^[a-f0-9]{64}$"),"R20_VERSION_REQUIRED");
        var paper=s.GetProperty("paper");
        Require(paper.GetProperty("state").GetString()=="BLOCKED" && !paper.GetProperty("authorization_granted").GetBoolean(),"R20_PAPER_NOT_AUTHORIZED");
        Require(s.GetProperty("seen").EnumerateArray().Select(x=>x.GetString()).Distinct().Count()==s.GetProperty("seen").GetArrayLength(),"R20_DUPLICATE_OPPORTUNITY");
        var portfolios=s.GetProperty("portfolios");
        Require(portfolios.EnumerateObject().Count()==2,"R20_PORTFOLIOS_REQUIRED");
        var runKind=s.GetProperty("run_kind").GetString()!;
        ValidatePortfolio(portfolios.GetProperty("R20"),10,runKind);
        ValidatePortfolio(portfolios.GetProperty("BASELINE_1X"),1,runKind);
        if(previous is null)
        {
            foreach(var port in portfolios.EnumerateObject())Require(Number(port.Value,"cash_equity")==100 &&
                port.Value.GetProperty("trades").GetArrayLength()==0 && port.Value.GetProperty("active").ValueKind==JsonValueKind.Null,"R20_INITIAL_STATE_REQUIRED");
            return;
        }
        using var old=JsonDocument.Parse(previous);var before=old.RootElement.GetProperty("state");
        Require(updated>=before.GetProperty("updated_at").GetDateTimeOffset(),"R20_TIME_CANNOT_REWIND");
        Require(!before.GetProperty("stop_requested").GetBoolean() || stopped,"R20_STOP_LATCH_IMMUTABLE");
        foreach(var key in new[]{"protocol","engine_hash","strategy_version","run_kind","started_at"})
            Require(s.GetProperty(key).GetRawText()==before.GetProperty(key).GetRawText(),"R20_PREREGISTRATION_IMMUTABLE");
        Require(before.GetProperty("status").GetString()!="STOPPED" || s.GetProperty("status").GetString()=="STOPPED","R20_STOP_IS_PERSISTENT");
        Preserve(before.GetProperty("seen"),s.GetProperty("seen"),"R20_SIGNALS_CANNOT_RESET");
        Preserve(before.GetProperty("signals"),s.GetProperty("signals"),"R20_SIGNAL_EVIDENCE_IMMUTABLE");
        foreach(var name in new[]{"R20","BASELINE_1X"})
        {
            var b=before.GetProperty("portfolios").GetProperty(name);var a=portfolios.GetProperty(name);
            Require(Number(a,"consumed_loss")>=Number(b,"consumed_loss"),"R20_LOSSES_CANNOT_RESET");
            Require(Number(a,"maximum_drawdown")>=Number(b,"maximum_drawdown") && Number(a,"peak_equity")>=Number(b,"peak_equity"),"R20_DRAWDOWN_CANNOT_RESET");
            Preserve(b.GetProperty("trades"),a.GetProperty("trades"),"R20_TRADES_IMMUTABLE");
            var active=b.GetProperty("active");
            if(active.ValueKind!=JsonValueKind.Null)
            {
                var id=active.GetProperty("id").GetString();var next=a.GetProperty("active");
                Require(next.ValueKind!=JsonValueKind.Null && next.GetProperty("id").GetString()==id ||
                    a.GetProperty("trades").EnumerateArray().Any(t=>t.GetProperty("id").GetString()==id),"R20_INVENTORY_CANNOT_DISAPPEAR");
                if(next.ValueKind!=JsonValueKind.Null && next.GetProperty("id").GetString()==id)
                    foreach(var key in new[]{"quantity","entry","stop","target","side","at"})
                        Require(next.GetProperty(key).GetRawText()==active.GetProperty(key).GetRawText(),"R20_OPEN_POSITION_IMMUTABLE");
            }
        }
    }
    private static void Preserve(JsonElement before,JsonElement after,string reason)
    {
        var values=after.EnumerateArray().Select(x=>x.GetRawText()).ToHashSet(StringComparer.Ordinal);
        Require(before.EnumerateArray().All(x=>values.Contains(x.GetRawText())),reason);
    }
    private static void ValidatePortfolio(JsonElement p,decimal leverage,string runKind)
    {
        Require(Number(p,"initial_capital")==100,"R20_LOGICAL_CAPITAL_REQUIRED");
        foreach(var k in new[]{"fees","spread_cost","slippage_cost","financing_cost","consumed_loss","current_drawdown","maximum_drawdown"})
            Require(Number(p,k)>=0,"R20_NEGATIVE_COST_OR_DRAWDOWN");
        Require(Math.Abs(Number(p,"cash_equity")-100-Number(p,"realized_net"))<.00000001m,"R20_CASH_RECONCILIATION");
        var trades=p.GetProperty("trades").EnumerateArray().ToArray();
        Require(trades.Select(t=>t.GetProperty("id").GetString()).Distinct().Count()==trades.Length,"R20_DUPLICATE_TRADE");
        var net=0m;var gross=0m;var loss=0m;
        foreach(var t in trades)
        {
            Require(t.GetProperty("classification").GetString()=="SHADOW_SIMULATED","R20_FILL_CLASSIFICATION");
            Require(t.GetProperty("run_kind").GetString()==runKind,"R20_FILL_RUN_KIND");
            net+=Number(t,"net_pnl");gross+=Number(t,"gross_pnl");loss+=Math.Max(0,-Number(t,"net_pnl"));
        }
        Require(Math.Abs(net-Number(p,"realized_net"))<.00000001m && Math.Abs(gross-Number(p,"realized_gross"))<.00000001m &&
            Math.Abs(loss-Number(p,"consumed_loss"))<.00000001m,"R20_LEDGER_RECONCILIATION");
        var active=p.GetProperty("active");
        if(active.ValueKind==JsonValueKind.Null)
            Require(Math.Abs(Number(p,"equity")-Number(p,"cash_equity"))<.00000001m,"R20_FLAT_EQUITY_RECONCILIATION");
        else
        {
            Require(active.GetProperty("classification").GetString()=="SHADOW_SIMULATED","R20_FILL_CLASSIFICATION");
            Require(active.GetProperty("run_kind").GetString()==runKind,"R20_FILL_RUN_KIND");
            var q=Number(active,"quantity");var entry=Number(active,"entry");var stop=Number(active,"stop");var target=Number(active,"target");
            var equity=Number(active,"entry_equity");var side=active.GetProperty("side").GetString();
            Require(q>0 && entry>0 && stop>0 && target>0 && equity>0 &&
                (side=="LONG" && stop<entry && entry<target || side=="SHORT" && target<entry && entry<stop),"R20_BRACKET_GEOMETRY");
            Require(q*entry<=equity*leverage+.00000001m && q*Math.Abs(entry-stop)<=equity*.2m+.00000001m,"R20_ENTRY_EXPOSURE_OR_PRICE_RISK");
            Require(Number(active,"margin")>=0 && Number(active,"margin")<=equity,"R20_MARGIN_LIMIT");
        }
    }
}
