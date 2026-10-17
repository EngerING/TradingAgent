using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.ResearchLab;

try
{
    var input=await Console.In.ReadToEndAsync();if(input.Length>5*1024*1024)throw new ArgumentException("RESEARCH_INPUT_TOO_LARGE");
    using var doc=JsonDocument.Parse(input);var r=doc.RootElement;
    if(r.GetProperty("environment").GetString()!="SIMULATION" || r.GetProperty("capital").GetDecimal()!=100 ||
        r.GetProperty("lossAllowance").GetDecimal()!=20 || r.GetProperty("exposure").GetDecimal()!=1 ||
        r.GetProperty("liveEnabled").GetBoolean() || r.GetProperty("executionAuthorized").GetBoolean())
        throw new ArgumentException("ISOLATED_RESEARCH_SCOPE_REQUIRED");
    var options=new JsonSerializerOptions(Evidence.Json){NumberHandling=System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString};
    var bars=r.GetProperty("bars").Deserialize<PaperCandle[]>(options)!;
    var signals=r.GetProperty("signals").Deserialize<ResearchSignal[]>(options)!;
    var exits=r.GetProperty("exits").Deserialize<ResearchExit[]>(options)!;
    var costs=r.GetProperty("costs").Deserialize<ResearchCosts>(options)!;var strategy=r.GetProperty("strategy").GetString()!;
    if(r.TryGetProperty("researchMode",out var mode))
    {
        if(mode.GetString()!="EXPOSURE_SWEEP")throw new ArgumentException("UNKNOWN_RESEARCH_MODE");
        var assumptions=r.GetProperty("marginAssumptions").Deserialize<ExposureAssumptions>(options)!;
        assumptions.Validate(.15m);
        if(r.TryGetProperty("minimumOnly",out var minimumOnly) && minimumOnly.GetBoolean())
            Console.WriteLine(JsonSerializer.Serialize(signals.Where(s=>s.EntryAt is not null && s.Reasons.Length==0)
                .Select(s=>new {signal=s,minimum=ExposureStudy.Minimum(s,costs,assumptions)}),Evidence.Json));
        else
            Console.WriteLine(JsonSerializer.Serialize(ExposureAssumptions.Exposures.SelectMany(exposure=>
                ExposureAssumptions.Rates.Select(rate=>ProgressiveRiskSimulation.Run(strategy,bars,signals,exits,costs,rate,
                    assumptions with {Exposure=exposure}))),Evidence.Json));
    }
    else
        Console.WriteLine(JsonSerializer.Serialize(ResearchScope.Rates.Select(rate=>
            ProgressiveRiskSimulation.Run(strategy,bars,signals,exits,costs,rate)),Evidence.Json));
}
catch(Exception error)
{
    var reason=error is ArgumentException or InvalidOperationException?error.Message:"RESEARCH_FAILED";
    if(!System.Text.RegularExpressions.Regex.IsMatch(reason,"^[A-Z][A-Z0-9_]{1,127}$"))reason="RESEARCH_FAILED";
    Console.WriteLine(JsonSerializer.Serialize(new {error="SIMULATION_REJECTED",reason,ordersSent=0,liveEnabled=false}));
    Environment.ExitCode=1;
}
