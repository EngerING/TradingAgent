using System.Text.Json;
using System.Text.Json.Serialization;
using TradingAgent.Core;
namespace TradingAgent.Api;
public static class FordDiagnosticCommand
{
    public static async Task Run(RiskPolicy policy)
    {
        try
        {
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>65536)throw new InvalidDataException();
            using var d=JsonDocument.Parse(raw);var r=d.RootElement;
            var o=new JsonSerializerOptions(Evidence.Json){NumberHandling=JsonNumberHandling.AllowReadingFromString};
            var result=FordDiagnosticRisk.Evaluate(policy,r.GetProperty("account").Deserialize<AccountState>(o)!,
                r.GetProperty("request").Deserialize<RiskRequest>(o)!,DateTimeOffset.UtcNow,
                r.GetProperty("diagnostic_scope").GetString()!,r.GetProperty("cash").Deserialize<decimal>(o),
                r.GetProperty("reservations").Deserialize<decimal>(o));
            Console.WriteLine(JsonSerializer.Serialize(result,Evidence.Json));
        }
        catch(Exception){Console.WriteLine("{\"allowed\":false,\"reason\":\"FORD_DIAGNOSTIC_RISK_PROTOCOL_REJECTED\"}");Environment.ExitCode=1;}
    }
}
