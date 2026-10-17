using System.Text.Json;
using Npgsql;
using TradingAgent.Infrastructure;
using TradingAgent.Core;
namespace TradingAgent.Api;
public static class ExploratoryCommand
{
    public static async Task Run()
    {
        try
        {
            var cs=Environment.GetEnvironmentVariable("TRADING_LAB_DB")??throw new InvalidDataException();
            var ep=new NpgsqlConnectionStringBuilder(cs);
            if(ep.Host!="127.0.0.1" || ep.Database!="postgres" || !((ep.Port==55433 && ep.Username=="paper_lab_app") || (ep.Port==55432 && ep.Username=="trading_test")))throw new InvalidDataException();
            var raw=await Console.In.ReadToEndAsync();if(raw.Length>8000000)throw new InvalidDataException();using var doc=JsonDocument.Parse(raw);var r=doc.RootElement;
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));
            ShadowEvent? e=r.TryGetProperty("event",out var value)?value.Deserialize<ShadowEvent>(Evidence.Json):null;
            var head=await new ExploratoryStore(cs).Execute(r.GetProperty("cohort").GetString()!,e,timeout.Token);
            var conflicts=await new ExploratoryStore(cs).Conflicts(r.GetProperty("cohort").GetString()!,timeout.Token);
            Console.WriteLine(JsonSerializer.Serialize(new{head.Revision,head.Hash,head.Payload,conflicting_cohorts=conflicts},Evidence.Json));
        }
        catch(Exception){Console.WriteLine("{\"error\":\"EXPLORATORY_POSTGRES_UNAVAILABLE_OR_CONFLICT\"}");Environment.ExitCode=1;}
    }
}
