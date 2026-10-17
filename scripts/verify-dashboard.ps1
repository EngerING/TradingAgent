param()
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$names=@('TRADING_DB','TRADING_DB_AUTO_MIGRATE','TRADING_LAB_DB','TRADING_UI_ROOT','TRADING_UI_STUDY','TRADING_SOL_CHAT_BUDGET','TRADING_ADMIN_TOKEN','TRADING_DASHBOARD_TOKEN','IBKR_DATA_ENABLED')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$proc=$null
try {
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Load | Out-Null
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
    $env:TRADING_UI_ROOT=$root;$env:TRADING_UI_STUDY='eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd'
    $env:TRADING_SOL_CHAT_BUDGET='0';$env:IBKR_DATA_ENABLED='false'
    $env:TRADING_ADMIN_TOKEN=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
    $env:TRADING_DASHBOARD_TOKEN=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
    $dll=Join-Path $root 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'
    $proc=Start-Process -FilePath dotnet -ArgumentList ('"'+$dll+'"') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'artifacts/frontend-preparation/api-e2e.log') -RedirectStandardError (Join-Path $root 'artifacts/frontend-preparation/api-e2e.err')
    $ready=$false
    for($i=0;$i -lt 50;$i++){
        if($proc.HasExited){throw 'DASHBOARD_TEST_SERVER_EXITED'}
        try{$null=Invoke-RestMethod 'http://127.0.0.1:5080/health';$ready=$true;break}catch{Start-Sleep -Milliseconds 200}
    }
    if(-not $ready){throw 'DASHBOARD_TEST_SERVER_TIMEOUT'}
    Push-Location (Join-Path $root 'frontend')
    try{npm run test:e2e;if($LASTEXITCODE -ne 0){throw 'DASHBOARD_E2E_FAILED'}}finally{Pop-Location}
} finally {
    if($proc -and -not $proc.HasExited){Stop-Process -Id $proc.Id}
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name],'Process')}
}
