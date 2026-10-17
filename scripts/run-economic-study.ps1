$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
$names=@('ECONOMIC_STUDY_ROOT','TRADING_POLICY_PATH')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name)}
try {
    $env:ECONOMIC_STUDY_ROOT=$root
    $env:TRADING_POLICY_PATH=Join-Path $root 'config/research-policy.json'
    $json=& dotnet (Join-Path $root 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll') --economic-study
    if($LASTEXITCODE -ne 0){throw 'ECONOMIC_STUDY_FAILED'}
    $report=($json | Out-String) | ConvertFrom-Json
    $out=Join-Path $root 'artifacts/economics';New-Item -ItemType Directory -Force -Path $out | Out-Null
    $name=([DateTimeOffset]::Parse($report.asOf)).UtcDateTime.ToString('yyyyMMddTHHmmssfffffffZ')+'.json'
    $json | Set-Content -LiteralPath (Join-Path $out $name) -Encoding UTF8
    $report.publicFeeLowerBoundComparisons | ForEach-Object { $_.result } |
        Select-Object quantity,status,nominalExposure,totalCosts,knownCostLowerBound,potentialGrossProfit,potentialNetProfit,breakEvenPips,effectiveBudget,reasons |
        ConvertTo-Json -Depth 4
    Write-Output ('Informe local: artifacts/economics/'+$name+'; cero ordenes; sin conexion TWS.')
} finally {foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name])}}
