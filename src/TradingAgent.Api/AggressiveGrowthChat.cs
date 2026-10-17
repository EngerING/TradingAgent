using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TradingAgent.Api;

public static class AggressiveGrowthChat
{
    public static bool Matches(string message)=>
        !Regex.IsMatch(message,@"\bR(1|5|10)\b",RegexOptions.IgnoreCase) &&
        Regex.IsMatch(message,@"\bR20\b|aggressive|capital queda|apalancamiento|oportunidades encontramos|rechazamos la [úu]ltima|comisiones consumieron|Kronos apoyaba",RegexOptions.IgnoreCase);

    public static JsonObject Respond(SolRequest request,JsonElement snapshot,JsonElement state)
    {
        decimal? Number(JsonElement element,string key)=>element.TryGetProperty(key,out var n) && n.ValueKind==JsonValueKind.String &&
            decimal.TryParse(n.GetString(),NumberStyles.Float,CultureInfo.InvariantCulture,out var result)?result:null;
        string Text(JsonElement element,string key)=>element.TryGetProperty(key,out var n)&&n.ValueKind!=JsonValueKind.Null?n.ToString():"UNKNOWN";
        var metrics=new List<object>();
        foreach(var (key,label,format) in new[]{("equity","Equity R20","money"),("effectiveLeverage","Apalancamiento efectivo","number"),
            ("exposure","Exposición nominal","money"),("priceRisk","Riesgo por precio","money"),("commissions","Comisiones modeladas","money"),
            ("grossPnl","P&L bruto realizado","money"),("netPnl","P&L neto realizado","money"),("anticipatedTotalLoss","Pérdida total prevista","money")})
            metrics.Add(new{label,value=Number(state,key),format});
        var baseline=state.GetProperty("baseline");var k=state.GetProperty("kronos");
        var reason=state.TryGetProperty("lastNoTrade",out var noTrade)&&noTrade.ValueKind==JsonValueKind.Object?Text(noTrade,"reason"):"SIN_RECHAZOS_REGISTRADOS";
        var text=$"R20: {Text(state,"status")}; evidencia {Text(state,"evidenceQuality")}. Capital inicial US$100; equity actual US${Text(state,"equity")}. " +
            $"Apalancamiento {Text(state,"effectiveLeverage")}×, límite 10×; riesgo por precio hasta 20% del equity. " +
            $"Oportunidades evaluadas: {Text(state,"opportunities")}; señales auténticas: {Text(state,"signals")}; operaciones Shadow cerradas: {Text(state,"shadowTrades")}. " +
            $"Último NO_TRADE: {reason}. Comisiones modeladas US${Text(state,"commissions")}, P&L bruto US${Text(state,"grossPnl")} y neto US${Text(state,"netPnl")}. " +
            $"Baseline independiente sin apalancamiento: equity US${Text(baseline,"equity")}, cierres {Text(baseline,"closedTrades")}; puede rechazar tamaños distintos. " +
            $"Kronos {Text(k,"status")}, acuerdo {Text(k,"agreement")}; RAW_ONLY, probabilidad calibrada desconocida. " +
            "La evidencia no demuestra rentabilidad ni validación estadística. IBKR_PAPER bloqueado; esta cohorte no ha transmitido órdenes.";
        return JsonSerializer.SerializeToNode(new{
            requestId=request.RequestId,status="LOCAL_EVIDENCE_ONLY",provider="DETERMINISTIC_JOURNAL",model=(string?)null,text,metrics,
            table=new{columns=new[]{"Evidencia","Equity USD","Operaciones cerradas"},rows=new object?[][] {
                ["SHADOW_SIMULATED · R20",Text(state,"equity"),Text(state,"shadowTrades")],
                ["SHADOW_SIMULATED · baseline 1×",Text(baseline,"equity"),Text(baseline,"closedTrades")],
                ["IBKR_PAPER · bloqueado",null,0]}},
            chart=new{title="Sin inferencias de rentabilidad",unit="USD",series=Array.Empty<object>()},
            warnings=new[]{"Stop y pérdida prevista no garantizan una pérdida máxima. Costos y margen son modelos Shadow.",
                "Las autorizaciones R10 no habilitan R20. EmergencyStop y Live no se modifican.",
                "Métricas desconocidas permanecen UNKNOWN; cero cierres no implica estrategia rentable."},
            operationDetails=(object?)null,prediction=snapshot.GetProperty("prediction"),command=(object?)null,
            usage=new{inputTokens=0,outputTokens=0,estimatedCostUsd=0,reservedCostUsd=0}})!.AsObject();
    }
}

public static class AggressiveGrowthFreshness
{
    public static void Apply(JsonObject? state,DateTimeOffset now)
    {
        if(state is null)return;
        var fresh=state["updatedAt"]?.GetValue<string>() is string at && DateTimeOffset.TryParse(at,out var t) && now>=t && now-t<=TimeSpan.FromSeconds(180);
        state["evidenceQuality"]=fresh?"RECENT_JOURNAL":"STALE";
        if(!fresh && state["status"]?.GetValue<string>()=="SHADOW_RUNNING")state["status"]="SHADOW_HEARTBEAT_STALE";
        if(state["market"] is JsonObject market &&
            (market["at"]?.GetValue<string>() is not string quoteAt || !DateTimeOffset.TryParse(quoteAt,out var quote) || now<quote || now-quote>TimeSpan.FromSeconds(30)))
            market["status"]="STALE";
        if(state["kronos"] is JsonObject kronos)
        {
            bool Timestamp(string field,out DateTimeOffset timestamp)
            {timestamp=default;return kronos[field]?.GetValue<string>() is string value && DateTimeOffset.TryParse(value,out timestamp);}
            var usable=Timestamp("createdAt",out var created) && Timestamp("decisionAt",out var decision) &&
                Timestamp("candleAt",out var candle) && Timestamp("expiresAt",out var expires) &&
                created<=decision && decision<=now && candle<=decision && now<expires && now-candle<=TimeSpan.FromSeconds(3900);
            if(!usable)
            {
                kronos["agreement"]=null;kronos["status"]="KRONOS_UNAVAILABLE";
                kronos["reason"]="FORECAST_MISSING_STALE_OR_NOT_AVAILABLE_AT_DECISION";
            }
        }
    }
}
