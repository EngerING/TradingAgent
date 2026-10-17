param(
 [Parameter(Mandatory=$true)][ValidateSet('Prepare','Inspect','Diagnose','Assess','Status','Authorize','Run','Stop','Revoke','RecoveryInspect','RecoveryAuthorize','RecoveryRun','CancelPending')][string]$Action,
 [string]$TrialId='', [string]$EvidencePath='',
 [ValidateSet('PAPER_EXPERIMENTAL_H40_SUPERVISED_V1','H40_PAPER_EXPERIMENTAL_R3')][string]$Profile='PAPER_EXPERIMENTAL_H40_SUPERVISED_V1'
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPythonPath=$env:PYTHONPATH
try {
 $env:PYTHONPATH=Join-Path $root 'python'
 $python=Join-Path $root '.venv/Scripts/python.exe'
 function Invoke-Trial([string]$op) {
  $arguments=@('-m','trading_agent.h40_paper_trial',$op,'--root',$root,'--profile',$Profile)
  if($TrialId){$arguments+=@('--trial',$TrialId)}
  if($EvidencePath){$arguments+=@('--evidence',$EvidencePath)}
  $text=& $python @arguments
  if($LASTEXITCODE -ne 0){Write-Output $text;throw 'H40_TRIAL_BLOCKED_SEE_SANITIZED_REASON'}
  return $text
 }
 if($Action -in @('Authorize','RecoveryAuthorize')) {
  if($TrialId -cnotmatch '^h40-trial-[a-f0-9]{32}$'){throw 'INVALID_TRIAL_ID'}
  $dir=Join-Path $root ('artifacts/paper-trials/h40/'+$TrialId)
  if($Action -eq 'Authorize') {
   if(-not $EvidencePath){throw 'PAPER_CAPABILITY_RECEIPTS_REQUIRED_NO_GRANT_WRITTEN'}
   foreach($name in @('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop','h40-paper-trial.stop')){
    if(Test-Path -LiteralPath (Join-Path $root ('.local/'+$name))){throw 'PROTECTED_EMERGENCY_REVIEW_REQUIRED_NO_GRANT_WRITTEN'}
   }
   if(Test-Path -LiteralPath (Join-Path $root '.local/h40-paper-trial-consumed.dpapi')){throw 'ONE_GLOBAL_H40_TRIAL_ONLY'}
   $report=(Invoke-Trial 'Assess') | ConvertFrom-Json
   if(@($report.blockers).Count -ne 0){Write-Output ($report.blockers | ConvertTo-Json -Compress);throw 'H40_TRIAL_NOT_READY_NO_GRANT_WRITTEN'}
   $confirm=if($report.experiment_profile -ceq 'H40_PAPER_EXPERIMENTAL_R3'){'AUTHORIZE_ONE_H40_PAPER_EXPERIMENTAL_R3_3_PERCENT_NO_LIVE'}else{'AUTHORIZE_ONE_SUPERVISED_H40_PAPER_TRIAL_2_PERCENT_NO_LIVE'}
  } else {
   $report=(Invoke-Trial 'RecoveryInspect') | ConvertFrom-Json
   if([decimal]$report.quantity -le 0){throw 'FLAT_NO_RECOVERY_ORDER_REQUIRED'}
   if($report.close_previously_attempted -eq $true -or @($report.buy_exec_ids).Count -eq 0 -or @($report.buy_perm_ids).Count -eq 0){throw 'RECOVERY_RECONCILIATION_REQUIRED_NO_BLIND_RETRY'}
   $confirm='AUTHORIZE_OWNED_H40_PAPER_RECOVERY_CLOSE_ONLY_NO_SHORT'
  }
  if((Read-Host ('Supervision local obligatoria; no rentabilidad acreditada. Escribe '+$confirm)) -cne $confirm){throw 'EXPLICIT_OWNER_CONSENT_REQUIRED'}
  if((Read-Host 'Verifica exclusivamente TWS Paper, API habilitada y Read-Only API desactivada para esta prueba. Escribe PAPER_TWS_API_CONFIRMED') -cne 'PAPER_TWS_API_CONFIRMED'){throw 'PAPER_TWS_API_ATTESTATION_REQUIRED'}
  # Refresh after human input. Never serialize a stale readiness or ownership.
  if($Action -eq 'Authorize') {
   $report=(Invoke-Trial 'Assess') | ConvertFrom-Json
   if(@($report.blockers).Count -ne 0){throw 'FRESH_H40_TRIAL_READINESS_BLOCKED'}
  } else {
   $report=(Invoke-Trial 'RecoveryInspect') | ConvertFrom-Json
   if([decimal]$report.quantity -le 0 -or $report.close_previously_attempted -eq $true){throw 'RECOVERY_POSITION_CHANGED'}
  }
  . (Join-Path $PSScriptRoot 'ibkr-session.ps1')
  $binding=Get-PaperAccountBinding
  if($binding.binding_id -cne $report.binding_id){throw 'EXACT_PAPER_BINDING_CHANGED'}
  $owners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
  if($owners.Count -ne 1){throw 'EXACT_TWS_PROCESS_REQUIRED'}
  $tws=Get-Process -Id $owners[0]
  $code='import json, sys; from pathlib import Path; from trading_agent.h40_paper_trial import hashes; print(json.dumps(hashes(Path(sys.argv[1]),sys.argv[2])))'
  $selectedProfile=$report.experiment_profile
  $source=& $python -c $code $root $selectedProfile
  if($LASTEXITCODE -ne 0){throw 'DEPLOYMENT_ATTESTATION_FAILED'}
  $now=[DateTimeOffset]::UtcNow
  $g=[ordered]@{schema_version=1;trial_id=$TrialId;account=$binding.account;binding_id=$binding.binding_id;
   environment='PAPER_TRADING';live_enabled=$false;host=$transport.host;port=$transport.port;
   source_hashes=($source | ConvertFrom-Json);tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();
   read_only_disabled_checked=$true;issued_at=$now.ToString('o');expires_at=$now.AddMinutes(30).ToString('o');revoked=$false}
  if($Action -eq 'Authorize') {
   $g.scope=$report.scope;$g.supervised_protection_bootstrap=$true
   $g.experiment_profile=$report.experiment_profile;$g.variant_version=$report.variant_version
   $g.protocol_sha256=(Get-FileHash -LiteralPath (Join-Path $dir 'protocol.json')).Hash.ToLowerInvariant()
   $g.paper_evidence=$report.paper_evidence;$g.evidence_sha256=$report.evidence_sha256
   $dest=Join-Path $dir 'authorization.dpapi'
  } else {
   $g.scope=$report.recovery_scope;$g.intent=$report.intent;$g.con_id=$report.con_id;
   $g.experiment_profile=$report.experiment_profile;$g.variant_version=$report.variant_version
   $g.quantity=$report.quantity;$g.buy_exec_ids=@($report.buy_exec_ids);$g.buy_perm_ids=@($report.buy_perm_ids)
   $g.journal_hash_at_consent=$report.journal_hash;$dest=Join-Path $dir 'recovery.dpapi'
  }
  Add-Type -AssemblyName System.Security
  $bytes=[Text.Encoding]::UTF8.GetBytes(($g | ConvertTo-Json -Depth 18 -Compress))
  try {
   $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
   $file=[IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
   try {$file.Write($sealed,0,$sealed.Length);$file.Flush($true)} finally {$file.Dispose()}
  } finally {[Array]::Clear($bytes,0,$bytes.Length);$binding=$null;$g=$null}
  Write-Output 'SCOPED_H40_PAPER_CONSENT_RECORDED; NO_ORDER_SENT; EMERGENCY_UNCHANGED; NO_PAPER_AUTO; LIVE_BLOCKED'
 } else {Invoke-Trial $Action}
} finally {$env:PYTHONPATH=$priorPythonPath}
