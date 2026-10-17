param([string]$AsOf=[DateTimeOffset]::UtcNow.ToString('o'),[string]$CalendarPath,[string]$IndicatorPath)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
$names=@('TRADING_DB','TRADING_DB_AUTO_MIGRATE','RESEARCH_SOURCE_ACCOUNT','RESEARCH_ROOT','RESEARCH_AS_OF','RESEARCH_CALENDAR_PATH',
    'RESEARCH_INDICATOR_PATH','IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_VERIFIED_TWS_PORT','IBKR_PORT','IBKR_DATA_ENABLED','LIVE_TRADING')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name)}
$socket=New-Object Net.Sockets.TcpClient
try {$pending=$socket.ConnectAsync('127.0.0.1',55433);$null=$pending.Wait(1000);$alreadyRunning=$socket.Connected}
catch {$alreadyRunning=$false} finally {$socket.Dispose()}
$started=$false
try {
    & (Join-Path $repoRoot 'scripts/paper-identity.ps1') -Action Load
    $hasher=[Security.Cryptography.SHA256]::Create()
    try {$env:RESEARCH_SOURCE_ACCOUNT='PAPER-'+([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($env:IBKR_PAPER_ACCOUNT))).Replace('-','').ToLowerInvariant()).Substring(0,16)}
    finally {$hasher.Dispose()}
    # The offline runner and Python worker do not need a broker identity or attestations.
    foreach($name in @('IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_DATA_ENABLED')) {[Environment]::SetEnvironmentVariable($name,$null)}
    $env:LIVE_TRADING='false';$env:RESEARCH_ROOT=$repoRoot;$env:RESEARCH_AS_OF=([DateTimeOffset]::Parse($AsOf)).ToUniversalTime().ToString('o')
    $env:RESEARCH_CALENDAR_PATH=if($CalendarPath){$CalendarPath}else{Join-Path $repoRoot 'config/forex-sessions.json'}
    $env:RESEARCH_INDICATOR_PATH=if($IndicatorPath){$IndicatorPath}else{Join-Path $repoRoot 'config/research-indicators.json'}
    & (Join-Path $repoRoot 'scripts/paper-database.ps1') -Action Start
    $started=-not $alreadyRunning
    $dll=Join-Path $repoRoot 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'
    $json=& dotnet $dll --research
    if($LASTEXITCODE -ne 0){throw 'MARKET_RESEARCH_FAILED'}
    $result=($json | Out-String) | ConvertFrom-Json
    $out=Join-Path $repoRoot 'artifacts/research';New-Item -ItemType Directory -Force -Path $out | Out-Null
    ($json | Out-String) | Set-Content -LiteralPath (Join-Path $out ($result.runId+'.json')) -Encoding UTF8
    $result.solContext | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath (Join-Path $out ($result.runId+'.sol-context.json')) -Encoding UTF8
    [pscustomobject]@{runId=$result.runId;storedNativeCounts=$result.storedNativeCounts;usableCounts=$result.analysis.usable_counts;
        latest=$result.analysis.latest;signalCounts=$result.analysis.signal_counts;
        evaluations=@($result.backtests | ForEach-Object {[pscustomobject]@{strategy=$_.strategyId;status=$_.status;
            signals=$_.assessments.Count;accepted=@($_.assessments | Where-Object accepted).Count;trades=$_.trades.Count;netProfit=$_.netProfit;
            finalEquity=$_.finalEquity;consumedLoss=$_.consumedLoss}});
        report=(Join-Path $out ($result.runId+'.json'));liveEnabled=$false;ordersSupported=$false;openaiEnabled=$false} | ConvertTo-Json -Depth 9
} finally {
    if($started){& (Join-Path $repoRoot 'scripts/paper-database.ps1') -Action Stop}
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name])}
}
