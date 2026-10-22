param(
    [ValidateSet('Prepare','Trust','Verify','Run','Stop','Cleanup')][string]$Mode = 'Prepare',
    [string]$RunId,
    [string]$Dotnet = './tmp/m011/dotnet/dotnet.exe',
    [string]$PostgresBin = 'C:/Program Files/PostgreSQL/17/bin'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Windows DPAPI and CurrentUser trust are required.' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if ((Get-Location).Path -cne $root) { throw 'Run from repository root.' }
if ($Mode -eq 'Prepare' -and !$RunId) { $RunId = [guid]::NewGuid().ToString('N') }
if ($RunId -cnotmatch '^[a-f0-9]{32}$') { throw 'An exact owned RunId is required.' }
$runs = Join-Path $root 'tmp/m014b-local-pilot/runs'
$run = [IO.Path]::GetFullPath((Join-Path $runs $RunId))
if (![string]::Equals([IO.Path]::GetDirectoryName($run),[IO.Path]::GetFullPath($runs),[StringComparison]::OrdinalIgnoreCase)) { throw 'Run containment failed.' }
$data = Join-Path $run 'data'
$dotnetExe = (Get-Command $Dotnet -ErrorAction Stop).Source
$pg = (Resolve-Path $PostgresBin).Path
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
function Confirm-Local([string]$message) {
    Add-Type -AssemblyName System.Windows.Forms
    $answer = [Windows.Forms.MessageBox]::Show($message,'TradingAgent local pilot approval',[Windows.Forms.MessageBoxButtons]::YesNo,[Windows.Forms.MessageBoxIcon]::Question,[Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($answer -ne [Windows.Forms.DialogResult]::Yes) { throw 'LOCAL_APPROVAL_DECLINED; no action performed.' }
}
function Assert-Owned {
    if (!(Test-Path -LiteralPath (Join-Path $run 'owner.json'))) { throw 'Owned run manifest missing.' }
    $script:owner = Get-Content -LiteralPath (Join-Path $run 'owner.json') -Raw | ConvertFrom-Json
    if ($owner.runId -cne $RunId -or $owner.ownerSid -cne $sid.Value -or $owner.root -cne $run -or $owner.marker -cne ('m012_disposable_'+$RunId)) { throw 'Run ownership rejected.' }
    # Reject reparse points on every path component and below the run before mutations/deletion.
    $ancestor = $run
    while ($ancestor) {
        if ((Get-Item -LiteralPath $ancestor).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked run path rejected.' }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    if (@(Get-ChildItem -LiteralPath $run -Recurse -Force | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count) { throw 'Linked child rejected.' }
    if (Test-Path -LiteralPath (Join-Path $data 'PG_VERSION')) {
        if ((Get-Content -LiteralPath (Join-Path $data 'PG_VERSION') -Raw).Trim() -cne '17') { throw 'Unexpected cluster version.' }
        if (!(Select-String -LiteralPath (Join-Path $data 'postgresql.conf') -SimpleMatch "cluster_name='$($owner.marker)'" -Quiet)) { throw 'Cluster ownership marker rejected.' }
    }
}
function Start-OwnedPostgres {
    Assert-Owned
    & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
    if ($LASTEXITCODE -eq 0) { throw 'Cluster already running; do not attach implicitly.' }
    # File redirection prevents the daemon inheriting PowerShell5 pipeline handles.
    # Wait for pg_ctl itself, never for the background PostgreSQL process tree.
    $arguments = '-D "'+$data+'" -l "'+(Join-Path $run 'postgres.log')+'" -w start'
    $controller = Start-Process -FilePath (Join-Path $pg 'pg_ctl.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'pgctl-start.log') -RedirectStandardError (Join-Path $run 'pgctl-start-error.log')
    try {
        $null = $controller.Handle # Retain the exit handle on Windows PowerShell5.
        if (!$controller.WaitForExit(45000) -or $controller.ExitCode -ne 0) { throw 'Owned PostgreSQL startup failed.' }
    } finally { $controller.Dispose() }
}
function Stop-OwnedPostgres {
    Assert-Owned
    & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
    if ($LASTEXITCODE -eq 0) {
        & (Join-Path $pg 'pg_ctl.exe') -D $data -m fast -w stop | Out-Null
        if ($LASTEXITCODE) { throw 'Owned PostgreSQL shutdown failed; resources preserved.' }
    }
}
function New-Password {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes); return [BitConverter]::ToString($bytes).Replace('-','') } finally { $rng.Dispose() }
}
function Unprotect-Local([string]$cipher) {
    $secure = ConvertTo-SecureString $cipher
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
}
$environmentKeys = @('M012_TEST_PORT','M012_BOOTSTRAP_PASSWORD','M012_CLUSTER_MARKER','M014B_LOCAL_PILOT_RUN_DIRECTORY','M014B_LOCAL_MIGRATION_PASSWORD','M014B_LOCAL_RUNTIME_PASSWORD','M014B_LOCAL_ISSUER_PASSWORD','M014B_LOCAL_TLS_PASSWORD')
$previous = @{}; foreach($name in $environmentKeys){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    if ($Mode -eq 'Prepare') {
        if ((& $dotnetExe --version) -cne '10.0.402') { throw 'Exact SDK 10.0.402 required.' }
        if ((& (Join-Path $pg 'postgres.exe') --version) -notmatch 'PostgreSQL\) 17\.') { throw 'PostgreSQL 17 required.' }
        if (Test-Path -LiteralPath $run) { throw 'Prepare never overwrites a run.' }
        New-Item -ItemType Directory -Force -Path $runs | Out-Null
        New-Item -ItemType Directory -Path $run | Out-Null
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
        Set-Acl -LiteralPath $run -AclObject $acl
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)
        $listener.Start(); $port=$listener.LocalEndpoint.Port; $listener.Stop()
        if ($port -lt 20000 -or $port -in @(55433,55434)) { throw 'Unsafe dynamic PostgreSQL port; prepare another run.' }
        $listener.Start(); $webPort=$listener.LocalEndpoint.Port; $listener.Stop()
        if ($webPort -lt 20000 -or $webPort -eq $port) { throw 'Unsafe HTTPS port.' }
        $owner = [ordered]@{runId=$RunId;ownerSid=$sid.Value;root=$run;marker=('m012_disposable_'+$RunId);sqlPort=$port;origin="https://127.0.0.1:$webPort/"}
        $owner | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'owner.json') -Encoding UTF8
        $secrets = @{bootstrap=(New-Password);migration=(New-Password);runtime=(New-Password);issuer=(New-Password);tls=(New-Password)}
        $secure = ConvertTo-SecureString ($secrets | ConvertTo-Json -Compress) -AsPlainText -Force
        try { ConvertFrom-SecureString $secure | Set-Content -LiteralPath (Join-Path $run 'secrets.dpapi') -Encoding ASCII } finally { $secure.Dispose() }
        $passwordFile=Join-Path $run 'init-password'
        try {
            [IO.File]::WriteAllText($passwordFile,$secrets.bootstrap,[Text.Encoding]::ASCII)
            & (Join-Path $pg 'initdb.exe') -D $data -U postgres -A scram-sha-256 --pwfile=$passwordFile --encoding=UTF8 --locale=C *> (Join-Path $run 'init.log')
            if ($LASTEXITCODE) { throw 'Disposable initdb failed.' }
        } finally { Remove-Item -LiteralPath $passwordFile -ErrorAction SilentlyContinue }
        Add-Content -LiteralPath (Join-Path $data 'postgresql.conf') -Value "`nlisten_addresses='127.0.0.1'`nport=$port`ncluster_name='$($owner.marker)'`nlog_statement='none'`nlog_min_error_statement='panic'`nlog_parameter_max_length_on_error=0`n"
        Start-OwnedPostgres
        try {
            $env:M012_TEST_PORT="$port"; $env:M012_CLUSTER_MARKER=$owner.marker; $env:M012_BOOTSTRAP_PASSWORD=$secrets.bootstrap
            $env:M014B_LOCAL_PILOT_RUN_DIRECTORY=$run
            $env:M014B_LOCAL_MIGRATION_PASSWORD=$secrets.migration; $env:M014B_LOCAL_RUNTIME_PASSWORD=$secrets.runtime; $env:M014B_LOCAL_ISSUER_PASSWORD=$secrets.issuer; $env:M014B_LOCAL_TLS_PASSWORD=$secrets.tls
            & $dotnetExe (Join-Path $PSScriptRoot 'BrowserFixture/bin/Release/net10.0/BrowserFixture.dll') --prepare-local-pilot *> (Join-Path $run 'prepare.log')
            if ($LASTEXITCODE) { throw 'Preparation failed; inspect code locally, preserve protected logs.' }
        } finally { Stop-OwnedPostgres }
        Write-Output "PREPARED RunId=$RunId; SQL stopped; root NOT trusted; no hosted requests."
    } else {
        Assert-Owned
        $prepared = $null
        if (Test-Path -LiteralPath (Join-Path $run 'prepared.json')) { $prepared=Get-Content -LiteralPath (Join-Path $run 'prepared.json') -Raw | ConvertFrom-Json }
        if ($Mode -in @('Trust','Run') -and $null -eq $prepared) { throw 'Preparation must complete before trust or hosted execution.' }
        if ($Mode -eq 'Verify') {
            $secret=Unprotect-Local ((Get-Content -LiteralPath (Join-Path $run 'secrets.dpapi') -Raw).Trim()) | ConvertFrom-Json
            $values=@{M012_TEST_PORT="$($owner.sqlPort)";M012_CLUSTER_MARKER=$owner.marker;M012_BOOTSTRAP_PASSWORD=$secret.bootstrap;M014B_SYNTHETIC_BROWSER_FIXTURE='YES';M014B_LOCAL_TLS_SMOKE='YES';M012_RESULTS_DIRECTORY=(Join-Path $root 'artifacts/m014b')}
            foreach($name in $values.Keys){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process');[Environment]::SetEnvironmentVariable($name,$values[$name],'Process')}
            Start-OwnedPostgres
            try {
                foreach($check in @('build/auth-pilot/check.ps1','build/auth/check.ps1','build/identity/check.ps1','build/web/check.ps1','build/react-bff/check.ps1')) {
                    & (Join-Path $root $check) -Dotnet $dotnetExe
                }
                $env:M012_RESULTS_DIRECTORY=Join-Path $root 'artifacts/m014b'
                & $dotnetExe (Join-Path $PSScriptRoot 'BrowserFixture/bin/Release/net10.0/BrowserFixture.dll') $root
                if($LASTEXITCODE){throw 'Synthetic TLS smoke failed.'}
            } finally {Stop-OwnedPostgres}
        } elseif ($Mode -eq 'Trust') {
            $cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2((Join-Path $run 'root.cer'))
            try {
                if ($cert.Thumbprint -cne $prepared.rootThumbprint) { throw 'Root identity mismatch.' }
                $store=New-Object Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser')
                try {
                    $store.Open('ReadWrite')
                    if ($store.Certificates.Find('FindByThumbprint',$cert.Thumbprint,$false).Count) { throw 'Root already exists; no ownership of prior trust inferred.' }
                    Confirm-Local "Install ONLY this public local development CA in CurrentUser Root?`nThumbprint: $($cert.Thumbprint)`nValid for four hours. No LocalMachine store, private key or Supabase call. Cleanup removes this exact owned root."
                    $cert.Thumbprint | Set-Content -LiteralPath (Join-Path $run 'trust-owned.txt') -Encoding ASCII
                    $store.Add($cert)
                } finally { $store.Dispose() }
            } finally { $cert.Dispose() }
            Write-Output 'CURRENT_USER_OWNED_ROOT_INSTALLED_AFTER_LOCAL_CONFIRMATION'
        } elseif ($Mode -eq 'Run') {
            if (!(Test-Path -LiteralPath (Join-Path $run 'trust-owned.txt'))) { throw 'Trusted certificate approval is pending.' }
            Confirm-Local "Authorize ONE local React/BFF pilot against ocwabwmzhpedyxlkjpje Auth Dev?`nOrigin: $($owner.origin)`nPassword/TOTP only in that browser. Existing unverified factor must stop flow. No enrollment, DELETE, recovery, grants or financial access. Maximum20minutes. SQL authorization is EMPTY; AAL2 cannot create an authorized application session."
            $public=Get-Content -LiteralPath (Join-Path $root 'tmp/m013b/hosted-development.public.json') -Raw | ConvertFrom-Json
            if ($public.confirmedReference -cne 'ocwabwmzhpedyxlkjpje' -or $public.project.TrimEnd('/') -cne 'https://ocwabwmzhpedyxlkjpje.supabase.co' -or !$public.publishableKey.StartsWith('sb_publishable_')) { throw 'Exact development public configuration required.' }
            $secret=Unprotect-Local ((Get-Content -LiteralPath (Join-Path $run 'secrets.dpapi') -Raw).Trim()) | ConvertFrom-Json
            $settings=@{INTERACTIVE_APPROVAL='APPROVED_HOSTED_AUTH_DEV_NO_TRADE';PROJECT_REF='ocwabwmzhpedyxlkjpje';PROJECT_URL='https://ocwabwmzhpedyxlkjpje.supabase.co/';PUBLISHABLE_KEY=$public.publishableKey;ORIGIN=$owner.origin;SQL_PORT="$($owner.sqlPort)";SQL_DATABASE=$prepared.database;RUNTIME_USER=$prepared.runtimeUser;RUNTIME_PASSWORD=$secret.runtime;ISSUER_USER=$prepared.issuerUser;ISSUER_PASSWORD=$secret.issuer;TLS_PFX=(Join-Path $run 'loopback.pfx');TLS_PASSWORD=$secret.tls;REACT_DIST=(Join-Path $root 'frontend-react/dist');STOP_FILE=(Join-Path $run 'stop');DIAGNOSTIC_FILE=(Join-Path $run 'diagnostic.jsonl')}
            foreach($key in $settings.Keys){$name='M014B_B2_'+$key;$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process');[Environment]::SetEnvironmentVariable($name,$settings[$key],'Process')}
            Remove-Item -LiteralPath (Join-Path $run 'stop') -ErrorAction SilentlyContinue
            $active = Join-Path $run 'runner-active'
            $lease = [IO.File]::Open($active,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            $lease.Dispose()
            try {
                Start-OwnedPostgres
                Write-Output "LOCAL_BFF_STARTING $($owner.origin) OFFLINE / NO_TRADE"
                & $dotnetExe (Join-Path $PSScriptRoot 'BrowserFixture/bin/Release/net10.0/BrowserFixture.dll') --hosted-development
                if ($LASTEXITCODE) { throw 'Hosted runner stopped; do not infer login success.' }
            } finally { Stop-OwnedPostgres; Remove-Item -LiteralPath $active -ErrorAction SilentlyContinue }
        } elseif ($Mode -eq 'Stop') {
            New-Item -ItemType File -Force -Path (Join-Path $run 'stop') | Out-Null
            Write-Output 'Owned BFF stop requested; its launcher will stop its PostgreSQL.'
        } elseif ($Mode -eq 'Cleanup') {
            if (Test-Path -LiteralPath (Join-Path $run 'runner-active')) { throw 'Runner has not confirmed exit; cleanup denied.' }
            if (!(Test-Path -LiteralPath (Join-Path $run 'stop'))) { throw 'Request Stop and wait for the runner to exit before Cleanup.' }
            & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
            if ($LASTEXITCODE -eq 0) { throw 'Owned cluster still running; wait for orderly shutdown.' }
            if (Test-Path -LiteralPath (Join-Path $run 'trust-owned.txt')) {
                if ($null -eq $prepared) { throw 'Trust ownership cannot be established.' }
                $thumb=(Get-Content -LiteralPath (Join-Path $run 'trust-owned.txt') -Raw).Trim()
                if ($thumb -cne $prepared.rootThumbprint) { throw 'Trust receipt mismatch.' }
                Confirm-Local "Remove ONLY this owned CurrentUser trust root and owned disposable run?`nThumbprint: $thumb`nRunId: $RunId`nNo other certificate, database or directory will be removed."
                $store=New-Object Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser')
                try {$store.Open('ReadWrite');foreach($cert in $store.Certificates.Find('FindByThumbprint',$thumb,$false)){$store.Remove($cert)}}finally{$store.Dispose()}
            }
            Assert-Owned
            Remove-Item -LiteralPath $run -Recurse -Force
            Write-Output 'OWNED_DISPOSABLE_RUN_REMOVED'
        }
    }
} finally {
    foreach($name in $previous.Keys){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
    $secrets=$null; $secret=$null; $settings=$null
}
