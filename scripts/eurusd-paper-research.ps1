param([ValidateSet('Backtest','Observe','ForwardStep')][string]$Action='Backtest', [string]$Observation)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'r20-only-policy.ps1')
Assert-R20OnlyLegacyAction -Entry 'eurusd-paper-research' -Action $Action
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH=Join-Path $root 'python'
    $python=Join-Path $root '.venv/Scripts/python.exe'
    if($Action -eq 'Observe') {
        # Discovery writes an identity candidate, never an order authorization.
        # Informational IBKR stderr must not become a PowerShell NativeCommandError.
        $eventLog=Join-Path $root ('artifacts/research/eurusd-paper-research-100/identity-'+[Guid]::NewGuid().ToString('N')+'.log')
        $null=New-Item -ItemType Directory -Force -Path (Split-Path -Parent $eventLog)
        $ErrorActionPreference='Continue'
        & $python -m trading_agent.paper_identity 2> $eventLog
        $identityExit=$LASTEXITCODE
        $ErrorActionPreference='Stop'
        if($identityExit -ne 0){throw 'PAPER_IDENTITY_DISCOVERY_FAILED'}
    }
    $arguments=@('-m','trading_agent.eurusd_paper_research','--root',$root,'--action',$Action)
    if($Action -eq 'ForwardStep') {
        if(-not $Observation){throw 'OBSERVATION_REQUIRED'}
        $arguments+=@('--observation',$Observation)
    }
    & $python @arguments
    if($LASTEXITCODE -ne 0){throw 'EURUSD_RESEARCH_STOPPED_INSPECT_EVIDENCE'}
} finally {$env:PYTHONPATH=$priorPath}
