param([ValidateSet('Prepare','Comparison','Run','Once','Status','Stop')][string]$Action='Status', [string]$Study, [decimal]$OpenAiBudget=0)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'r20-only-policy.ps1')
Assert-R20OnlyLegacyAction -Entry 'eurusd-shadow-research' -Action $Action
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPath=$env:PYTHONPATH;$priorDb=$env:TRADING_LAB_DB
try {
    $env:PYTHONPATH=Join-Path $root 'python'
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
    $arguments=@('-m','trading_agent.eurusd_shadow_research',$Action,'--root',$root)
    if($Study){$arguments+=@('--study',$Study)}
    if($Action -eq 'Prepare'){$arguments+=@('--openai-budget',$OpenAiBudget.ToString([Globalization.CultureInfo]::InvariantCulture))}
    & (Join-Path $root '.venv/Scripts/python.exe') @arguments
    if($LASTEXITCODE -ne 0){throw 'EURUSD_SHADOW_STOPPED_INSPECT_JOURNAL'}
} finally {$env:PYTHONPATH=$priorPath;$env:TRADING_LAB_DB=$priorDb}
