param([ValidateSet('Prepare','Inspect','Assess','RecoveryInspect','Status','Authorize','AuthorizeRecovery','Run','Once','Stop','Revoke','Recovery','ReviewEmergency')][string]$Action='Status',
 [string]$Cohort,[string]$EvidencePath,[ValidateRange(1,30)][int]$Minutes=30,
 [ValidateSet('EURUSD_R1','EURUSD_R5','EURUSD_R10')][string]$Profile,
 [ValidateSet('PAPER_EXECUTION_DIAGNOSTIC','PAPER_EXPLORATORY_RESEARCH')][string]$Purpose='PAPER_EXPLORATORY_RESEARCH')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'r20-only-policy.ps1')
Assert-R20OnlyLegacyAction -Entry 'eurusd-paper-exploratory' -Action $Action
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot
$oldPath=$env:PYTHONPATH;$oldDb=$env:TRADING_LAB_DB
try {
 $env:PYTHONPATH=Join-Path $root 'python'
 & (Join-Path $PSScriptRoot 'paper-lab-database.ps1') -Action Load | Out-Null
 $argsList=@('-m','trading_agent.eurusd_exploratory_runner',$Action,'--root',$root)
 if($Cohort){$argsList+=@('--cohort',$Cohort)}
 if($Action -eq 'Prepare'){$argsList+=@('--purpose',$Purpose)}
 if($Action -eq 'Authorize') {
  if((Read-Host 'Confirma EURUSD_PAPER_EXPLORATORY; sólo Paper, sin rentabilidad validada, sin levantar emergencia (escribe AUTORIZAR PAPER EXPLORATORY)') -cne 'AUTORIZAR PAPER EXPLORATORY'){throw 'LOCAL_CONFIRMATION_REQUIRED'}
  $argsList+=@('--confirmed','--minutes',$Minutes,'--evidence',$EvidencePath,'--profile',$Profile)
 }
 if($Action -eq 'ReviewEmergency') {
  & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.eurusd_exploratory_runner Inspect --root $root --cohort $Cohort
  if($LASTEXITCODE -ne 0){throw 'REVIEW_INSPECT_FAILED'}
  if((Read-Host 'Revisa el incidente EUR y la conciliación anterior. Para levantar SOLO la emergencia Paper escribe REVISADO LEVANTAR PAPER') -cne 'REVISADO LEVANTAR PAPER'){throw 'LOCAL_REVIEW_CONFIRMATION_REQUIRED'}
  $argsList+='--confirmed'
 }
 if($Action -eq 'AuthorizeRecovery') {
  & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.eurusd_exploratory_runner Inspect --root $root --cohort $Cohort
  if($LASTEXITCODE -ne 0){throw 'RECOVERY_INSPECT_FAILED'}
  if((Read-Host 'Autoriza una reducción única del inventario propio Paper confirmado (escribe CERRAR SOLO PAPER PROPIO)') -cne 'CERRAR SOLO PAPER PROPIO'){throw 'LOCAL_RECOVERY_CONFIRMATION_REQUIRED'}
  $argsList+=@('--confirmed','--minutes',$Minutes)
 }
 & (Join-Path $root '.venv/Scripts/python.exe') @argsList
 if($LASTEXITCODE -ne 0){throw 'EXPLORATORY_BLOCKED_INSPECT_EVIDENCE'}
} finally {$env:PYTHONPATH=$oldPath;$env:TRADING_LAB_DB=$oldDb}
