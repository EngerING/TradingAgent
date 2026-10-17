param([ValidateSet('Prepare','Status','Run','Once','Stop','PaperPlan')][string]$Action='Status',[string]$Experiment)
$ErrorActionPreference='Stop'
if($Action -eq 'Prepare'){throw 'R20_V1_NEW_COHORT_RETIRED'}
$root=Split-Path -Parent $PSScriptRoot
$names=@('PYTHONPATH','TRADING_LAB_DB','OPENAI_API_KEY','LIVE_TRADING')
$prior=@{};foreach($name in $names){$prior[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
    $env:PYTHONPATH=Join-Path $root 'python';$env:LIVE_TRADING='false'
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
    $arguments=@('-m','trading_agent.aggressive_growth_runner',$Action,'--root',$root)
    if($Experiment){$arguments+=@('--experiment',$Experiment)}
    & (Join-Path $root '.venv/Scripts/python.exe') @arguments
    if($LASTEXITCODE -ne 0){throw 'R20_BLOCKED_INSPECT_JOURNAL'}
} finally {foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$prior[$name],'Process')}}
