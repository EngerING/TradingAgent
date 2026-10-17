param([ValidateSet('Inspect','Authorize','Execute','Status')][string]$Action='Inspect',
      [ValidateRange(1,30)][int]$SessionMinutes=15,[string]$Intent='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'ibkr-session.ps1')
$recoveryPath=Join-Path $root '.local/paper-recovery-close.dpapi'
$anchorPath=Join-Path $root '.local/paper-lab-authorization.dpapi'
Add-Type -AssemblyName System.Security
function Read-Protected([string]$path) {
    $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($path),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {return ([Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json)} finally {[Array]::Clear($plain,0,$plain.Length)}
}
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -cne 'false'){throw 'LIVE_DISABLED'}
if($Action -eq 'Status') {
    if(-not(Test-Path -LiteralPath $recoveryPath)){Write-Output 'RECOVERY_NOT_AUTHORIZED';return}
    $a=Read-Protected $recoveryPath
    @{mode=$a.mode;scope=$a.scope;account=('***'+$a.account.Substring($a.account.Length-4));intent=$a.intent;
      openingPermId=$a.opening_perm_id;maxQuantity=$a.max_quantity;expiresAt=$a.expires_at;
      expired=([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($a.expires_at));singleUse=$a.single_use;emergencyRetained=$a.emergency_retained;liveEnabled=$a.live_enabled} | ConvertTo-Json
    return
}
$priorPath=$env:PYTHONPATH;$priorLabDb=$env:TRADING_LAB_DB;$priorDb=$env:TRADING_DB;$priorMigrate=$env:TRADING_DB_AUTO_MIGRATE;$started=$false
try {
    $socket=New-Object Net.Sockets.TcpClient
    try {$pending=$socket.ConnectAsync('127.0.0.1',55433);$null=$pending.Wait(1000);$alreadyRunning=$socket.Connected}
    catch {$alreadyRunning=$false} finally {$socket.Dispose()}
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Start
    $started=-not $alreadyRunning
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load
    $env:PYTHONPATH=Join-Path $root 'python'
    & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
    $argsList=@('--root',$root);if($Intent){$argsList+=@('--intent',$Intent)}
    if($Action -ne 'Execute'){$argsList+='--inspect'}
    if($Action -eq 'Authorize') {
        $preview=& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_recovery_close @argsList
        if($LASTEXITCODE -ne 0){throw 'RECOVERY_PREFLIGHT_BLOCKED'}
        $plan=$preview | ConvertFrom-Json
        if($plan.ready -ne $true -or [decimal]$plan.quantity_to_close -le 0){throw 'RECOVERY_PREFLIGHT_BLOCKED'}
        $anchor=Read-Protected $anchorPath
        $candidate=Read-Protected (Join-Path $root '.local/ibkr-paper-candidate.dpapi')
        if(-not [string]::Equals($anchor.account,$candidate.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}
        Write-Output ('RECOVERY_CLOSE_ONLY: SELL IOC de LONG conciliado hasta '+$plan.quantity_to_close+' EUR; BUY permId '+$plan.opening_perm_id+'; sin entradas, sin levantar emergencia. Un solo envio; parcial/timeout exige reconciliacion y nueva decision local.')
        $binding=Get-PaperAccountBinding
        $typed=$binding.account
        try {if(-not [string]::Equals($typed,$anchor.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}} finally {$typed=$null;$entered=$null}
        if((Read-Host 'Tras verificar Paper, permisos FX y API habilitada, y detener otras operaciones manuales/automaticas EUR/USD, escribe PAPER_RECOVERY_CLOSE_ONLY') -cne 'PAPER_RECOVERY_CLOSE_ONLY'){throw 'RECOVERY_OWNER_ATTESTATION_REQUIRED'}
        # Refresh the broker after owner input; do not seal a stale position or quote.
        & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
        $candidate=Read-Protected (Join-Path $root '.local/ibkr-paper-candidate.dpapi')
        if(-not [string]::Equals($anchor.account,$candidate.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}
        $fresh=& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_recovery_close @argsList
        if($LASTEXITCODE -ne 0){throw 'RECOVERY_PREFLIGHT_BLOCKED'}
        $current=$fresh | ConvertFrom-Json
        if($current.ready -ne $true -or $current.intent -cne $plan.intent -or $current.source_signature -cne $plan.source_signature -or
           [decimal]$current.quantity_to_close -gt [decimal]$plan.quantity_to_close){throw 'RECOVERY_POSITION_CHANGED'}
        $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
        if($listeners.Count -ne 1){throw 'TWS_SESSION_UNVERIFIED'}
        $tws=Get-Process -Id $listeners[0];$now=[DateTimeOffset]::UtcNow
        if($tws.Id -ne $current.tws_pid -or $tws.StartTime.ToFileTimeUtc().ToString() -cne $current.tws_start_filetime){throw 'RECOVERY_TWS_SESSION_CHANGED'}
        $record=[ordered]@{schema_version=1;mode='RecoveryClose';scope='RECOVERY_CLOSE_ONLY';authorized=$true;revoked=$false;
          environment='PAPER_TRADING';live_enabled=$false;account=$anchor.account;host=$transport.host;port=$transport.port;client_id=82;
          tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();session_id=[Guid]::NewGuid().ToString('N');
          paper_checked=$true;identity_manual_match=$true;read_only_disabled_checked=$true;forex_permission_checked=$true;
          single_use=$true;emergency_retained=$true;contract_id=12087792;instrument='EUR/USD CASH IDEALPRO';side='SELL';order_types=@('LMT');tif='IOC';
          intent=$current.intent;opening_order_id=[int]$current.opening_order_id;opening_perm_id=[int]$current.opening_perm_id;
          opening_quantity=[string]$current.opening_quantity;source_signature=$current.source_signature;max_quantity=[string]$current.quantity_to_close;
          confirmed_at=$now.ToString('o');expires_at=$now.AddMinutes($SessionMinutes).ToString('o')}
        $bytes=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 8 -Compress))
        try {
            $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
            [IO.File]::WriteAllBytes($recoveryPath+'.tmp',$sealed);Move-Item -LiteralPath ($recoveryPath+'.tmp') -Destination $recoveryPath -Force
        } finally {[Array]::Clear($bytes,0,$bytes.Length)}
        Write-Output 'RECOVERY_AUTHORIZED_ONCE; emergencia conservada; autorizacion diagnostica sin cambios; ninguna orden enviada.'
    } else {
        & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_recovery_close @argsList
        if($LASTEXITCODE -ne 0){throw 'RECOVERY_SUSPENDED_INSPECT_JOURNAL'}
    }
} finally {
    if($started){& (Join-Path $root 'scripts/paper-database.ps1') -Action Stop}
    $env:PYTHONPATH=$priorPath;$env:TRADING_LAB_DB=$priorLabDb;$env:TRADING_DB=$priorDb;$env:TRADING_DB_AUTO_MIGRATE=$priorMigrate
}
