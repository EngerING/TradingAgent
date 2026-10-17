# Shared protected identity/configuration helpers. Dot-source; never sends orders.
$sessionRoot=Split-Path -Parent $PSScriptRoot
$transport=Get-Content -LiteralPath (Join-Path $sessionRoot 'config/ibkr-session.json') -Raw | ConvertFrom-Json
if($transport.host -cnotin @('127.0.0.1','::1') -or $transport.port -lt 1 -or $transport.port -gt 65535){throw 'IBKR_ENDPOINT_CONFIGURATION_INVALID'}
function Get-PaperAccountBinding {
    $priorBindingPath=$env:PYTHONPATH
    try {
        $env:PYTHONPATH=Join-Path $sessionRoot 'python'
        $result=& (Join-Path $sessionRoot '.venv/Scripts/python.exe') -m trading_agent.ibkr_session --root $sessionRoot
        if($LASTEXITCODE -ne 0){throw 'ACCOUNT_BINDING_HARD_STOP'}
        Add-Type -AssemblyName System.Security
        $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $sessionRoot '.local/ibkr-account-binding.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        try {return ([Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json)}
        finally {[Array]::Clear($plain,0,$plain.Length)}
    } finally {$env:PYTHONPATH=$priorBindingPath}
}
