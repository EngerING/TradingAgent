param([string]$Start='2026-04-03T00:00:00Z',[string]$End='2026-10-03T00:00:00Z')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
$names=@('IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_VERIFIED_TWS_PORT','IBKR_PORT','IBKR_DATA_ENABLED','IBKR_CLIENT_ID','LIVE_TRADING','PYTHONPATH','PAPER_MANUAL_EXPIRES_AT')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name)}
try {
    & (Join-Path $root 'scripts/paper-identity.ps1') -Action Load
    Add-Type -AssemblyName System.Security
    $bytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $root '.local/ibkr-paper-authorized.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {$authorization=[Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json;$env:PAPER_MANUAL_EXPIRES_AT=([DateTimeOffset]::Parse($authorization.confirmed_at)).AddHours(24).ToString('o')}
    finally {[Array]::Clear($bytes,0,$bytes.Length);$authorization=$null}
    $env:IBKR_CLIENT_ID='79';$env:PYTHONPATH=Join-Path $root 'python'
    & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.history_extension --root (Join-Path $root '.local/research-history') --start $Start --end $End
    if($LASTEXITCODE -ne 0){throw 'RESEARCH_HISTORY_COLLECTION_BLOCKED'}
} finally {foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name])}}
