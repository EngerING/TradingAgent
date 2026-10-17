using System.Text.Json;
using TradingAgent.Core;

namespace TradingAgent.Api;

// Offline stdin protocol. No database, secret, broker connection or profile activation.
public static class PaperRiskProfileCommand
{
    public static async Task Run(RiskPolicy conservative)
    {
        try
        {
            var raw = await Console.In.ReadToEndAsync();
            if (raw.Length > 1024 * 1024) throw new ArgumentException();
            var input = JsonSerializer.Deserialize<StudyInput>(raw,Evidence.Json) ?? throw new ArgumentException();
            if(input.Account is null || input.Request is null) throw new ArgumentException();
            Console.WriteLine(JsonSerializer.Serialize(PaperRiskProfile.Study(input.Profile,conservative,
                input.Account,input.Request,input.AsOf,input.Broker,input.Mode,input.LiveEnabled),Evidence.Json));
        }
        catch (Exception e) when (e is ArgumentException or JsonException or InvalidOperationException)
        { Console.WriteLine("{\"error\":\"PAPER_PROFILE_STUDY_FAILED\",\"active\":false,\"executionAuthorized\":false}"); Environment.ExitCode=1; }
    }

    private sealed record StudyInput(string Profile, AccountState Account, RiskRequest Request,
        DateTimeOffset AsOf, string Broker, string Mode, bool LiveEnabled);
}
