using System.Text.Json;
using System.Text.Json.Nodes;
using TradingAgent.Core;
namespace TradingAgent.Api;

public static class KronosChat
{
    public static JsonObject Respond(SolRequest request,JsonElement snapshot)
    {
        var k=snapshot.TryGetProperty("kronos",out var v)?v:JsonSerializer.SerializeToElement(new{status="KRONOS_UNAVAILABLE",last20=Array.Empty<object>(),calibration=new{sample_size=0,brier_score=(double?)null,calibration_error=(double?)null,buckets=Array.Empty<object>()},byRegime=Array.Empty<object>(),evaluation=(object?)null});
        var predictions=k.GetProperty("last20").EnumerateArray().Take(20).ToArray();var stats=k.GetProperty("calibration");
        object table=new{columns=new[]{"UTC","Timeframe","Raw TP","Calibrada","Estado","Régimen"},rows=predictions.Select(p=>new object[]{p.GetProperty("candle_timestamp"),p.GetProperty("timeframe"),p.GetProperty("raw_tp_frequency"),p.GetProperty("calibrated_probability"),p.GetProperty("calibration_state"),p.GetProperty("regime")}).ToArray()};
        if(request.Message.Contains("70",StringComparison.Ordinal) || request.Message.Contains("calibra",StringComparison.OrdinalIgnoreCase))
            table=new{columns=new[]{"Bucket","Muestra","Frecuencia prevista","TP observado"},rows=stats.GetProperty("buckets").EnumerateArray().Select(b=>new object[]{b.GetProperty("bucket"),b.GetProperty("samples"),b.GetProperty("average_probability"),b.GetProperty("observed_tp_rate")}).ToArray()};
        if(request.Message.Contains("régimen",StringComparison.OrdinalIgnoreCase) || request.Message.Contains("regimen",StringComparison.OrdinalIgnoreCase))
            table=new{columns=new[]{"Régimen","Muestra","Brier","Error calibración"},rows=k.GetProperty("byRegime").EnumerateArray().Select(g=>new object[]{g.GetProperty("regime"),g.GetProperty("sample_size"),g.GetProperty("brier_score"),g.GetProperty("calibration_error")}).ToArray()};
        if((request.Message.Contains("compara",StringComparison.OrdinalIgnoreCase) || request.Message.Contains("expected value",StringComparison.OrdinalIgnoreCase)) && k.TryGetProperty("evaluation",out var evaluation) && evaluation.ValueKind==JsonValueKind.Object && evaluation.TryGetProperty("benchmark",out var benchmark))
        {
            var rows=new List<object[]>();
            foreach(var profile in benchmark.GetProperty("profiles").EnumerateObject())
                foreach(var arm in new[]{"BASELINE_ACTUAL","BASELINE_PLUS_KRONOS"})
                {var m=profile.Value.GetProperty(arm);rows.Add([profile.Name,arm,m.GetProperty("trades"),m.GetProperty("net_pnl"),m.GetProperty("expectancy"),m.GetProperty("profit_factor"),m.GetProperty("maximum_drawdown")]);}
            table=new{columns=new[]{"Perfil","Comparador","Trades","P&L neto","Expectancy","PF","Drawdown"},rows=rows.ToArray()};
        }
        var latest=predictions.FirstOrDefault();
        var text="Kronos: "+k.GetProperty("status").GetString()+". Modo observación; frecuencia bruta no es probabilidad real calibrada. Sin evidencia económica fuera de muestra suficiente ni promoción Paper.";
        if(latest.ValueKind!=JsonValueKind.Undefined)text+=" Consenso: "+latest.GetProperty("consensus").GetProperty("consensus").GetString()+". "+latest.GetProperty("calibration_state").GetString()+".";
        return JsonSerializer.SerializeToNode(new{requestId=request.RequestId,status="LOCAL_EVIDENCE_ONLY",provider="DETERMINISTIC_JOURNAL",model=(string?)null,text,
            metrics=new[]{new{label="Brier",value=stats.GetProperty("brier_score"),format="number"},new{label="Calibration error",value=stats.GetProperty("calibration_error"),format="number"}},table,
            chart=new{title="Kronos: predicted vs observed TP rate",unit="probabilidad",series=new[]{new{name="Reliability",points=stats.GetProperty("buckets").EnumerateArray().Where(b=>b.GetProperty("samples").GetInt32()>0).Select(b=>new{at=b.GetProperty("average_probability").ToString(),value=b.GetProperty("observed_tp_rate")}).ToArray()}}},
            warnings=new[]{"RAW_KRONOS_TP_FREQUENCY no es confidence inventada. Sin autoridad para cambiar EV/RiskEngine/ExecutionGuard.","Baseline vs Kronos no demuestra mejora cuando faltan trades netos fuera de muestra. Prueba final sellada."},
            operationDetails=(object?)null,prediction=snapshot.GetProperty("prediction"),command=(object?)null,
            usage=new{inputTokens=0,outputTokens=0,estimatedCostUsd=0,reservedCostUsd=0}},Evidence.Json)!.AsObject();
    }
}
