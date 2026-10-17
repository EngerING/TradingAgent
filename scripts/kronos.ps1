param([ValidateSet('Install','Once','Observe','Status','Stop','Resume','Replay')][string]$Action='Status',[string]$Study,[string]$Configuration)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.local/kronos/venv/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $python)){throw 'KRONOS_ISOLATED_ENVIRONMENT_MISSING'}
$prior=@{}
$keys=@('PYTHONPATH','TRADING_LAB_DB','HF_HOME','HF_HUB_OFFLINE','HF_HUB_DISABLE_TELEMETRY','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','LIVE_TRADING')
$keys+=@(Get-ChildItem Env: | Where-Object {$_.Name -match '^(IBKR_|TRADING_IBKR_)'} | Select-Object -ExpandProperty Name)
foreach($k in $keys){$prior[$k]=[Environment]::GetEnvironmentVariable($k,'Process')}
try {
 $env:PYTHONPATH=Join-Path $root 'python';$env:HF_HOME=Join-Path $root '.local/kronos/hf-cache';$env:HF_HUB_DISABLE_TELEMETRY='1';$env:LIVE_TRADING='false'
 Remove-Item Env:OPENAI_API_KEY,Env:HF_TOKEN,Env:HUGGING_FACE_HUB_TOKEN -ErrorAction SilentlyContinue
 foreach($k in $keys){if($k -match '^(IBKR_|TRADING_IBKR_)'){[Environment]::SetEnvironmentVariable($k,$null,'Process')}}
 if($Action -eq 'Install') {
  Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
  & $python -m pip install --requirement (Join-Path $root 'config/kronos/requirements.lock.txt') --only-binary=:all: --extra-index-url https://download.pytorch.org/whl/cu128
  if($LASTEXITCODE -ne 0){throw 'KRONOS_DEPENDENCIES_FAILED'}
  & $python -m trading_agent.kronos.bootstrap $root
 } else {
  $env:HF_HUB_OFFLINE='1'
  & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load | Out-Null
  $a=@('-m','trading_agent.kronos.worker',$Action,'--root',$root)
  if($Study){$a+=@('--study',$Study)}
  if($Configuration){$a+=@('--config',$Configuration)}
  & $python @a
 }
 if($LASTEXITCODE -ne 0){throw 'KRONOS_FAILED_INSPECT_EVIDENCE'}
} finally {foreach($k in $keys){[Environment]::SetEnvironmentVariable($k,$prior[$k],'Process')}}
