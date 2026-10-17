using System.Text.Json;
using TradingAgent.Infrastructure;
namespace TradingAgent.Api;
public static class KronosCommand
{
    public static async Task Run()
    {
        try
        {
            var cs=Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidDataException();
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>300000)throw new InvalidDataException();
            using var d=JsonDocument.Parse(raw);var p=d.RootElement;var store=new KronosStore(cs);using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
            if(p.GetProperty("action").GetString()=="append")
            {await store.Append(p.GetProperty("id").GetString()!,p.GetProperty("kind").GetString()!,p.GetProperty("payload").GetString()!,p.GetProperty("hash").GetString()!,timeout.Token);Console.WriteLine("{\"stored\":true}");}
            else if(p.GetProperty("action").GetString()=="read")Console.WriteLine(JsonSerializer.Serialize(new{events=await store.Read(timeout.Token),source=await store.Source(p.TryGetProperty("study",out var s)?s.GetString():null,timeout.Token)}));
            else throw new InvalidDataException();
        }
        catch(Exception){Console.WriteLine("{\"error\":\"KRONOS_POSTGRES_UNAVAILABLE_OR_CONFLICT\"}");Environment.ExitCode=1;}
    }
}
