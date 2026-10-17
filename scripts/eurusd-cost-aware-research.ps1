param([ValidateSet('Search','Prepare','Run','Once','Status','Stop')][string]$Action='Search',[string]$Search,[string]$Study,[string]$Campaign)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'r20-only-policy.ps1')
Assert-R20OnlyLegacyAction -Entry 'eurusd-cost-aware-research' -Action $Action
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPath=$env:PYTHONPATH;$priorDb=$env:TRADING_LAB_DB
try {
    $env:PYTHONPATH=Join-Path $root 'python'
    if($Action -eq 'Search'){
        $arguments=@('-m','trading_agent.eurusd_cost_aware_search','--root',$root)
    }else{
        & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
        $arguments=@('-m','trading_agent.eurusd_cost_aware_forward',$Action,'--root',$root)
        if($Search){$arguments+=@('--search',$Search)}
        if($Study){$arguments+=@('--study',$Study)}
        if($Campaign){$arguments+=@('--campaign',$Campaign)}
    }
    & (Join-Path $root '.venv/Scripts/python.exe') @arguments
    if($LASTEXITCODE -ne 0){throw 'COST_AWARE_RESEARCH_FAILED_INSPECT_EVIDENCE_NO_BROKER_RETRY'}
}finally{$env:PYTHONPATH=$priorPath;$env:TRADING_LAB_DB=$priorDb}
