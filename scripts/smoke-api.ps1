$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
if (-not $env:TRADING_DB) { throw 'Set TRADING_DB to the disposable test database' }
$env:TRADING_ADMIN_TOKEN=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
$headers=@{Authorization='Bearer '+$env:TRADING_ADMIN_TOKEN}
$dll=Join-Path $repoRoot 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'
$local=Join-Path $repoRoot '.local'
New-Item -ItemType Directory -Force -Path $local | Out-Null
function Start-TestApi {
    $proc=Start-Process -FilePath 'dotnet' -ArgumentList ('"'+$dll+'"') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $local 'api-test.log') -RedirectStandardError (Join-Path $local 'api-test.err')
    for ($i=0;$i -lt 50;$i++) {
        if ($proc.HasExited) { throw 'API exited; inspect .local/api-test.err' }
        try { $null=Invoke-RestMethod 'http://127.0.0.1:5080/health'; return $proc } catch { Start-Sleep -Milliseconds 200 }
    }
    Stop-Process -Id $proc.Id
    throw 'API startup timeout'
}
function CallApi($path,$body) {
    Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:5080'+$path) -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 20)
}
function Check($condition,$message) { if(-not $condition){throw $message} }
$proc=$null
try {
    $proc=Start-TestApi
    $health=Invoke-RestMethod 'http://127.0.0.1:5080/health'
    Check (-not $health.liveEnabled -and -not $health.ordersSupported -and -not $health.aiEnabled) 'Unsafe health state'
    try { $null=Invoke-RestMethod 'http://127.0.0.1:5080/policy';throw 'Authentication unexpectedly succeeded' }
    catch { if($_.Exception.Response.StatusCode.value__ -ne 401){throw} }
    $account='SIM-SMOKE-'+[guid]::NewGuid().ToString('N')
    $null=CallApi '/simulation/accounts' @{accountId=$account;equity=100}
    $strategy=CallApi '/simulation/strategies' @{strategyId=$account;name='Smoke';version=1;instrument='EUR/USD';timeframes='15,60,240';entryRule='deterministic test';exitRule='stop';stopDistance=.001;takeProfitDistance=.002;maxExposure=1000;executionRequirements='simulation';parametersJson='{}'}
    $decisionId=[guid]::NewGuid().ToString('N')
    $command=@{id=$decisionId;accountId=$account;strategyHash=$strategy.hash;session='London';features=@{rsi=50};marketBeforeJson='{}';request=@{instrument='EUR/USD';side='BUY';bid=1.0999;ask=1.1001;stop=1.099;quoteToAccountFx=1;multiplier=1;minQuantity=1;quantityStep=1;marginRate=1;availableMargin=100;commissionFixedRoundTrip=0;commissionPerUnitRoundTrip=0;slippagePerUnit=.0001;adverseGapPerUnit=.0002;marketAt=[DateTimeOffset]::UtcNow.ToString('o')}}
    $command.request.execution=@{source='synthetic-api-test';environment='SIMULATION';mode='SIMULATED';at=[DateTimeOffset]::UtcNow.ToString('o');openingCommission=0;closingCommission=0;costsReliable=$true;marginReliable=$true;contractReliable=$true;brokerPermitsEntry=$true;quoteStatus='SIMULATED'}
    $command.id=[guid]::NewGuid().ToString('N');$command.request.execution.closingCommission=$null
    $incomplete=CallApi '/simulation/decisions' $command
    Check ($incomplete.evaluation.reason -eq 'EXECUTION_DATA_INCOMPLETE' -and -not $incomplete.evaluation.allowed) 'Unknown closing commission was accepted'
    $command.id=$decisionId;$command.request.execution.closingCommission=0
    $first=CallApi '/simulation/decisions' $command
    Check $first.evaluation.allowed 'Simulation rejected unexpectedly'
    Check ($first.evaluation.feasibility.productionValidation -eq 'UNVALIDATED_FOR_PRODUCTION') 'Missing real account evidence was accepted as production validation'
    $again=CallApi '/simulation/decisions' $command
    Check ($first.commandHash -eq $again.commandHash) 'Idempotency failed'
    $valuation=@{accountId=$account;eventId=[guid]::NewGuid().ToString('N');decisionId=$decisionId;unrealizedNetPnl=-.05;openCosts=.002;remainingRisk=.05}
    $null=CallApi '/simulation/valuation' $valuation
    $null=CallApi '/simulation/valuation' $valuation
    $valued=Invoke-RestMethod ('http://127.0.0.1:5080/simulation/accounts/'+$account) -Headers $headers
    Check ($valued.equity -eq 99.95 -and $valued.reservationId -eq $decisionId -and $valued.capital.unrealizedNetPnl -eq -.05) 'Floating valuation lost accounting or reservation'
    $null=CallApi '/simulation/settle' @{accountId=$account;decisionId=$decisionId;netPnl=-.1;observedCosts=.01;marketAfterJson='{}'}
    $episodes=Invoke-RestMethod ('http://127.0.0.1:5080/experiences/'+$account) -Headers $headers
    Check ($episodes[0].simulatedPnl -eq -.1) 'Experience recovery failed'
    $null=CallApi ('/safety/stop/'+$account) @{}
    Stop-Process -Id $proc.Id; $proc.WaitForExit();$proc=$null
    $proc=Start-TestApi
    $state=Invoke-RestMethod ('http://127.0.0.1:5080/simulation/accounts/'+$account) -Headers $headers
    Check ($state.halts -contains 'EMERGENCY_STOP') 'Restart cleared emergency stop'
    Check ($state.equity -eq 99.9) 'Restart lost equity'
    Check ($state.capital.initialCapital -eq 100 -and $state.capital.realizedNetPnl -eq -.1 -and $state.capital.realizedCosts -eq .01 -and $state.capital.consumedLoss -eq .1) 'Restart lost virtual capital accounting'
    Write-Output 'API smoke passed: auth, Live disabled, strategy, risk, replay, settlement, experience, emergency stop and recovery after process restart.'
} finally {
    if($proc -and -not $proc.HasExited){Stop-Process -Id $proc.Id}
    Remove-Item Env:TRADING_ADMIN_TOKEN -ErrorAction SilentlyContinue
}
