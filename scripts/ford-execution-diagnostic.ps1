param(
 [Parameter(Mandatory=$true)][ValidateSet('Prepare','Inspect','WhatIf','Assess','Status','Authorize','Run','Reconcile','Stop','Revoke','RecoveryInspect','RecoveryAuthorize','RecoveryRun','CancelPending')][string]$Action,
 [string]$TrialId='', [string]$EvidencePath='',
 [ValidateSet('FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1','FORD_DIAGNOSTIC_R10')][string]$Profile='FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1'
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPythonPath=$env:PYTHONPATH
$priorLabDb=$env:TRADING_LAB_DB
try {
 $env:PYTHONPATH=Join-Path $root 'python'
 $python=Join-Path $root '.venv/Scripts/python.exe'
 if($Profile -eq 'FORD_DIAGNOSTIC_R10' -and $Action -in @('Authorize','Run','Reconcile','RecoveryInspect','RecoveryAuthorize','RecoveryRun','CancelPending','Inspect','Assess') -and (Test-Path -LiteralPath (Join-Path $root '.local/paper-lab-db.secret.xml'))) {
  & (Join-Path $PSScriptRoot 'paper-lab-database.ps1') -Action Load | Out-Null
 }
 function Invoke-Diagnostic([string]$op) {
  $arguments=@('-m','trading_agent.ford_execution_diagnostic',$op,'--root',$root,'--profile',$Profile)
  if($TrialId){$arguments+=@('--trial',$TrialId)}
  if($EvidencePath){$arguments+=@('--evidence',$EvidencePath)}
  $text=& $python @arguments
  if($LASTEXITCODE -ne 0){Write-Output $text;throw 'FORD_DIAGNOSTIC_BLOCKED_SEE_SANITIZED_REASON'}
  return $text
 }
 if($Action -in @('Authorize','RecoveryAuthorize')) {
  if($TrialId -cnotmatch '^ford-diag-[a-f0-9]{32}$'){throw 'INVALID_DIAGNOSTIC_ID'}
  $dir=Join-Path $root ('artifacts/paper-diagnostics/ford/'+$TrialId)
  if($Action -eq 'Authorize') {
   if(-not $EvidencePath){throw 'PAPER_DIAGNOSTIC_RECEIPTS_REQUIRED'}
   foreach($n in @('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop','h40-paper-trial.stop','ford-diagnostic.stop')){
    if(Test-Path -LiteralPath (Join-Path $root ('.local/'+$n))){throw 'PROTECTED_EMERGENCY_REVIEW_REQUIRED_NO_GRANT_WRITTEN'}
   }
   if(Test-Path -LiteralPath (Join-Path $root '.local/ford-diagnostic-consumed.dpapi')){throw 'ONE_FORD_DIAGNOSTIC_GLOBAL_ONLY'}
   if(Test-Path -LiteralPath (Join-Path $dir 'revoked.json')){throw 'DIAGNOSTIC_REVOKED_NO_REAUTHORIZATION'}
   $report=(Invoke-Diagnostic 'Assess') | ConvertFrom-Json
   if($report.error -or @($report.blockers).Count -ne 0){Write-Output ($report.blockers | ConvertTo-Json -Compress);throw 'DIAGNOSTIC_NOT_READY_NO_GRANT_WRITTEN'}
   $budget=if($Profile -eq 'FORD_DIAGNOSTIC_R10'){10}else{3}
   $confirm='AUTHORIZE_ONE_FORD_PAPER_EXECUTION_DIAGNOSTIC_1_SHARE_'+$budget+'_USD_NO_STRATEGY_NO_LIVE'
  } else {
   $report=(Invoke-Diagnostic 'RecoveryInspect') | ConvertFrom-Json
   if([decimal]$report.quantity -le 0){throw 'FLAT_NO_RECOVERY_ORDER_REQUIRED'}
   if($report.close_previously_attempted -eq $true -or @($report.buy_exec_ids).Count -eq 0 -or @($report.buy_perm_ids).Count -eq 0){throw 'OWNED_RECOVERY_RECONCILIATION_REQUIRED_NO_RETRY'}
   $confirm='AUTHORIZE_OWNED_FORD_DIAGNOSTIC_RECOVERY_CLOSE_ONLY_NO_SHORT'
  }
  if((Read-Host ('Supervision Paper obligatoria. Escribe '+$confirm)) -cne $confirm){throw 'EXPLICIT_DIAGNOSTIC_OWNER_CONSENT_REQUIRED'}
  if($Action -eq 'Authorize' -and (Read-Host 'El stop no garantiza el presupuesto ante gaps/fallo. Revisa escenarios adversos. Escribe ACKNOWLEDGE_DIAGNOSTIC_TAIL_RISK_NO_BUDGET_INCREASE') -cne 'ACKNOWLEDGE_DIAGNOSTIC_TAIL_RISK_NO_BUDGET_INCREASE'){throw 'TAIL_RISK_REVIEW_REQUIRED'}
  if((Read-Host 'Comprueba TWS Paper exacto, API habilitada y Read-Only API desactivada para el ensayo. Escribe PAPER_TWS_API_CONFIRMED') -cne 'PAPER_TWS_API_CONFIRMED'){throw 'PAPER_TWS_API_ATTESTATION_REQUIRED'}
  if($Action -eq 'Authorize') {
   $report=(Invoke-Diagnostic 'Assess') | ConvertFrom-Json
   if($report.error -or @($report.blockers).Count -ne 0){throw 'FRESH_DIAGNOSTIC_READINESS_BLOCKED'}
  } else {
   $report=(Invoke-Diagnostic 'RecoveryInspect') | ConvertFrom-Json
   if([decimal]$report.quantity -le 0 -or $report.close_previously_attempted -eq $true){throw 'RECOVERY_POSITION_CHANGED'}
  }
  . (Join-Path $PSScriptRoot 'ibkr-session.ps1')
  $binding=Get-PaperAccountBinding
  if($binding.binding_id -cne $report.binding_id){throw 'EXACT_PAPER_BINDING_CHANGED'}
  $owners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
  if($owners.Count -ne 1){throw 'EXACT_TWS_PROCESS_REQUIRED'}
  $tws=Get-Process -Id $owners[0]
  $code='import json,sys; from pathlib import Path; from trading_agent.ford_execution_diagnostic import sources; print(json.dumps(sources(Path(sys.argv[1]))))'
  $source=& $python -c $code $root
  if($LASTEXITCODE -ne 0){throw 'DIAGNOSTIC_DEPLOYMENT_ATTESTATION_FAILED'}
  $now=[DateTimeOffset]::UtcNow
  $g=[ordered]@{schema_version=1;trial_id=$TrialId;account=$binding.account;binding_id=$binding.binding_id;
   environment='PAPER_TRADING';live_enabled=$false;host=$transport.host;port=$transport.port;
   scope=$Profile;source_hashes=($source | ConvertFrom-Json);
   protocol_sha256=(Get-FileHash -LiteralPath (Join-Path $dir 'protocol.json')).Hash.ToLowerInvariant();
   tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();read_only_disabled_checked=$true;
   issued_at=$now.ToString('o');expires_at=$now.AddMinutes(30).ToString('o');revoked=$false}
  if($Action -eq 'Authorize') {
   $g.supervised_protection_bootstrap=$true;$g.tail_risk_acknowledged=$true
   $g.paper_evidence=$report.paper_evidence;$g.evidence_path=(Resolve-Path -LiteralPath $EvidencePath).Path
   $g.evidence_sha256=(Get-FileHash -LiteralPath $EvidencePath).Hash.ToLowerInvariant()
   $dest=Join-Path $dir 'authorization.dpapi'
  } else {
   $g.scope=if($Profile -eq 'FORD_DIAGNOSTIC_R10'){'FORD_DIAGNOSTIC_R10_RECOVERY_CLOSE_ONLY'}else{'FORD_DIAGNOSTIC_OWNED_RECOVERY_ONLY_V1'};$g.intent=$report.intent;$g.con_id=$report.con_id;
   $g.quantity=$report.quantity;$g.buy_exec_ids=@($report.buy_exec_ids);$g.buy_perm_ids=@($report.buy_perm_ids)
   $g.journal_hash_at_consent=$report.journal_hash;$dest=Join-Path $dir 'recovery.dpapi'
  }
  Add-Type -AssemblyName System.Security
  $bytes=[Text.Encoding]::UTF8.GetBytes(($g | ConvertTo-Json -Depth 24 -Compress))
  try {
   $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
   $file=[IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
   try {$file.Write($sealed,0,$sealed.Length);$file.Flush($true)} finally {$file.Dispose()}
  } finally {[Array]::Clear($bytes,0,$bytes.Length);$binding=$null;$g=$null}
  Write-Output 'ONE_USE_PAPER_DIAGNOSTIC_CONSENT_RECORDED; NO_ORDER_SENT; EMERGENCY_UNCHANGED; NO_STRATEGY_APPROVAL; NO_PAPER_AUTO; LIVE_BLOCKED'
 } else {Invoke-Diagnostic $Action}
} finally {$env:PYTHONPATH=$priorPythonPath;$env:TRADING_LAB_DB=$priorLabDb}
