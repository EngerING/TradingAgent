param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('status','enroll','revoke','watch')][string]$Action,
    [ValidateSet('PAPER','LIVE','BOTH')][string]$Environment = 'PAPER',
    [int]$Port = 0,
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) {
    throw 'M033_WINDOWS_REQUIRED'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'M033_VENV_PYTHON_REQUIRED' }
$old = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'python'
    if ($Action -eq 'status') {
        & $python -B -m trading_agent.market_data.host_service status
    } elseif ($Action -eq 'revoke') {
        if ($Environment -eq 'BOTH') { throw 'M033_REVOKE_EACH_ENVIRONMENT_EXPLICITLY' }
        & $python -B -m trading_agent.market_data.host_service revoke --kind $Environment
    } elseif ($Action -eq 'enroll') {
        if ($Environment -eq 'BOTH') { throw 'M033_ENROLL_EACH_ENVIRONMENT_EXPLICITLY' }
        $expected = if ($Environment -eq 'PAPER') { 7497 } else { 7496 }
        if ($Port -eq 0) { $Port = $expected }
        $clientId = if ($Environment -eq 'PAPER') { 19033 } else { 19034 }
        Write-Output 'SOLO DATOS EUR/USD. NO GUARDA CLAVE IBKR, NO AUTORIZA OPERAR.'
        $confirmation = Read-Host "Confirma TWS $Environment, datos de mercado y Read-Only API DESMARCADO (SI/NO)"
        if ($confirmation.Trim().ToUpperInvariant() -ne 'SI') { throw 'M033_OPERATOR_CONFIRMATION_REQUIRED' }
        $cliArguments = @('-B','-m','trading_agent.market_data.host_service','enroll',
                  '--kind',$Environment,'--port',"$Port",'--client-id',"$clientId",
                  '--confirm-session','--confirm-market-data','--confirm-read-only-disabled')
        if ($Replace) { $cliArguments += '--replace' }
        & $python @cliArguments
    } else {
        Write-Output "M03-A.3 DATA_ONLY: leer TWS autorizado, nunca enviar ordenes."
        $confirmation = Read-Host 'Confirma iniciar el colector DATA_ONLY en TWS (SI/NO)'
        if ($confirmation.Trim().ToUpperInvariant() -ne 'SI') { throw 'M033_OPERATOR_CONFIRMATION_REQUIRED' }
        & $python -B -m trading_agent.market_data.host_service watch --kind $Environment --approved-data-only
    }
    if ($LASTEXITCODE -ne 0) { throw 'M033_HOST_ACTION_FAILED' }
} finally {
    $env:PYTHONPATH = $old
}
