param([ValidateSet('Prepare','Assess','Status','Run','Once','Stop','PaperPlan')][string]$Action='Status',[string]$Experiment)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'r20-only-policy.ps1')
Assert-R20OnlyLegacyAction -Entry 'r10-price-risk' -Action $Action
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$oldPath=$env:PYTHONPATH;$oldDb=$env:TRADING_LAB_DB
try {
 $env:PYTHONPATH=Join-Path $root 'python'
 & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
 $argsList=@('-m','trading_agent.r10_price_risk',$Action,'--root',$root)
 if($Experiment){$argsList+=@('--experiment',$Experiment)}
 & (Join-Path $root '.venv/Scripts/python.exe') @argsList
 if($LASTEXITCODE -ne 0){throw 'PRICE_RISK_RESEARCH_BLOCKED_INSPECT_JOURNAL'}
} finally {$env:PYTHONPATH=$oldPath;$env:TRADING_LAB_DB=$oldDb}
