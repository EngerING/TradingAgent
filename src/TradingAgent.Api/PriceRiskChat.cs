using System.Text.Json;
using System.Text.Json.Nodes;
namespace TradingAgent.Api;

public static class PriceRiskChat
{
    public static bool Matches(string message)=>!System.Text.RegularExpressions.Regex.IsMatch(message,@"\bR(1|5)\b",System.Text.RegularExpressions.RegexOptions.IgnoreCase) && System.Text.RegularExpressions.Regex.IsMatch(message,"experimental|price.risk|R10.*(riesgo|precio|comisi)|arriesga.*R10|riesgo.*R10",System.Text.RegularExpressions.RegexOptions.IgnoreCase);
    public static JsonObject Respond(SolRequest request,JsonElement snapshot,JsonElement state)
    {
        var metrics=new List<object>();
        if(state.TryGetProperty("last_assessment",out var a) && a.ValueKind==JsonValueKind.Object)
            foreach(var (key,label) in new[]{("price_risk","PRICE_RISK alcanzable"),("estimated_fees","Fees ESTIMATED"),("spread_cost","Spread modelado"),("slippage_cost","Slippage modelado"),("financing_reserve","Financiación provisionada"),("estimated_all_in_loss","Pérdida total prevista")})
                metrics.Add(new{label,value=a.TryGetProperty(key,out var v)&&v.ValueKind==JsonValueKind.String&&decimal.TryParse(v.GetString(),System.Globalization.NumberStyles.Number,System.Globalization.CultureInfo.InvariantCulture,out var n)?(decimal?)n:null,format="money"});
        var trades=state.GetProperty("trades").EnumerateArray().TakeLast(1).ToArray();
        var reason=a.ValueKind==JsonValueKind.Object && a.TryGetProperty("reason",out var r)?r.ToString():"NO_ASSESSMENT";
        return JsonSerializer.SerializeToNode(new{requestId=request.RequestId,status="LOCAL_EVIDENCE_ONLY",provider="DETERMINISTIC_JOURNAL",model=(string?)null,
            text="R10 Experimental es independiente de R10 original (riesgo all-in). Su presupuesto por precio es US$10; el stop técnico y el capital financiado pueden producir un riesgo menor. Fees, spread, slippage y financiación se contabilizan por separado. Pérdida total prevista limitada a US$15 para admisión; el stop no garantiza la pérdida máxima. Estado: "+state.GetProperty("status")+". Evaluación: "+reason+". Cierres Shadow: "+state.GetProperty("trades").GetArrayLength()+". No hubo ensayo Paper en este perfil. Kronos sólo observa; sin probabilidad calibrada ni acuerdo inferido.",
            metrics,table=new{columns=new[]{"Cierre Shadow","P&L bruto","P&L neto simulado","Motivo"},rows=trades.Select(t=>new object?[]{t.GetProperty("closed_at").GetString(),t.GetProperty("gross_pnl").GetString(),t.GetProperty("realized_all_in_pnl").GetString(),t.GetProperty("reason").GetString()})},
            chart=new{title="Sin inferencias",unit="USD",series=Array.Empty<object>()},warnings=new[]{"SIMULATED_SHADOW no es un fill IBKR. Paper bloqueado; EmergencyStop continúa activo.","Costos ESTIMATED; condiciones efectivas UNKNOWN. US$14 no es un máximo garantizado."},operationDetails=(object?)null,prediction=snapshot.GetProperty("prediction"),command=(object?)null,usage=new{inputTokens=0,outputTokens=0,estimatedCostUsd=0,reservedCostUsd=0}})!.AsObject();
    }
}
