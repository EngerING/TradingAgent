using System.Text.Json;
using System.Text.Json.Serialization;
using TradingAgent.Core;

namespace TradingAgent.Api;

public static class StockPaperForwardCommand
{
    public static async Task Run(RiskPolicy policy, bool supervisedTrial = false, bool r3 = false)
    {
        try
        {
            var raw=await Console.In.ReadToEndAsync();
            if(raw.Length>65536)throw new InvalidDataException();
            using var document=JsonDocument.Parse(raw);
            var r=document.RootElement;
            var options=new JsonSerializerOptions(Evidence.Json){NumberHandling=JsonNumberHandling.AllowReadingFromString};
            var account=r.GetProperty("account").Deserialize<AccountState>(options)!;
            var request=r.GetProperty("request").Deserialize<RiskRequest>(options)!;
            if(r3 && (r.GetProperty("experiment_profile").GetString()!=H40PaperR3Risk.Profile ||
                r.GetProperty("variant_version").GetString()!=H40PaperR3Risk.VariantVersion))
                throw new InvalidDataException();
            Func<RiskPolicy,AccountState,RiskRequest,DateTimeOffset,string,decimal,decimal,RiskEvaluation> evaluate=
                r3 ? H40PaperR3Risk.Evaluate : supervisedTrial ? H40PaperTrialRisk.Evaluate : StockPaperForwardRisk.Evaluate;
            var result=evaluate(policy,account,request,DateTimeOffset.UtcNow,
                r.GetProperty("strategy_version").GetString()!,
                r.GetProperty("cash").Deserialize<decimal>(options),r.GetProperty("reservations").Deserialize<decimal>(options));
            Console.WriteLine(JsonSerializer.Serialize(result,Evidence.Json));
        }
        catch(Exception)
        {
            Console.WriteLine("{\"allowed\":false,\"reason\":\"STOCK_FORWARD_RISK_PROTOCOL_REJECTED\",\"quantity\":0}");
            Environment.ExitCode=1;
        }
    }
}
