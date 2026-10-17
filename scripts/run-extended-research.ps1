param([string]$ValidationStart='2026-08-03T00:00:00Z',[string]$AsOf=[DateTimeOffset]::UtcNow.ToString('o'))
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
$names=@('TRADING_DB','TRADING_DB_AUTO_MIGRATE','RESEARCH_SOURCE_ACCOUNT','RESEARCH_ROOT','RESEARCH_AS_OF','RESEARCH_ARCHIVE_PATH','RESEARCH_VALIDATION_START',
    'IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_VERIFIED_TWS_PORT','IBKR_PORT','IBKR_DATA_ENABLED','LIVE_TRADING')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name)}
$started=$false
try {
    & (Join-Path $root 'scripts/paper-identity.ps1') -Action Load
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$env:RESEARCH_SOURCE_ACCOUNT='PAPER-'+([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($env:IBKR_PAPER_ACCOUNT))).Replace('-','').ToLowerInvariant()).Substring(0,16)}
    finally {$hash.Dispose()}
    foreach($name in @('IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_DATA_ENABLED')){[Environment]::SetEnvironmentVariable($name,$null)}
    $archivePath=Join-Path $root '.local/research-history/manifest.json'
    if(Test-Path -LiteralPath (Join-Path $root '.local/research-history/collector.lock')){throw 'HISTORY_COLLECTION_IN_PROGRESS'}
    if(-not(Test-Path -LiteralPath $archivePath)){throw 'HISTORY_ARCHIVE_MISSING'}
    $env:RESEARCH_ARCHIVE_PATH=$archivePath;$env:RESEARCH_VALIDATION_START=([DateTimeOffset]::Parse($ValidationStart)).ToUniversalTime().ToString('o')
    $env:RESEARCH_ROOT=$root;$env:RESEARCH_AS_OF=([DateTimeOffset]::Parse($AsOf)).ToUniversalTime().ToString('o');$env:LIVE_TRADING='false'
    $socket=New-Object Net.Sockets.TcpClient
    try {$pending=$socket.ConnectAsync('127.0.0.1',55433);$null=$pending.Wait(1000);$alreadyRunning=$socket.Connected}
    catch {$alreadyRunning=$false} finally {$socket.Dispose()}
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Start
    $started=-not $alreadyRunning
    $json=& dotnet (Join-Path $root 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll') --research
    if($LASTEXITCODE -ne 0){throw 'EXTENDED_RESEARCH_FAILED'}
    $result=($json | Out-String) | ConvertFrom-Json
    $out=Join-Path $root 'artifacts/research';New-Item -ItemType Directory -Force -Path $out | Out-Null
    $id=$result.research.runId
    ($json | Out-String) | Set-Content -LiteralPath (Join-Path $out ($id+'.extended.json')) -Encoding UTF8
    $result.validation.solContext | ConvertTo-Json -Depth 70 | Set-Content -LiteralPath (Join-Path $out ($id+'.extended.sol-context.json')) -Encoding UTF8
    $partitions=@(foreach($partition in $result.validation.partitions){
        $evaluations=@(foreach($evaluation in $partition.verifiableEvaluations){
            [pscustomobject]@{strategy=$evaluation.strategyId;signals=$evaluation.assessments.Count;
                accepted=@($evaluation.assessments | Where-Object accepted).Count;net=$evaluation.netProfit}
        })
        [pscustomobject]@{role=$partition.datasetRole;evaluations=$evaluations}
    })
    [pscustomobject]@{runId=$id;quality=@($result.research.analysis.quality.PSObject.Properties | ForEach-Object {[pscustomobject]@{timeframe=$_.Name;original=$_.Value.original_count;normalized=$_.Value.included_count;gaps=$_.Value.missing_expected_openings.Count}});
        signals=$result.research.analysis.signal_counts;costs=$result.research.analysis.extension.cost_evidence;
        partitions=$partitions;
        liveEnabled=$false;ordersSupported=$false;openaiEnabled=$false} | ConvertTo-Json -Depth 8
} finally {
    if($started){& (Join-Path $root 'scripts/paper-database.ps1') -Action Stop}
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name])}
}
