param([ValidateSet('Status','Authorize','AuthorizeEurAbsence','Run','EmergencyStop','Revoke','Review','Diagnose','Di',
 'PaperAutoStatus','GrantPaperAuto','RevokePaperAuto','RunPaperAuto','StopPaperAuto','ClearPaperEmergency')][string]$Action='Status',
 [ValidateSet('ExecutionDiagnostics','StrategyPaper')][string]$Mode='ExecutionDiagnostics',
 [decimal]$DiagnosticLossBudget=0,[int]$MaxExperiments=1,[decimal]$MaxQuantity=100,[decimal]$MaxNotionalUsd=150,
 [int]$MaxHoldSeconds=60,[int]$SessionMinutes=30,[string]$StrategyVersion='',
 [switch]$AllowAbsentEurDiagnostic,[switch]$AllowAbsentEurStrategy,[int]$ExceptionMinutes=15,
 [ValidateSet('PAPER_CONSERVATIVE','PAPER_EXPERIMENTAL_10_PERCENT')][string]$RiskProfile='PAPER_CONSERVATIVE',
 [string]$StrategyEvidencePath='', [switch]$Continuous,[switch]$StrategyMarketEvidence,
 [ValidateSet('Research','PaperAuto','LiveApproval')][string]$ExecutionMode='PaperAuto',
 [ValidateRange(1,1440)][int]$PaperAutoMinutes=480,
 [ValidateSet('trend','pullback','mean_reversion')][string]$PaperAutoStrategy='trend')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'ibkr-session.ps1')
$grantPath=Join-Path $root '.local/paper-lab-authorization.dpapi'
$stopPath=Join-Path $root '.local/paper-lab.emergency'
$eurExceptionPath=Join-Path $root '.local/paper-lab-eur-exception.dpapi'
$reviewPermitPath=Join-Path $root '.local/paper-lab-review-permit.dpapi'
Add-Type -AssemblyName System.Security
function Read-LabGrant([string]$path=$grantPath) {
    if(-not(Test-Path -LiteralPath $path)){throw 'PAPER_EXECUTION_NOT_AUTHORIZED'}
    $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($path),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {return ([Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json)}
    catch {throw 'PROTECTED_AUTHORIZATION_UNREADABLE'}
    finally {[Array]::Clear($plain,0,$plain.Length)}
}
function Read-EurException($grant) {
    $exception=Read-LabGrant $eurExceptionPath
    $now=[DateTimeOffset]::UtcNow;$begin=[DateTimeOffset]::Parse($exception.confirmed_at);$end=[DateTimeOffset]::Parse($exception.expires_at)
    $strategyException=$exception.scope -ceq 'INITIAL_STRATEGY_PAPER_EUR_ABSENCE'
    if($strategyException) {
        if($exception.mode -cne 'StrategyPaper' -or $exception.risk_profile -cne 'PAPER_EXPERIMENTAL_10_PERCENT' -or
           $exception.strategy_version -cnotmatch '^[a-f0-9]{64}$' -or $exception.plan_hash -cnotmatch '^[a-f0-9]{64}$' -or
           $exception.execution_session_id -cnotmatch '^[a-f0-9]{32}$' -or $exception.review_session_id -cne $grant.session_id -or
           $exception.maximum_exposure -ne 1 -or $exception.risk_ceiling -ne 10 -or $exception.loss_allowance -ne 20){throw 'EUR_EXCEPTION_STRATEGY_BINDING_REQUIRED'}
    } elseif($exception.scope -cne 'INITIAL_DIAGNOSTIC_EUR_ABSENCE' -or $exception.mode -cne 'ExecutionDiagnostics' -or
             $grant.mode -cne 'ExecutionDiagnostics' -or $exception.max_experiments -ne 1 -or $exception.max_quantity -ne 100 -or
             $exception.max_notional_usd -ne 150 -or $exception.diagnostic_loss_budget -ne 10 -or $exception.max_hold_seconds -ne 60){throw 'EUR_EXCEPTION_INVALID_OR_EXPIRED'}
    $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
    if($listeners.Count -ne 1){throw 'TWS_SESSION_UNVERIFIED'}
    if($exception.schema_version -ne 1 -or $exception.environment -cne 'PAPER_TRADING' -or $exception.live_enabled -ne $false -or
       $grant.environment -cne 'PAPER_TRADING' -or $grant.live_enabled -ne $false -or
       -not [string]::Equals($exception.account,$grant.account,[StringComparison]::Ordinal) -or
       $exception.tws_pid -ne $listeners[0] -or
       $exception.manual_uncertainty_accepted -ne $true -or $exception.paper_checked -ne $true -or $exception.identity_manual_match -ne $true -or
       $exception.observed_state -cne 'EUR_ROW_ABSENT' -or $exception.record_id -cnotmatch '^[a-f0-9]{32}$' -or $exception.contract_id -ne 12087792 -or
       $begin -gt $now -or $now -ge $end -or $end -gt $begin.AddMinutes(30)) {throw 'EUR_EXCEPTION_INVALID_OR_EXPIRED'}
    $tws=Get-Process -Id $exception.tws_pid -ErrorAction Stop
    if($tws.StartTime.ToFileTimeUtc().ToString() -cne $exception.tws_start_filetime){throw 'EUR_EXCEPTION_TWS_SESSION_CHANGED'}
    return $exception
}
function Save-LabGrant($record,[string]$path=$grantPath) {
    $bytes=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 10 -Compress))
    try {
        $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        [IO.File]::WriteAllBytes($path+'.tmp',$sealed)
        Move-Item -LiteralPath ($path+'.tmp') -Destination $path -Force
    } finally {[Array]::Clear($bytes,0,$bytes.Length)}
}
if($env:LIVE_TRADING -and $env:LIVE_TRADING.ToLowerInvariant() -ne 'false'){throw 'LIVE_DISABLED'}
$clearAutoEmergency=$Action -eq 'ClearPaperEmergency'
if($clearAutoEmergency){$Action='Review'}
if($Action -eq 'Di'){$Action='PaperAutoStatus'}
if($Action -eq 'StopPaperAuto') {
    New-Item -ItemType Directory -Force -Path (Join-Path $root '.local') | Out-Null
    [IO.File]::WriteAllText((Join-Path $root '.local/paper-auto.stop'),[DateTimeOffset]::UtcNow.ToString('o'))
    $Action='EmergencyStop'
}
if($Action -in @('PaperAutoStatus','GrantPaperAuto','RevokePaperAuto','RunPaperAuto')) {
    $priorAutoPath=$env:PYTHONPATH;$priorAutoLab=$env:TRADING_LAB_DB;$priorAutoDb=$env:TRADING_DB;$priorAutoMigrate=$env:TRADING_DB_AUTO_MIGRATE
    $autoStarted=$false
    try {
        $env:PYTHONPATH=Join-Path $root 'python'
        if($Action -eq 'RevokePaperAuto') {
            & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_auto --root $root --action revoke
            if($LASTEXITCODE -ne 0){throw 'PAPER_AUTO_REVOKE_FAILED'}
            return
        }
        if($Action -eq 'GrantPaperAuto') {
            Write-Output ('Autorizacion PAPER AUTO, *** cuenta vinculada, '+$PaperAutoMinutes+' minutos; US100/20, riesgo min(10% equity,US10), exposicion 1x. Ninguna aprobacion Live. Consentimiento una vez por vigencia, sin confirmacion por orden.')
            if((Read-Host 'Tras verificar Paper, API no Read-Only y permisos FX, escribe GRANT_PAPER_AUTO') -cne 'GRANT_PAPER_AUTO'){throw 'EXPLICIT_PAPER_AUTO_OWNER_CONSENT_REQUIRED'}
        }
        $socket=New-Object Net.Sockets.TcpClient
        try {$pending=$socket.ConnectAsync('127.0.0.1',55433);$null=$pending.Wait(1000);$alreadyAuto=$socket.Connected}
        catch {$alreadyAuto=$false} finally {$socket.Dispose()}
        & (Join-Path $root 'scripts/paper-database.ps1') -Action Start;$autoStarted=-not $alreadyAuto
        & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load
        & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
        & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_lab_diagnostics --root $root
        if($LASTEXITCODE -ne 0){throw 'PAPER_AUTO_DIAGNOSTIC_BLOCKED'}
        $autoArgs=@('--root',$root,'--action','status')
        if($Action -eq 'GrantPaperAuto'){$autoArgs=@('--root',$root,'--action','grant','--minutes',$PaperAutoMinutes,'--strategy',$PaperAutoStrategy,'--owner-consent')}
        $autoGrantLock=$null
        try {
            if($Action -eq 'GrantPaperAuto') {
                $autoGrantLock=[IO.File]::Open((Join-Path $root '.local/paper-lab.run.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
                try {$autoGrantLock.Lock(0,1)} catch {throw 'ACTIVE_SESSION_CANNOT_GRANT_PAPER_AUTO'}
            }
            & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_auto @autoArgs
            if($LASTEXITCODE -ne 0){throw 'PAPER_AUTO_BLOCKED'}
        } finally {if($autoGrantLock){$autoGrantLock.Dispose()}}
        if($Action -eq 'RunPaperAuto') {
            $ready=Get-Content -LiteralPath (Join-Path $root 'artifacts/paper-lab/paper-auto-status.json') -Raw | ConvertFrom-Json
            if($ready.paper_auto_ready -ne $true){throw 'PAPER_AUTO_NOT_READY'}
            & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_lab_runner --root $root --execution-mode PaperAuto --paper-auto
            if($LASTEXITCODE -ne 0){throw 'PAPER_AUTO_SUSPENDED'}
        }
    } finally {
        if($autoStarted){& (Join-Path $root 'scripts/paper-database.ps1') -Action Stop}
        $env:PYTHONPATH=$priorAutoPath;$env:TRADING_LAB_DB=$priorAutoLab;$env:TRADING_DB=$priorAutoDb;$env:TRADING_DB_AUTO_MIGRATE=$priorAutoMigrate
    }
    return
}
if($AllowAbsentEurStrategy -and ($AllowAbsentEurDiagnostic -or $Action -notin @('Authorize','Review'))){throw 'EUR_EXCEPTION_OPT_IN_SCOPE_INVALID'}
if($AllowAbsentEurStrategy -and $Action -eq 'Authorize' -and ($Mode -cne 'StrategyPaper' -or $RiskProfile -cne 'PAPER_EXPERIMENTAL_10_PERCENT')){throw 'EUR_EXCEPTION_STRATEGY_SCOPE_INVALID'}
if($AllowAbsentEurDiagnostic -and $Action -notin @('Authorize','Review')){throw 'EUR_EXCEPTION_OPT_IN_SCOPE_INVALID'}
if($Action -eq 'AuthorizeEurAbsence') {
    $grant=Read-LabGrant
    if($Mode -ceq 'ExecutionDiagnostics' -and $grant.mode -cne 'ExecutionDiagnostics'){throw 'INITIAL_PAPER_DIAGNOSTIC_EXCEPTION_ONLY'}
    if($grant.environment -cne 'PAPER_TRADING' -or $grant.live_enabled -ne $false -or
       $grant.paper_checked -ne $true -or $grant.identity_manual_match -ne $true -or $ExceptionMinutes -lt 1 -or $ExceptionMinutes -gt 30){throw 'INITIAL_PAPER_DIAGNOSTIC_EXCEPTION_ONLY'}
    $runLock=Join-Path $root '.local/paper-lab.run.lock';$stream=$null
    try {
        $stream=[IO.File]::Open($runLock,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
        try {$stream.Lock(0,1)} catch {throw 'ACTIVE_SESSION_CANNOT_REGISTER_EXCEPTION'}
        & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
        $candidate=Read-LabGrant (Join-Path $root '.local/ibkr-paper-candidate.dpapi')
        if(-not [string]::Equals($candidate.account,$grant.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}
        $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
        if($listeners.Count -ne 1){throw 'TWS_SESSION_UNVERIFIED'}
        $tws=Get-Process -Id $listeners[0] -ErrorAction Stop
        $strategyPlan=$null
        if($Mode -ceq 'StrategyPaper') {
            if($RiskProfile -cne 'PAPER_EXPERIMENTAL_10_PERCENT' -or $StrategyVersion -cnotmatch '^[a-f0-9]{64}$' -or -not(Test-Path -LiteralPath $StrategyEvidencePath -PathType Leaf)){throw 'STRATEGY_PLAN_MISSING'}
            $priorPlanPath=$env:PYTHONPATH
            try {
                $env:PYTHONPATH=Join-Path $root 'python'
                $out=& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_strategy --validate-file $StrategyEvidencePath --version $StrategyVersion
                if($LASTEXITCODE -ne 0){throw 'STRATEGY_PLAN_BLOCKED'}
                $strategyPlan=$out | ConvertFrom-Json
            } finally {$env:PYTHONPATH=$priorPlanPath}
        }
        Write-Output 'Excepcion inicial Paper: EUR_ROW_ABSENT; saldo EUR UNKNOWN/null. NO afirma EUR=0. NO modifica ledger ni autoriza ordenes ni limpia emergencia.'
        Write-Output ('Un unico diagnostico, hasta 100 EUR / USD 150 / perdida simulada USD 10 / cierre iniciado a 60 s. Vigencia de excepcion: '+$ExceptionMinutes+' min; solo mismo proceso TWS.')
        $binding=Get-PaperAccountBinding
        $paper=Read-Host 'Tras comprobar aviso Paper y cuenta, escribe PAPER_IDENTITY_CHECKED'
        $absent=Read-Host 'Tras revisar Real FX Balance sin fila EUR y sin posiciones/ordenes, escribe EUR_ROW_ABSENT'
        $accepted=Read-Host 'Acepto expresamente incertidumbre de EUR solo para el diagnostico inicial; escribe ACCEPT_INITIAL_EUR_UNCERTAINTY'
        $typed=$binding.account
        if(-not [string]::Equals($typed,$grant.account,[StringComparison]::Ordinal) -or $paper -cne 'PAPER_IDENTITY_CHECKED' -or
           $absent -cne 'EUR_ROW_ABSENT' -or $accepted -cne 'ACCEPT_INITIAL_EUR_UNCERTAINTY'){throw 'EXPLICIT_EUR_UNCERTAINTY_ACCEPTANCE_REQUIRED'}
        $now=[DateTimeOffset]::UtcNow
        $exception=[ordered]@{schema_version=1;record_id=[Guid]::NewGuid().ToString('N');account=$grant.account;
            environment='PAPER_TRADING';live_enabled=$false;mode='ExecutionDiagnostics';scope='INITIAL_DIAGNOSTIC_EUR_ABSENCE';contract_id=12087792;
            tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();paper_checked=$true;identity_manual_match=$true;
            manual_uncertainty_accepted=$true;observed_state='EUR_ROW_ABSENT';max_experiments=1;max_quantity=100;max_notional_usd=150;
            diagnostic_loss_budget=10;max_hold_seconds=60;confirmed_at=$now.ToString('o');expires_at=$now.AddMinutes($ExceptionMinutes).ToString('o')}
        if($strategyPlan) {
            $exception.mode='StrategyPaper';$exception.scope='INITIAL_STRATEGY_PAPER_EUR_ABSENCE'
            $exception.risk_profile=$RiskProfile;$exception.strategy_version=$StrategyVersion;$exception.plan_hash=$strategyPlan.plan_hash
            $exception.review_session_id=$grant.session_id;$exception.execution_session_id=[Guid]::NewGuid().ToString('N')
            $exception.maximum_exposure=1;$exception.risk_ceiling=10;$exception.loss_allowance=20;$exception.diagnostic_loss_budget=0
        }
        Save-LabGrant $exception $eurExceptionPath
        Write-Output 'Aceptacion excepcional protegida registrada. Autorizacion de ejecucion y emergencia SIN CAMBIOS; falta revision expresa y autorizacion de ejecucion vigente.'
    } finally {$typed=$null;$entered=$null;if($stream){$stream.Dispose()}}
    return
}
if($Action -eq 'EmergencyStop') {
    New-Item -ItemType Directory -Force -Path (Join-Path $root '.local') | Out-Null
    [IO.File]::WriteAllText($stopPath,[DateTimeOffset]::UtcNow.ToString('o'))
    Write-Output 'Emergencia duradera: nuevas entradas bloqueadas. No se cancelan protecciones.';return
}
if($Action -eq 'Revoke') {
    $grant=Read-LabGrant;$grant.revoked=$true;$grant.emergency=$true
    $grant | Add-Member -NotePropertyName flat_reviewed_at -NotePropertyValue $null -Force
    $grant | Add-Member -NotePropertyName initial_eur_absence_reviewed_at -NotePropertyValue $null -Force
    $grant | Add-Member -NotePropertyName initial_eur_absence_reviewed_id -NotePropertyValue $null -Force
    Save-LabGrant $grant
    [IO.File]::WriteAllText($stopPath,[DateTimeOffset]::UtcNow.ToString('o'))
    Write-Output 'Sesion revocada: entradas bloqueadas; gestion limitada de posiciones propias conserva el alcance autorizado.';return
}
if($Action -eq 'Authorize') {
    if($Mode -ceq 'ExecutionDiagnostics' -and ($MaxExperiments -ne 1 -or $DiagnosticLossBudget -ne 10 -or
        $MaxNotionalUsd -gt 150 -or $MaxHoldSeconds -gt 60 -or $SessionMinutes -gt 30)) {throw 'SINGLE_DIAGNOSTIC_SCOPE_REQUIRED'}
    $exception=$null
    $strategyPlan=$null
    if($RiskProfile -eq 'PAPER_EXPERIMENTAL_10_PERCENT') {
        if($Mode -cne 'StrategyPaper' -or $AllowAbsentEurDiagnostic -or $DiagnosticLossBudget -ne 0 -or -not $Continuous){throw 'EXPERIMENTAL_CONTINUOUS_STRATEGY_PAPER_ONLY'}
        if([string]::IsNullOrWhiteSpace($StrategyVersion) -or [string]::IsNullOrWhiteSpace($StrategyEvidencePath) -or -not(Test-Path -LiteralPath $StrategyEvidencePath -PathType Leaf)){throw 'STRATEGY_PLAN_MISSING'}
        $planPrior=$env:PYTHONPATH
        try {
            $env:PYTHONPATH=Join-Path $root 'python'
            $planOutput=& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_strategy --validate-file $StrategyEvidencePath --version $StrategyVersion
            if($LASTEXITCODE -ne 0){throw ('STRATEGY_PLAN_BLOCKED: '+($planOutput | ConvertFrom-Json).error)}
            $strategyPlan=$planOutput | ConvertFrom-Json
        } finally {$env:PYTHONPATH=$planPrior}
    } elseif($Continuous){throw 'CONTINUOUS_REQUIRES_EXPERIMENTAL_STRATEGY_PAPER'}
    if(Test-Path -LiteralPath $grantPath) {
        $previous=Read-LabGrant
        if($AllowAbsentEurDiagnostic -or $AllowAbsentEurStrategy) {
            $exception=Read-EurException $previous
            if($AllowAbsentEurDiagnostic -and $exception.mode -cne 'ExecutionDiagnostics'){throw 'EUR_EXCEPTION_ACCOUNT_OR_MODE_MISMATCH'}
            if($AllowAbsentEurStrategy -and ($exception.mode -cne 'StrategyPaper' -or $exception.strategy_version -cne $StrategyVersion -or $exception.plan_hash -cne $strategyPlan.plan_hash)){throw 'EUR_EXCEPTION_STRATEGY_SESSION_MISMATCH'}
            if(-not $previous.revoked -or -not $previous.initial_eur_absence_reviewed_at -or
               $previous.initial_eur_absence_reviewed_id -cne $exception.record_id){throw 'REVOKE_AND_EXCEPTION_REVIEW_REQUIRED_BEFORE_NEW_SESSION'}
        } elseif(-not $previous.revoked -or -not $previous.flat_reviewed_at){throw 'REVOKE_AND_FLAT_REVIEW_REQUIRED_BEFORE_NEW_SESSION'}
    }
    if($AllowAbsentEurDiagnostic -and ($null -eq $exception -or $Mode -cne 'ExecutionDiagnostics' -or $DiagnosticLossBudget -ne 10 -or
       $MaxExperiments -ne 1 -or $MaxQuantity -gt 100 -or $MaxNotionalUsd -gt 150 -or $MaxHoldSeconds -gt 60)){throw 'EUR_EXCEPTION_EXECUTION_SCOPE_EXCEEDED'}
    $runLock=Join-Path $root '.local/paper-lab.run.lock'
    if(Test-Path -LiteralPath $runLock) {
        $stream=[IO.File]::Open($runLock,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
        try {try {$stream.Lock(0,1);$stream.Unlock(0,1)} catch {throw 'ACTIVE_SESSION_CANNOT_BE_REAUTHORIZED'}} finally {$stream.Dispose()}
    }
    if($DiagnosticLossBudget -lt 0 -or $DiagnosticLossBudget -gt 100 -or ($Mode -eq 'ExecutionDiagnostics' -and $DiagnosticLossBudget -lt 8.50) -or
       $MaxExperiments -lt 1 -or $MaxExperiments -gt 10 -or $MaxQuantity -le 0 -or $MaxQuantity -gt 100 -or
       $MaxNotionalUsd -le 0 -or $MaxNotionalUsd -gt 250 -or $MaxHoldSeconds -lt 1 -or $MaxHoldSeconds -gt 300 -or
       $SessionMinutes -lt 1 -or $SessionMinutes -gt 1440){throw 'EXPLICIT_BOUNDED_BUDGET_REQUIRED'}
    Write-Output ('Autorizaras '+$Mode+'; perdida diagnostica USD '+$DiagnosticLossBudget+'; maximo '+$MaxExperiments+' experimentos; '+$MaxQuantity+' EUR; nominal USD '+$MaxNotionalUsd+'; '+$MaxHoldSeconds+' s; '+$SessionMinutes+' min. Capital de estrategia USD 100/20 sin cambios. Live prohibido.')
    if($AllowAbsentEurDiagnostic){Write-Output 'Esta sesion acepta la incertidumbre EUR_ROW_ABSENT solo al inicio; saldo EUR permanece UNKNOWN. La excepcion puede vencer antes de esta sesion.'}
    Write-Output 'Verifica manualmente TWS Paper y permisos Forex. Solo para esta sesion Paper, desmarca Read-Only API manualmente. El script no cambia TWS.'
    $binding=Get-PaperAccountBinding
    $paper=Read-Host 'Tras verificar Paper, escribe PAPER_ORDERS_ALLOWED'
    $readOnly=Read-Host 'Tras verificar Read-Only API desmarcado, escribe READ_ONLY_DISABLED'
    $forex=Read-Host 'Tras verificar permiso Forex, escribe FOREX_PERMISSION'
    $confirm=Read-Host 'Para autorizar todo el alcance mostrado, escribe AUTHORIZE_SESSION'
    if($paper -cne 'PAPER_ORDERS_ALLOWED' -or $readOnly -cne 'READ_ONLY_DISABLED' -or $forex -cne 'FOREX_PERMISSION' -or $confirm -cne 'AUTHORIZE_SESSION'){throw 'MANUAL_EXECUTION_AUTHORIZATION_REQUIRED'}
    if($strategyPlan) {
        Write-Output ('Perfil '+$RiskProfile+'; estrategia '+$strategyPlan.plan.name+' / '+$StrategyVersion+'; plan hash '+$strategyPlan.plan_hash+'. Senales BUY causales, salida bracket o tiempo; sin cuota. Riesgo min(10% equity,USD10), capital USD100/20, exposicion 1x.')
        $strategyConsent=Read-Host 'Tras revisar estrategia, calendario y evidencia real de costos/restricciones del plan, escribe APPROVE_STRATEGY_PAPER_PLAN'
        if($strategyConsent -cne 'APPROVE_STRATEGY_PAPER_PLAN'){throw 'OWNER_STRATEGY_APPROVAL_REQUIRED'}
    }
    & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover # Handshake only; no orders or operational data.
    $candidateBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $root '.local/ibkr-paper-candidate.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $typed=$binding.account
    try {
        $candidate=[Text.Encoding]::UTF8.GetString($candidateBytes) | ConvertFrom-Json
        if(-not [string]::Equals($typed,$candidate.account,[StringComparison]::Ordinal) -or $candidate.port -ne $transport.port){throw 'EXACT_IDENTITY_MISMATCH'}
        $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
        if($listeners.Count -ne 1){throw 'TWS_SESSION_UNVERIFIED'}
        $tws=Get-Process -Id $listeners[0]
        $now=[DateTimeOffset]::UtcNow
        $record=[ordered]@{schema_version=1;account=$candidate.account;authorized=$true;environment='PAPER_TRADING';live_enabled=$false;
            paper_checked=$true;read_only_disabled_checked=$true;identity_manual_match=$true;forex_permission_checked=$true;
            host=$transport.host;port=$transport.port;client_id=82;tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();mode=$Mode;
            session_id=[Guid]::NewGuid().ToString('N');instruments=@('EUR/USD');order_types=@('LMT','STP');
            max_experiments=$MaxExperiments;max_quantity=$MaxQuantity;max_notional_usd=$MaxNotionalUsd;max_hold_seconds=$MaxHoldSeconds;
            diagnostic_loss_budget=$DiagnosticLossBudget;confirmed_at=$now.ToString('o');expires_at=$now.AddMinutes($SessionMinutes).ToString('o');
            emergency=$false;revoked=$false;manage_owned_positions_after_stop=$true}
        $record.strategy_versions=@($StrategyVersion);$record.strategy_requirements_verified=$false
        $record.risk_profile=$RiskProfile;$record.continuous=[bool]$Continuous
        if($strategyPlan) {
            $evidenceEnd=[DateTimeOffset]::Parse($strategyPlan.plan.evidence_expires_at)
            if($evidenceEnd -le $now){throw 'STRATEGY_EVIDENCE_EXPIRED'}
            if($evidenceEnd -lt [DateTimeOffset]::Parse($record.expires_at)){$record.expires_at=$evidenceEnd.ToString('o')}
            $record.strategy_requirements_verified=$true;$record.strategy_plan=$strategyPlan.plan
            $record.strategy_plan_hash=$strategyPlan.plan_hash;$record.execution_requirements=$strategyPlan.plan.execution_requirements
            $record.strategy_approved_at=$now.ToString('o')
        }
        if($AllowAbsentEurDiagnostic -or $AllowAbsentEurStrategy) {
            $exception=Read-EurException $previous
            if(-not [string]::Equals($record.account,$exception.account,[StringComparison]::Ordinal) -or $record.tws_pid -ne $exception.tws_pid -or
               $record.tws_start_filetime -cne $exception.tws_start_filetime){throw 'EUR_EXCEPTION_SESSION_CHANGED'}
            $record.eur_absence_exception_id=$exception.record_id
            if($AllowAbsentEurStrategy){$record.session_id=$exception.execution_session_id}
        }
        if(Test-Path -LiteralPath $stopPath){throw 'EMERGENCY_LATCHED_REVIEW_REQUIRED'}
        # A manual change to Read-Only invalidates the earlier read-only attestation.
        $readerPath=Join-Path $root '.local/ibkr-paper-authorized.dpapi'
        if(Test-Path -LiteralPath $readerPath) {
            $reader=Read-LabGrant $readerPath;$reader.authorized=$false;$reader.read_only_checked=$false
            Save-LabGrant $reader $readerPath
        }
        Save-LabGrant $record
        Write-Output ('Sesion protegida autorizada para ***'+$candidate.account.Substring($candidate.account.Length-4)+'. Aun no se han enviado ordenes; Run inicia el laboratorio.')
    } finally {$typed=$null;$entered=$null;[Array]::Clear($candidateBytes,0,$candidateBytes.Length)}
    return
}
if($Action -eq 'Status') {
    if(-not(Test-Path -LiteralPath $grantPath)){Write-Output 'Sin autorizacion de ejecucion Paper. Cero ordenes; Live bloqueado.';return}
    $grant=Read-LabGrant
    [pscustomobject]@{account=('***'+$grant.account.Substring($grant.account.Length-4));mode=$grant.mode;
        expiresAt=$grant.expires_at;expired=([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($grant.expires_at));
        revoked=$grant.revoked;emergency=($grant.emergency -or (Test-Path -LiteralPath $stopPath));
        diagnosticBudget=$grant.diagnostic_loss_budget;maxExperiments=$grant.max_experiments;maxQuantity=$grant.max_quantity;liveEnabled=$false;
        riskProfile=$grant.risk_profile;continuous=$grant.continuous;strategyVersions=$grant.strategy_versions;
        strategyEvidenceVerified=$grant.strategy_requirements_verified;
        eurExceptionRegistered=(Test-Path -LiteralPath $eurExceptionPath);eurExceptionBound=$grant.eur_absence_exception_id} | ConvertTo-Json
    return
}
if(-not(Test-Path -LiteralPath $grantPath)){throw 'PAPER_EXECUTION_NOT_AUTHORIZED'}
$priorPath=$env:PYTHONPATH;$priorDb=$env:TRADING_LAB_DB;$priorTradingDb=$env:TRADING_DB;$priorMigrate=$env:TRADING_DB_AUTO_MIGRATE;$priorPolicy=$env:TRADING_POLICY_PATH;$started=$false
try {
    $socket=New-Object Net.Sockets.TcpClient
    try {$pending=$socket.ConnectAsync('127.0.0.1',55433);$null=$pending.Wait(1000);$alreadyRunning=$socket.Connected}
    catch {$alreadyRunning=$false} finally {$socket.Dispose()}
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Start
    $started=-not $alreadyRunning
    & (Join-Path $root 'scripts/paper-lab-database.ps1') -Action Load
    $env:PYTHONPATH=Join-Path $root 'python'
    $env:TRADING_POLICY_PATH=Join-Path $root 'config/research-policy.json'
    if($Action -eq 'Review') {
        # Fresh owner permission for this READ-ONLY review, bound to the current TWS process.
        # The expired execution grant provides only the original account/session scope.
        $reviewGrant=Read-LabGrant
        & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
        $candidate=Read-LabGrant (Join-Path $root '.local/ibkr-paper-candidate.dpapi')
        if(-not [string]::Equals($candidate.account,$reviewGrant.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}
        $binding=Get-PaperAccountBinding
        $reviewTyped=$binding.account
        try {if(-not [string]::Equals($reviewTyped,$reviewGrant.account,[StringComparison]::Ordinal)){throw 'EXACT_IDENTITY_MISMATCH'}} finally {$reviewTyped=$null;$reviewEntered=$null}
        $reviewPaper=Read-Host 'Tras verificar que la sesion actual es Paper, escribe PAPER_REVIEW_CHECKED'
        if($reviewPaper -cne 'PAPER_REVIEW_CHECKED'){throw 'CURRENT_PAPER_REVIEW_ATTESTATION_REQUIRED'}
        $reviewListeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
        if($reviewListeners.Count -ne 1){throw 'TWS_SESSION_UNVERIFIED'}
        $reviewTws=Get-Process -Id $reviewListeners[0]
        $reviewArgs=@('--root',$root,'--review')
        if($AllowAbsentEurDiagnostic -or $AllowAbsentEurStrategy) {
            $reviewException=Read-EurException (Read-LabGrant)
            if($AllowAbsentEurStrategy -and $reviewException.mode -cne 'StrategyPaper' -or $AllowAbsentEurDiagnostic -and $reviewException.mode -cne 'ExecutionDiagnostics'){throw 'EUR_EXCEPTION_ACCOUNT_OR_MODE_MISMATCH'}
            $confirmation=Read-Host 'Revision EXCEPCIONAL inicial con EUR desconocido; solo si aceptas revisar y levantar emergencia, escribe REVIEW_INITIAL_EUR_UNCERTAINTY'
            if($confirmation -cne 'REVIEW_INITIAL_EUR_UNCERTAINTY'){throw 'OWNER_EXCEPTION_REVIEW_REQUIRED'}
            $reviewArgs+='--allow-absent-eur'
        } else {
            $confirmation=Read-Host 'Solo para revisar identidad, posiciones, journal y costos antes de limpiar emergencia, escribe REVIEW_FLAT_PAPER'
            if($confirmation -cne 'REVIEW_FLAT_PAPER'){throw 'OWNER_REVIEW_REQUIRED'}
        }
        $reviewGrant=Read-LabGrant;$reviewNow=[DateTimeOffset]::UtcNow
        $reviewPermit=[ordered]@{schema_version=1;scope='OWNER_REVIEW_CLEAR_EMERGENCY';record_id=[Guid]::NewGuid().ToString('N');
            environment='PAPER_TRADING';live_enabled=$false;account=$reviewGrant.account;session_id=$reviewGrant.session_id;
            tws_pid=$reviewTws.Id;tws_start_filetime=$reviewTws.StartTime.ToFileTimeUtc().ToString();current_paper_review_attested=$true;
            confirmed_at=$reviewNow.ToString('o');expires_at=$reviewNow.AddMinutes(2).ToString('o');exception_id=$null}
        if($AllowAbsentEurDiagnostic -or $AllowAbsentEurStrategy){$reviewPermit.exception_id=$reviewException.record_id}
        Save-LabGrant $reviewPermit $reviewPermitPath
        try {$reviewOutput=& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_lab_runner @reviewArgs}
        finally {if(Test-Path -LiteralPath $reviewPermitPath){Remove-Item -LiteralPath $reviewPermitPath}}
        Write-Output $reviewOutput
        if($LASTEXITCODE -eq 0) {
            $reviewed=Read-LabGrant
            $reviewResult=$reviewOutput | ConvertFrom-Json
            if($reviewResult.state -ceq 'INITIAL_BASELINE_EXCEPTION_REVIEWED') {
                $exception=Read-EurException $reviewed
                if($reviewResult.exception_id -cne $exception.record_id){throw 'EUR_EXCEPTION_REVIEW_MISMATCH'}
                $reviewed | Add-Member -NotePropertyName initial_eur_absence_reviewed_at -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString('o')) -Force
                $reviewed | Add-Member -NotePropertyName initial_eur_absence_reviewed_id -NotePropertyValue $exception.record_id -Force
                $reviewed | Add-Member -NotePropertyName flat_reviewed_at -NotePropertyValue $null -Force
            } else {
                if($reviewResult.state -cne 'FLAT_REVIEWED'){throw 'OWNER_REVIEW_RESULT_UNVERIFIED'}
                $reviewed | Add-Member -NotePropertyName flat_reviewed_at -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString('o')) -Force
            }
            Save-LabGrant $reviewed
            if(Test-Path -LiteralPath $stopPath){Remove-Item -LiteralPath $stopPath}
            if($clearAutoEmergency -and $reviewResult.state -ceq 'FLAT_REVIEWED') {
                $autoStopPath=Join-Path $root '.local/paper-auto.stop'
                if(Test-Path -LiteralPath $autoStopPath){Remove-Item -LiteralPath $autoStopPath}
            }
        }
    } elseif($Action -eq 'Diagnose') {
        & (Join-Path $root 'scripts/paper-identity.ps1') -Action Discover
        $diagnoseArgs=@('--root',$root)
        if($StrategyMarketEvidence){$diagnoseArgs+='--strategy-market'}
        & (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_lab_diagnostics @diagnoseArgs
    } else {& (Join-Path $root '.venv/Scripts/python.exe') -m trading_agent.paper_lab_runner --root $root --execution-mode $ExecutionMode}
    if($LASTEXITCODE -ne 0){throw 'PAPER_LAB_SUSPENDED_INSPECT_JOURNAL'}
} finally {
    if($started){& (Join-Path $root 'scripts/paper-database.ps1') -Action Stop}
    $env:PYTHONPATH=$priorPath;$env:TRADING_LAB_DB=$priorDb
    $env:TRADING_DB=$priorTradingDb;$env:TRADING_DB_AUTO_MIGRATE=$priorMigrate
    $env:TRADING_POLICY_PATH=$priorPolicy
}
