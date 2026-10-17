param([string]$Study='eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd',[ValidateRange(0,1)][decimal]$SolBudget=0,[switch]$CopyAccessCode)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($Study -notmatch '^eurusd-shadow-[a-f0-9]{32}$'){throw 'INVALID_SHADOW_STUDY'}
$secret=Join-Path $root '.local/dashboard-access.dpapi.xml'
if(-not(Test-Path -LiteralPath $secret)){
    $code=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
    [pscredential]::new('dashboard-readonly',(ConvertTo-SecureString $code -AsPlainText -Force)) | Export-Clixml -LiteralPath $secret
    $code=$null
}
$names=@('TRADING_ADMIN_TOKEN','TRADING_DASHBOARD_TOKEN','TRADING_DB','TRADING_DB_AUTO_MIGRATE','TRADING_LAB_DB','TRADING_UI_ROOT','TRADING_UI_STUDY','TRADING_SOL_CHAT_BUDGET','IBKR_DATA_ENABLED')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Load | Out-Null
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
    $credential=Import-Clixml -LiteralPath $secret
    $env:TRADING_DASHBOARD_TOKEN=$credential.GetNetworkCredential().Password
    $env:TRADING_ADMIN_TOKEN=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
    if($CopyAccessCode){Set-Clipboard -Value $env:TRADING_DASHBOARD_TOKEN;Write-Output 'Código local de lectura copiado; pégalo únicamente en el dashboard. No es la API Key ni la credencial administrativa.'}
    $env:TRADING_UI_ROOT=$root;$env:TRADING_UI_STUDY=$Study
    $env:TRADING_SOL_CHAT_BUDGET=$SolBudget.ToString([Globalization.CultureInfo]::InvariantCulture)
    # The UI reads the existing observer journal; it does not start a second collector or any runner.
    $env:IBKR_DATA_ENABLED='false'
    Write-Output "TradingAgent: http://127.0.0.1:5080 | Sol presupuesto US`$$SolBudget | solo lectura | Ctrl+C detiene el backend."
    # Separate host build: Debug remains pinned to the running R20 journal and recovery manifests.
    & dotnet (Join-Path $root 'src/TradingAgent.Api/bin/R20Only/net9.0/TradingAgent.Api.dll')
    if($LASTEXITCODE -ne 0){throw 'DASHBOARD_STOPPED_INSPECT_SAFE_LOGS'}
} finally {foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name],'Process')};$credential=$null}
