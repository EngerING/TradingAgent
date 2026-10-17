param([ValidateSet('Discover','Authorize','Load','Status')][string]$Action='Discover')
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'ibkr-session.ps1')
$candidatePath=Join-Path $repoRoot '.local/ibkr-paper-candidate.dpapi'
$authorizedPath=Join-Path $repoRoot '.local/ibkr-paper-authorized.dpapi'
Add-Type -AssemblyName System.Security

function Read-SealedRecord([string]$path) {
    if(-not (Test-Path -LiteralPath $path)){throw 'LOCAL_PAPER_IDENTITY_MISSING'}
    try {
        $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($path),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $record=[Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
        return $record
    } catch {throw 'LOCAL_PAPER_IDENTITY_UNREADABLE'}
    finally {if($plain){[Array]::Clear($plain,0,$plain.Length)}}
}
function Discover-Identity {
    $priorPath=$env:PYTHONPATH
    try {
        $env:PYTHONPATH=Join-Path $repoRoot 'python'
        $result=& (Join-Path $repoRoot '.venv/Scripts/python.exe') -m trading_agent.paper_identity
        if($LASTEXITCODE -ne 0){throw 'PAPER_IDENTITY_DISCOVERY_FAILED'}
        $summary=$result | ConvertFrom-Json
        Write-Output ('Cuenta descubierta: '+$summary.masked_account+'; handshake verificado; aun no autorizada.')
    } finally {$env:PYTHONPATH=$priorPath}
}
function Validate-Authorization($record) {
    if($record.schema_version -ne 1 -or $record.authorized -ne $true -or $record.paper_checked -ne $true -or
        $record.read_only_checked -ne $true -or $record.identity_manual_match -ne $true -or $record.port -ne $transport.port -or
        $record.account -cnotmatch '\ADU(?:R)?[0-9]+\z'){throw 'PAPER_MANUAL_VERIFICATION_REQUIRED'}
    $at=[DateTimeOffset]::Parse($record.confirmed_at)
    if($at -gt [DateTimeOffset]::UtcNow.AddSeconds(5) -or $at -lt [DateTimeOffset]::UtcNow.AddHours(-24)) {
        throw 'PAPER_MANUAL_VERIFICATION_EXPIRED'
    }
}

if($Action -eq 'Discover') {Discover-Identity}
elseif($Action -eq 'Authorize') {
    # No flags, command arguments or discovery suffix can bypass these manual checks.
    Write-Output 'En TWS verifica modo Paper Trading y la identidad completa; API > Settings: puerto configurado y Read-Only API marcado.'
    $binding=$null
    if((Test-Path -LiteralPath (Join-Path $repoRoot '.local/ibkr-account-binding.dpapi')) -or
       (Test-Path -LiteralPath (Join-Path $repoRoot '.local/paper-lab-authorization.dpapi')) -or
       (Test-Path -LiteralPath $authorizedPath)){$binding=Get-PaperAccountBinding}
    else {$entered=Read-Host 'Primera vinculacion: cuenta COMPLETA Paper (entrada oculta)' -AsSecureString}
    $paper=Read-Host 'Solo si verificaste modo Paper en TWS, escribe PAPER'
    $readOnly=Read-Host 'Solo si verificaste Read-Only API marcado y puerto configurado, escribe READ_ONLY'
    if($paper -cne 'PAPER' -or $readOnly -cne 'READ_ONLY'){throw 'PAPER_MANUAL_VERIFICATION_REQUIRED'}
    Discover-Identity # Fresh managedAccounts after the manual UI check.
    $candidate=Read-SealedRecord $candidatePath
    $typed=if($binding){$binding.account}else{([pscredential]::new('local-verification',$entered)).GetNetworkCredential().Password}
    try {
        if(-not [string]::Equals($typed,$candidate.account,[StringComparison]::Ordinal)){throw 'PAPER_ACCOUNT_EXACT_MATCH_FAILED'}
        if($candidate.authorized -ne $false -or $candidate.port -ne $transport.port -or $candidate.schema_version -ne 1 -or
            $candidate.account -cnotmatch '\ADU(?:R)?[0-9]+\z'){throw 'INVALID_PAPER_CANDIDATE'}
        $record=[ordered]@{schema_version=1;account=$candidate.account;authorized=$true;paper_checked=$true;read_only_checked=$true;
            identity_manual_match=$true;environment='PAPER_TRADING';live_enabled=$false;host=$transport.host;port=$transport.port;confirmed_at=[DateTimeOffset]::UtcNow.ToString('o');
            observed_at=$candidate.observed_at;server_version=$candidate.server_version}
        $bytes=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Compress))
        $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $tempPath=$authorizedPath+'.tmp'
        [IO.File]::WriteAllBytes($tempPath,$sealed)
        Move-Item -LiteralPath $tempPath -Destination $authorizedPath -Force
        Write-Output ('Cuenta autorizada localmente: ***'+$candidate.account.Substring($candidate.account.Length-4)+'. Vigencia manual: 24 horas; repetir si cambias/reinicias la sesion TWS.')
        Write-Output 'No se consultaron saldos, mercado ni se enviaron ordenes.'
    } finally {$typed=$null;$entered=$null;if($bytes){[Array]::Clear($bytes,0,$bytes.Length)}}
} elseif($Action -eq 'Load') {
    # Fail closed even if a caller already had environment attestations set.
    foreach($name in @('IBKR_PAPER_ACCOUNT','IBKR_PAPER_ATTESTED','IBKR_READ_ONLY_ATTESTED','IBKR_VERIFIED_TWS_PORT','IBKR_HOST','IBKR_CONFIGURED_ENDPOINT','IBKR_DATA_ENABLED')) {
        [Environment]::SetEnvironmentVariable($name,$null)
    }
    $binding=Get-PaperAccountBinding
    $record=Read-SealedRecord $authorizedPath;Validate-Authorization $record
    if(-not [string]::Equals($binding.account,$record.account,[StringComparison]::Ordinal)){throw 'ACCOUNT_BINDING_HARD_STOP'}
    $env:IBKR_PAPER_ACCOUNT=$record.account
    $env:IBKR_PAPER_ATTESTED='true';$env:IBKR_READ_ONLY_ATTESTED='true'
    $env:IBKR_HOST=$transport.host;$env:IBKR_PORT=[string]$transport.port;$env:IBKR_VERIFIED_TWS_PORT=[string]$transport.port;$env:IBKR_CONFIGURED_ENDPOINT='true';$env:LIVE_TRADING='false'
    Write-Output ('Configuracion local cargada para ***'+$record.account.Substring($record.account.Length-4)+'. Colector aun deshabilitado.')
} else {
    if(Test-Path -LiteralPath $authorizedPath) {
        $record=Read-SealedRecord $authorizedPath;Validate-Authorization $record
        Write-Output ('Autorizacion manual vigente: ***'+$record.account.Substring($record.account.Length-4))
    } else {Write-Output 'Sin autorizacion manual: lecturas operativas bloqueadas.'}
}
