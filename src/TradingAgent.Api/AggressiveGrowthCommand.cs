using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;

namespace TradingAgent.Api;

public static class AggressiveGrowthCommand
{
    public static async Task Run()
    {
        try
        {
            var buffer=new char[8_000_001];var length=0;
            while(length<buffer.Length)
            {
                var n=await Console.In.ReadAsync(buffer.AsMemory(length));if(n==0)break;length+=n;
            }
            if(length==buffer.Length)throw new InvalidDataException("R20_INPUT_LIMIT");
            using var doc=JsonDocument.Parse(new string(buffer,0,length));var request=doc.RootElement;
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(8));
            var result=await new AggressiveGrowthStore(Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidDataException()).Execute(
                request.GetProperty("experiment").GetString()!,request.GetProperty("event").ValueKind==JsonValueKind.Null?null:request.GetProperty("event").Deserialize<ShadowEvent>(Evidence.Json),timeout.Token);
            Console.WriteLine(JsonSerializer.Serialize(result,Evidence.Json));
        }
        catch(Exception){Console.WriteLine("{\"error\":\"R20_JOURNAL_UNAVAILABLE_OR_CONFLICT\"}");Environment.ExitCode=1;}
    }
}
