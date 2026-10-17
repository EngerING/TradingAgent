using System.Text.Json;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
namespace TradingAgent.Api;

// Internal stdin only. No broker connection and no authorization capability.
public static class FordDiagnosticEvidenceCommand
{
    public static async Task Run()
    {
        try
        {
            var cs=Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidDataException();
            var endpoint=new NpgsqlConnectionStringBuilder(cs);
            if(endpoint.Host!="127.0.0.1" || endpoint.Database!="postgres" ||
               !((endpoint.Port==55433 && endpoint.Username=="paper_lab_app") ||
                 (endpoint.Port==55432 && endpoint.Username=="trading_test")))throw new InvalidDataException();
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>16*1024*1024)throw new InvalidDataException();
            using var doc=JsonDocument.Parse(raw);var r=doc.RootElement;
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var head=await new PostgresStore(cs).AppendFordDiagnostic(r.GetProperty("trial").GetString()!,
                r.GetProperty("binding").GetString()!,r.GetProperty("scope").GetString()!,
                r.GetProperty("events").Deserialize<FordDiagnosticEvent[]>(Evidence.Json)!,timeout.Token);
            Console.WriteLine(JsonSerializer.Serialize(head,Evidence.Json));
        }
        catch(Exception){Console.WriteLine("{\"error\":\"FORD_DIAGNOSTIC_POSTGRES_UNAVAILABLE_OR_CONFLICT\"}");Environment.ExitCode=1;}
    }
}
