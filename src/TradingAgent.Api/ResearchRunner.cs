using System.Diagnostics;
using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;

namespace TradingAgent.Api;

public static class ResearchRunner
{
    public static async Task<JsonElement> Run(PostgresStore store,RiskPolicy policy,string account,string root,
        DateTimeOffset asOf,string calendarPath,string indicatorPath,CancellationToken ct=default,string? originalDirectory=null)
    {
        if((Environment.GetEnvironmentVariable("LIVE_TRADING")??"false")!="false")throw new InvalidOperationException("LIVE_DISABLED");
        var originals=await store.ResearchOriginals(account,ct);var stored=originals.ToDictionary(p=>p.Key,p=>p.Value.Length);
        var provenance=new Dictionary<string,string>{{"15","POSTGRESQL_NATIVE"},{"60","POSTGRESQL_NATIVE"},{"240","POSTGRESQL_NATIVE"}};
        var receipts=new Dictionary<string,object>();
        foreach(var minutes in new[]{60,240})
        {
            var path=Path.Combine(originalDirectory??Path.Combine(root,".local"),$"eurusd-history-{minutes}.received.json");
            if(!File.Exists(path))continue;
            var originalText=await File.ReadAllTextAsync(path,ct);
            using var received=JsonDocument.Parse(originalText);var data=received.RootElement;
            if(data.GetProperty("source").GetString()!="IBKR_TWS" || data.GetProperty("what_to_show").GetString()!="MIDPOINT" ||
                data.GetProperty("minutes").GetInt32()!=minutes)throw new InvalidDataException("INVALID_ORIGINAL_PROVENANCE");
            var rows=data.GetProperty("rows").EnumerateArray().Select(x=>x.Clone()).ToArray();
            if(rows.Length>10000)throw new InvalidDataException("ORIGINAL_DATASET_TOO_LARGE");
            var byTime=rows.ToDictionary(r=>DateTimeOffset.Parse(r.GetProperty("opened_at").GetString()!).ToUniversalTime());
            foreach(var retained in originals[minutes.ToString()])
            {
                var time=DateTimeOffset.Parse(retained.GetProperty("opened_at").GetString()!).ToUniversalTime();
                if(!byTime.TryGetValue(time,out var raw))throw new InvalidDataException("ORIGINAL_HISTORY_DOES_NOT_COVER_STORED_DATA");
                foreach(var field in new[]{"open","high","low","close"})
                    if(Number(raw.GetProperty(field))!=Number(retained.GetProperty(field)))throw new InvalidDataException("ORIGINAL_HISTORY_CONFLICT");
            }
            originals[minutes.ToString()]=rows;provenance[minutes.ToString()]="LOCAL_RECEIVED_HISTORY_MATCHED_AGAINST_POSTGRESQL";
            var receivedAt=DateTimeOffset.Parse(data.GetProperty("received_at").GetString()!).ToUniversalTime();
            if(receivedAt>asOf)throw new InvalidDataException("ORIGINAL_RECEIPT_AFTER_RESEARCH_CUTOFF");
            receipts[minutes.ToString()]=new {receivedAt,sha256=Evidence.Hash(originalText),source="IBKR_TWS",availability="RECEIVED"};
        }
        using var calendar=JsonDocument.Parse(await File.ReadAllTextAsync(calendarPath,ct));
        using var parameters=JsonDocument.Parse(await File.ReadAllTextAsync(indicatorPath,ct));
        var archivePath=Environment.GetEnvironmentVariable("RESEARCH_ARCHIVE_PATH");
        using var archive=archivePath is null?null:JsonDocument.Parse(await File.ReadAllTextAsync(archivePath,ct));
        if(archive is not null && archive.RootElement.GetProperty("account_id").GetString()!=account)throw new InvalidDataException("UNAUTHORIZED_ARCHIVE_SOURCE");
        var input=archive is null?JsonSerializer.SerializeToElement(new {instrument="EUR/USD",source="IBKR_TWS",what_to_show="MIDPOINT",
            as_of=asOf.ToUniversalTime(),calendar=calendar.RootElement,indicators=parameters.RootElement,originals,original_receipts=receipts}):
            JsonSerializer.SerializeToElement(new {instrument="EUR/USD",source="IBKR_TWS",what_to_show="MIDPOINT",as_of=asOf.ToUniversalTime(),
                indicators=parameters.RootElement,archive=archive.RootElement,expected_account=account,
                validation_start=Environment.GetEnvironmentVariable("RESEARCH_VALIDATION_START")??throw new InvalidDataException("VALIDATION_START_REQUIRED")});
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(120));
        using var process=new Process {StartInfo=new(Path.Combine(root,".venv","Scripts","python.exe")) {
            UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=root}};
        process.StartInfo.ArgumentList.Add("-m");process.StartInfo.ArgumentList.Add(archive is null?"trading_agent.research_analysis":"trading_agent.research_extension");
        var basic=process.StartInfo.Environment.Where(p=>new[]{"PATH","SystemRoot","TEMP","TMP"}.Contains(p.Key,StringComparer.OrdinalIgnoreCase)).ToArray();
        process.StartInfo.Environment.Clear();foreach(var pair in basic)process.StartInfo.Environment[pair.Key]=pair.Value;
        process.StartInfo.Environment["PYTHONPATH"]=Path.Combine(root,"python");process.StartInfo.Environment["PYTHONIOENCODING"]="utf-8";
        process.Start();
        var output=process.StandardOutput.ReadToEndAsync(timeout.Token);var errors=process.StandardError.ReadToEndAsync(timeout.Token);
        string text;
        try
        {
            await process.StandardInput.WriteAsync(input.GetRawText());process.StandardInput.Close();
            await process.WaitForExitAsync(timeout.Token);text=await output;await errors;
            if(process.ExitCode!=0 || text.Length>(archive is null?32:64)*1024*1024)throw new InvalidDataException("RESEARCH_PROCESS_FAILED");
        }
        finally {if(!process.HasExited)process.Kill(entireProcessTree:true);}
        using var result=JsonDocument.Parse(text);var analysis=result.RootElement;
        if(analysis.GetProperty("schema_version").GetInt32()!=1 || analysis.GetProperty("instrument").GetString()!="EUR/USD" ||
            analysis.GetProperty("live_enabled").GetBoolean() || analysis.GetProperty("orders_supported").GetBoolean() || analysis.GetProperty("openai_enabled").GetBoolean())
            throw new InvalidDataException("INVALID_RESEARCH_RESULT");
        var config=analysis.GetProperty("config_hash").GetString()!;
        var signals=analysis.GetProperty("candidates").Deserialize<ResearchSignal[]>(PaperData.Json)!;
        var exits=analysis.GetProperty("exit_signals").Deserialize<ResearchExit[]>(PaperData.Json)!;
        var bars=analysis.GetProperty("normalized").GetProperty("15").Deserialize<PaperCandle[]>(PaperData.Json)!;
        var strategies=analysis.GetProperty("strategies").EnumerateArray().Select(s=>new StrategyVersion(
            "research-d-"+s.GetProperty("id").GetString()+"-"+config[..12],s.GetProperty("name").GetString()!,1,"EUR/USD","15,60,240",
            s.GetProperty("entry_rule").GetString()!,s.GetProperty("exit_rule").GetString()!, .00005m,.00005m,100,
            "RESEARCH_ONLY_NO_EXECUTION_COSTS_REQUIRED",s.GetRawText())).ToArray();
        var backtests=new[]{"trend","pullback","mean_reversion"}.Select(s=>ResearchSimulation.Run(s,bars,signals,exits,policy)).ToArray();
        ResearchPartition[]? partitions=null;
        if(archive is not null)
        {
            var split=analysis.GetProperty("extension").GetProperty("split");
            partitions=ResearchValidation.Evaluate(bars,signals,exits,policy,DateTimeOffset.Parse(split.GetProperty("start").GetString()!),
                DateTimeOffset.Parse(split.GetProperty("validation_start").GetString()!),DateTimeOffset.Parse(split.GetProperty("end").GetString()!));
        }
        var id=Evidence.Hash("research-d-v1|"+account+"|"+analysis.GetProperty("dataset_hash").GetString()+"|"+config+"|"+asOf.ToUniversalTime().ToString("O"));
        var summary=JsonSerializer.SerializeToElement(new {schemaVersion=1,runId=id,instrument="EUR/USD",asOf,
            storedNativeCounts=stored,originalProvenance=provenance,originalReceipts=receipts,analysis,backtests,
            solContext=new {instrument="EUR/USD",timeframes=analysis.GetProperty("latest"),
                dataQuality=analysis.GetProperty("quality"),strategies=analysis.GetProperty("strategies"),backtests,
                risk=new{capital=100,lossAllowance=20,maximumRisk=policy.MaximumRisk},openaiEnabled=false},
            liveEnabled=false,ordersSupported=false,openaiEnabled=false},Evidence.Json);
        JsonElement? validationEvidence=null;
        if(partitions is not null)
        {
            var testPath=Path.Combine(root,"artifacts","test-results","research-extension-evidence.json");
            using var testReport=File.Exists(testPath)?JsonDocument.Parse(await File.ReadAllTextAsync(testPath,ct)):null;
            var tests=testReport?.RootElement.Clone()??JsonSerializer.SerializeToElement(new{status="NOT_RECORDED"});
            var extension=JsonSerializer.SerializeToElement(new {schemaVersion=1,runId=id,partitions,
                uncertainty="UNKNOWN_ACCOUNT_CLOSING_FEES_SLIPPAGE_AND_ODD_LOT_EXECUTION; NO_STATISTICAL_SIGNIFICANCE_CLAIM",
                analysisExtension=analysis.GetProperty("extension"),
                solContext=new{instrument="EUR/USD",sample=analysis.GetProperty("extension").GetProperty("split"),
                    quality=analysis.GetProperty("quality"),costs=analysis.GetProperty("extension").GetProperty("cost_evidence"),
                    conditions=analysis.GetProperty("extension").GetProperty("conditions"),partitions,
                    indicators=analysis.GetProperty("latest"),risk=new{capital=100,lossAllowance=20},
                    tests,openaiEnabled=false},
                liveEnabled=false,ordersSupported=false,openaiEnabled=false},Evidence.Json);
            validationEvidence=extension;
            summary=JsonSerializer.SerializeToElement(new{research=summary,validation=extension},Evidence.Json);
        }
        await store.SaveResearch(id,account,asOf,input,summary,strategies,backtests,ct,validationEvidence);
        return summary;
    }
    private static decimal Number(JsonElement value)=>value.ValueKind==JsonValueKind.String?
        decimal.Parse(value.GetString()!,System.Globalization.CultureInfo.InvariantCulture):value.GetDecimal();
}
