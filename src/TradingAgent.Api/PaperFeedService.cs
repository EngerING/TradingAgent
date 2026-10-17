using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;

namespace TradingAgent.Api;

public sealed record PaperFeedConfiguration(bool Enabled,string AccountId,string PythonExecutable,string PythonRoot,int ClientId)
{
    public static PaperFeedConfiguration Load()
    {
        var enabled=Environment.GetEnvironmentVariable("IBKR_DATA_ENABLED")=="true";
        if(!enabled)return new(false,"","","",73);
        var account=Environment.GetEnvironmentVariable("IBKR_PAPER_ACCOUNT")??"";
        // DU/DUR validate syntax only; they never replace the manual environment checks.
        if(!System.Text.RegularExpressions.Regex.IsMatch(account,@"\ADU(?:R)?[0-9]+\z") ||
            Environment.GetEnvironmentVariable("IBKR_PAPER_ATTESTED")!="true" ||
            Environment.GetEnvironmentVariable("IBKR_READ_ONLY_ATTESTED")!="true" ||
            Environment.GetEnvironmentVariable("IBKR_VERIFIED_TWS_PORT")!="7497" ||
            (Environment.GetEnvironmentVariable("IBKR_PORT")??"7497")!="7497" ||
            (Environment.GetEnvironmentVariable("LIVE_TRADING")??"false").ToLowerInvariant()!="false")
            throw new InvalidOperationException("PAPER_READ_ONLY_CONFIGURATION_REQUIRED");
        var python=Environment.GetEnvironmentVariable("TRADING_PYTHON")??Path.GetFullPath(".venv/Scripts/python.exe");
        var root=Environment.GetEnvironmentVariable("TRADING_PYTHON_ROOT")??Path.GetFullPath("python");
        if(!File.Exists(python)||!File.Exists(Path.Combine(root,"trading_agent","paper_feed.py")))throw new InvalidOperationException("PAPER_FEED_NOT_INSTALLED");
        if(!int.TryParse(Environment.GetEnvironmentVariable("IBKR_CLIENT_ID")??"73",out var clientId)||clientId<1)throw new InvalidOperationException("INVALID_CLIENT_ID");
        var hash=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(account))).ToLowerInvariant()[..16];
        return new(true,"PAPER-"+hash,python,root,clientId);
    }
}

public sealed class PaperFeedService(PaperFeedConfiguration config,PostgresStore store,ILogger<PaperFeedService> logger) : BackgroundService
{
    private PaperConnection? current;
    private DateTimeOffset heartbeat;
    private readonly object gate=new();
    public bool Connected {get{lock(gate)return config.Enabled && current?.AccountVerified==true && current.State is "CONNECTED" or "DEGRADED" && DateTimeOffset.UtcNow-heartbeat<TimeSpan.FromSeconds(90);}}
    public object Status()
    {
        lock(gate)return new {mode="PAPER_TRADING",enabled=config.Enabled,connected=Connected,
            state=!config.Enabled?"DISABLED":Connected?current!.State:current?.State is "REJECTED" or "CONNECTING"?current.State:"DISCONNECTED",accountId=config.Enabled?config.AccountId:null,
            accountVerified=Connected,host="127.0.0.1",port=7497,clientId=config.ClientId,readOnly=true,
            liveEnabled=false,ordersSupported=false,serverVersion=current?.ServerVersion,sdkVersion=current?.SdkVersion,
            lastHeartbeat=heartbeat==default?(DateTimeOffset?)null:heartbeat,reason=current?.Reason};
    }
    private void SetStatus(PaperConnection value,DateTimeOffset at){lock(gate){current=value;heartbeat=at;}}

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if(!config.Enabled)return;
        var restartDelay=1;
        while(!stoppingToken.IsCancellationRequested)
        {
            using var process=new Process();
            process.StartInfo=new(config.PythonExecutable)
            {
                UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,
                RedirectStandardInput=true,WorkingDirectory=Path.GetDirectoryName(config.PythonRoot)!
            };
            process.StartInfo.ArgumentList.Add("-u");process.StartInfo.ArgumentList.Add("-m");process.StartInfo.ArgumentList.Add("trading_agent.paper_feed");
            // The collector does not receive database credentials or the operator's bearer token.
            var keep=new[]{"PATH","SystemRoot","TEMP","TMP"};
            var basic=process.StartInfo.Environment.Where(x=>keep.Contains(x.Key,StringComparer.OrdinalIgnoreCase)).ToArray();
            process.StartInfo.Environment.Clear();foreach(var pair in basic)process.StartInfo.Environment[pair.Key]=pair.Value;
            foreach(var name in new[]{"IBKR_PAPER_ACCOUNT","IBKR_PAPER_ATTESTED","IBKR_READ_ONLY_ATTESTED","IBKR_VERIFIED_TWS_PORT","IBKR_PORT","IBKR_CLIENT_ID"})
                process.StartInfo.Environment[name]=Environment.GetEnvironmentVariable(name);
            process.StartInfo.Environment["LIVE_TRADING"]="false";process.StartInfo.Environment["PYTHONPATH"]=config.PythonRoot;
            process.StartInfo.Environment["PYTHONIOENCODING"]="utf-8";
            Task? errors=null;bool rejected=false;string? rejectedReason=null;
            var started=DateTimeOffset.UtcNow;
            try
            {
                process.Start();errors=Drain(process.StandardError,stoppingToken);
                while(!stoppingToken.IsCancellationRequested)
                {
                    using var timeout=CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);timeout.CancelAfter(TimeSpan.FromSeconds(90));
                    var line=await process.StandardOutput.ReadLineAsync(timeout.Token);
                    if(line is null)break;
                    if(line.Length>2*1024*1024)throw new InvalidDataException("PAPER_FEED_TOO_LARGE");
                    var envelope=JsonSerializer.Deserialize<PaperEnvelope>(line,PaperData.Json)??throw new InvalidDataException("MISSING_PAPER_ENVELOPE");
                    await store.SavePaper(envelope,config.AccountId,DateTimeOffset.UtcNow,stoppingToken);
                    if(envelope.Kind=="status")
                    {
                        var state=PaperData.Read<PaperConnection>(envelope.Data);SetStatus(state,envelope.ReceivedAt);
                        if(state.State=="REJECTED"){rejected=true;rejectedReason=state.Reason;break;}
                        if(state.State=="CONNECTED" && DateTimeOffset.UtcNow-started>TimeSpan.FromMinutes(2))restartDelay=1;
                    }
                }
            }
            catch(OperationCanceledException) when(stoppingToken.IsCancellationRequested) { }
            catch(Exception e){logger.LogWarning("Paper feed unavailable: {Type}",e.GetType().Name);}
            finally
            {
                if(process.IdSafe())
                {
                    if(!process.HasExited)
                    {
                        try
                        {
                            await process.StandardInput.WriteLineAsync("shutdown");await process.StandardInput.FlushAsync();
                            using var shutdown=new CancellationTokenSource(TimeSpan.FromSeconds(20));await process.WaitForExitAsync(shutdown.Token);
                        }
                        catch(Exception){if(!process.HasExited)process.Kill(entireProcessTree:true);}
                    }
                    if(errors is not null)try{await errors;}catch(Exception e) when(e is OperationCanceledException or IOException){}
                }
                var state=new PaperConnection(rejected?"REJECTED":"DISCONNECTED",false,7497,config.ClientId,current?.ServerVersion,current?.SdkVersion??"unknown",true,false,false,rejected?rejectedReason??"UNAUTHORIZED_ACCOUNT":"FEED_STOPPED");
                SetStatus(state,DateTimeOffset.UtcNow);
                try
                {
                    var envelope=new PaperEnvelope("status",config.AccountId,DateTimeOffset.UtcNow,JsonSerializer.SerializeToElement(state,PaperData.Json));
                    using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));await store.SavePaper(envelope,config.AccountId,DateTimeOffset.UtcNow,timeout.Token);
                }
                catch(Exception e){logger.LogWarning("Paper status persistence unavailable: {Type}",e.GetType().Name);}
            }
            if(rejected)return; // account/permission rejection requires operator correction
            try{await Task.Delay(TimeSpan.FromSeconds(restartDelay),stoppingToken);}catch(OperationCanceledException){break;}
            restartDelay=Math.Min(60,restartDelay*2);
        }
    }
    private static async Task Drain(StreamReader reader,CancellationToken ct)
    {while(await reader.ReadLineAsync(ct) is not null){} } // SDK text may include sensitive identifiers
}

internal static class ProcessExtensions
{
    public static bool IdSafe(this Process p){try{_ = p.Id;return true;}catch(InvalidOperationException){return false;}}
}
