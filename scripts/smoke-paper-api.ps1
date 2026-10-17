param([switch]$RealTws)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$names=@('TRADING_DB','TRADING_DB_AUTO_MIGRATE','TRADING_ADMIN_TOKEN','IBKR_DATA_ENABLED','IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED',
    'IBKR_READ_ONLY_ATTESTED','IBKR_VERIFIED_TWS_PORT','IBKR_PORT','IBKR_CLIENT_ID','TRADING_PYTHON_ROOT','TRADING_PYTHON','LIVE_TRADING')
$saved=@{};foreach($name in $names){$saved[$name]=[Environment]::GetEnvironmentVariable($name)}
$proc=$null
function Check($condition,$message){if(-not $condition){throw $message}}
function GetApi($path){Invoke-RestMethod ('http://127.0.0.1:5080'+$path) -Headers $headers}
function Start-Api {
    $dll=Join-Path $repoRoot 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'
    $apiProcess=Start-Process dotnet -ArgumentList ('"'+$dll+'"') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $repoRoot '.local/paper-smoke.log') -RedirectStandardError (Join-Path $repoRoot '.local/paper-smoke.err')
    for($i=0;$i -lt 50;$i++) {
        if($apiProcess.HasExited){throw 'Paper API exited; inspect .local/paper-smoke.err'}
        try{$null=Invoke-RestMethod 'http://127.0.0.1:5080/health';return $apiProcess}catch{Start-Sleep -Milliseconds 200}
    }
    Stop-Process -Id $apiProcess.Id;throw 'API startup timeout'
}
function Stop-Api {
    if($proc -and -not $proc.HasExited) {
        # Native process termination cannot deliver SIGTERM to a .NET console on Windows.
        # Test abrupt backend restart explicitly; terminate only its own child tree.
        & taskkill.exe /PID $proc.Id /T /F | Out-Null
        if($LASTEXITCODE -ne 0){throw 'Could not terminate test API tree; elevated process permission may be required'}
        if(-not $proc.WaitForExit(5000)){throw 'Test API did not exit'}
    }
}
try {
    $testSocket=New-Object Net.Sockets.TcpClient
    try {$testSocket.Connect('127.0.0.1',5080);throw 'Port 5080 is occupied; stop the existing API first'}
    catch [Net.Sockets.SocketException] {} finally {$testSocket.Dispose()}
    if(-not $RealTws) {
        if(-not $env:TRADING_TEST_DB){throw 'Set TRADING_TEST_DB to the synthetic disposable database'}
        $env:TRADING_DB=$env:TRADING_TEST_DB
        $env:TRADING_DB_AUTO_MIGRATE='false'
        $env:IBKR_PAPER_ACCOUNT='DU'+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $env:IBKR_PAPER_ATTESTED='true';$env:IBKR_READ_ONLY_ATTESTED='true'
        $env:IBKR_VERIFIED_TWS_PORT='7497';$env:IBKR_PORT='7497';$env:IBKR_CLIENT_ID='73'
        $env:TRADING_PYTHON_ROOT=Join-Path $repoRoot 'python/tests/fixtures'
        Write-Output 'SYNTHETIC PROCESS TEST: no connection to TWS; observations are test doubles.'
    } else {
        if(-not $env:TRADING_DB -or -not $env:IBKR_PAPER_ACCOUNT -or $env:IBKR_PAPER_ATTESTED -ne 'true' -or $env:IBKR_READ_ONLY_ATTESTED -ne 'true') {
            throw 'Real demonstration requires configured database, exact authorized account, Paper and Read-Only attestations'
        }
        $env:TRADING_PYTHON_ROOT=Join-Path $repoRoot 'python'
    }
    $env:IBKR_DATA_ENABLED='true';$env:LIVE_TRADING='false'
    $env:TRADING_PYTHON=Join-Path $repoRoot '.venv/Scripts/python.exe'
    $env:TRADING_ADMIN_TOKEN=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
    $headers=@{Authorization='Bearer '+$env:TRADING_ADMIN_TOKEN}
    $proc=Start-Api
    try{$null=Invoke-RestMethod 'http://127.0.0.1:5080/api/broker/status';throw 'Missing token accepted'}
    catch {if($_.Exception.Response.StatusCode.value__ -ne 401){throw}}
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(180)
    do {
        $status=GetApi '/api/broker/status'
        if($status.state -eq 'REJECTED'){throw 'Paper account or permissions rejected'}
        if($status.state -eq 'DEGRADED'){throw ('Paper data validation failed: '+$status.reason)}
        $complete=$status.connected
        foreach($tf in @('15m','1h','4h')) {
            $candles=GetApi ('/api/market/eurusd/candles?timeframe='+$tf)
            if($candles.rows.Count -eq 0){$complete=$false}
        }
        if(-not $complete){Start-Sleep -Milliseconds 500}
    } until($complete -or [DateTimeOffset]::UtcNow -gt $deadline)
    Check $complete 'Paper history demonstration timed out'
    Check (-not $status.liveEnabled -and -not $status.ordersSupported -and $status.readOnly) 'Unsafe broker capabilities'
    $balance=GetApi '/api/broker/account';$positions=GetApi '/api/broker/positions';$quote=GetApi '/api/market/eurusd/quote';$contract=GetApi '/api/market/eurusd/contract'
    Check ($balance.data.values.Count -gt 0 -and $contract.data.con_id -gt 0) 'Missing broker observations'
    Check (-not $quote.executable -and -not $quote.data.executable) 'Quote became executable'
    $counts=@{};foreach($tf in @('15m','1h','4h')){$counts[$tf]=(GetApi ('/api/market/eurusd/candles?timeframe='+$tf)).rows.Count}
    if(-not $RealTws) {
        Check ($quote.data.data_type -eq 'FROZEN') 'Frozen status lost'
        Check ($counts['15m'] -eq 1 -and $counts['1h'] -eq 1 -and $counts['4h'] -eq 1) 'Duplicate candles stored'
        Stop-Api;$proc=$null;$proc=Start-Api
        $recovered=GetApi '/api/market/eurusd/candles?timeframe=4h'
        Check ($recovered.rows.Count -eq 1) 'Restart lost candles'
    }
    # Route absence is checked without constructing or transmitting an IBKR order.
    try {$null=Invoke-RestMethod -Method Post 'http://127.0.0.1:5080/api/broker/orders' -Headers $headers -ContentType application/json -Body '{}';throw 'Order route exists'}
    catch {if($_.Exception.Response.StatusCode.value__ -ne 404){throw}}
    [pscustomobject]@{realTws=[bool]$RealTws;accountId=$status.accountId;sdk=$status.sdkVersion;serverVersion=$status.serverVersion;
        port=$status.port;quoteType=$quote.data.data_type;quoteMarketDataType=$quote.data.market_data_type;
        quoteReceivedAt=$quote.receivedAt;quoteSourceTimestamp=$quote.data.source_timestamp;quoteBid=$quote.data.bid;quoteAsk=$quote.data.ask;
        balanceCurrency=$balance.data.base_currency;balanceValues=$balance.data.values;balanceReceivedAt=$balance.receivedAt;
        positionsCount=@($positions.data).Count;positionsReceivedAt=$positions.receivedAt;contractConId=$contract.data.con_id;
        retrievedCandles=$counts;queryLimit=500;ordersSupported=$false;authenticationVerified=$true} | ConvertTo-Json -Depth 5
} finally {
    Stop-Api
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$saved[$name])}
}
