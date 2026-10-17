using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
namespace TradingAgent.Api;
public static class PriceRiskCommand
{
    public static async Task Run()
    {
        try
        {
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>4_000_000)throw new InvalidDataException();
            using var doc=JsonDocument.Parse(raw);var r=doc.RootElement;
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(8));
            var result=await new PriceRiskStore(Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidDataException()).Execute(r.GetProperty("experiment").GetString()!,r.GetProperty("event").ValueKind==JsonValueKind.Null?null:r.GetProperty("event").Deserialize<ShadowEvent>(Evidence.Json),timeout.Token);
            Console.WriteLine(JsonSerializer.Serialize(result,Evidence.Json));
        }
        catch(Exception){Console.WriteLine("{\"error\":\"PRICE_RISK_JOURNAL_UNAVAILABLE_OR_CONFLICT\"}");Environment.ExitCode=1;}
    }
}
