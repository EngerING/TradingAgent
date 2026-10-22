param(
    [ValidateSet('Start','Foreground','Status','Stop')][string]$Mode = 'Start',
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{32}$')][string]$RunId,
    [string]$Dotnet = './tmp/m011/dotnet/dotnet.exe',
    [string]$PostgresBin = 'C:/Program Files/PostgreSQL/17/bin'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$runs=[IO.Path]::GetFullPath((Join-Path $root 'tmp/m014b-local-pilot/runs'))
$run=[IO.Path]::GetFullPath((Join-Path $runs $RunId))
$data=Join-Path $run 'data'
$stateFile=Join-Path $run 'persistent-state.json'
$stopFile=Join-Path $run 'persistent-stop'
$dotnetPath=$Dotnet
if(![IO.Path]::IsPathRooted($dotnetPath)){$dotnetPath=Join-Path $root $dotnetPath}
$dotnetExe=(Get-Command $dotnetPath -ErrorAction Stop).Source
$pg=(Resolve-Path $PostgresBin).Path
$previous=@{}
$lease=$null
$started=$false
$ownedValidated=$false
function Assert-Owned {
    if ([IO.Path]::GetDirectoryName($run) -cne $runs) {throw 'RUN_CONTAINMENT_REJECTED'}
    $part=$run
    while($part){if((Get-Item -LiteralPath $part).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_PATH_REJECTED'};$part=[IO.Path]::GetDirectoryName($part)}
    if(@(Get-ChildItem -LiteralPath $run -Recurse -Force | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'LINKED_CHILD_REJECTED'}
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl=Get-Acl -LiteralPath $run
    if(!$acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $sid.Value){throw 'PRIVATE_OWNER_ACL_REQUIRED'}
    foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -cne $sid.Value){throw 'PRIVATE_OWNER_ACL_REQUIRED'}}
    $script:owner=Get-Content -LiteralPath (Join-Path $run 'owner.json') -Raw | ConvertFrom-Json
    $script:prepared=Get-Content -LiteralPath (Join-Path $run 'prepared.json') -Raw | ConvertFrom-Json
    if($owner.runId -cne $RunId -or $owner.root -cne $run -or $owner.ownerSid -cne $sid.Value -or $owner.marker -cne ('m012_disposable_'+$RunId)){throw 'OWNERSHIP_REJECTED'}
    if((Get-Content -LiteralPath (Join-Path $data 'PG_VERSION') -Raw).Trim() -cne '17' -or !(Select-String -LiteralPath (Join-Path $data 'postgresql.conf') -SimpleMatch "cluster_name='$($owner.marker)'" -Quiet)){throw 'CLUSTER_IDENTITY_REJECTED'}
    $origin=[uri]$owner.origin
    if($origin.Scheme -cne 'https' -or $origin.Host -cne '127.0.0.1' -or $origin.Port -lt 20000 -or $origin.AbsolutePath -cne '/' -or $origin.UserInfo -or $origin.Query -or $origin.Fragment){throw 'ORIGIN_REJECTED'}
}
function Status {
    if(!(Test-Path -LiteralPath $stateFile)){Write-Output 'STATE=STOPPED';return}
    $s=Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if($s.state -cne 'READY' -or $s.localChecksOnly -ne $true -or $s.origin -cne $owner.origin){Write-Output 'STATE=STOPPED';return}
    $process=Get-Process -Id $s.pid -ErrorAction SilentlyContinue
    if(!$process -or $process.StartTime.ToUniversalTime() -ne [datetime]::Parse($s.startedAtUtc).ToUniversalTime()){Write-Output 'STATE=STOPPED';return}
    $health=Invoke-RestMethod -Uri ($owner.origin+'health') -TimeoutSec 5
    $config=Invoke-RestMethod -Uri ($owner.origin+'bff/config') -TimeoutSec 5
    if($health.status -cne 'ok' -or $config.profile -cne 'HOSTED_DEVELOPMENT_AUTH' -or $config.mode -cne 'OFFLINE' -or $config.decision -cne 'NO_TRADE' -or $config.executionAuthorized -ne $false){throw 'HEALTH_PROFILE_REJECTED'}
    Write-Output "URL=$($owner.origin) PID=$($s.pid) STATE=READY LOGIN_DISABLED OFFLINE / NO_TRADE"
}
function Unprotect([string]$cipher) {
    $secure=ConvertTo-SecureString $cipher
    $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try{return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$secure.Dispose()}
}
try {
    Assert-Owned
    $ownedValidated=$true
    if($Mode -eq 'Status'){Status;exit 0}
    if($Mode -eq 'Stop'){
        # No kill-by-name/PID/port. The owned runner observes only this exact stop file.
        New-Item -ItemType File -Force -Path $stopFile | Out-Null
        for($i=0;$i -lt 60;$i++){
            $hostStopped=!(Test-Path -LiteralPath $stateFile) -or (Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json).state -ceq 'STOPPED'
            & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
            if($hostStopped -and $LASTEXITCODE -ne 0){break}
            Start-Sleep -Milliseconds 500
        }
        & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
        if($LASTEXITCODE -eq 0){throw 'OWNED_SHUTDOWN_PENDING; DO_NOT_KILL_OTHER_PROCESSES'}
        Write-Output 'STATE=STOPPED; OWNED_POSTGRES_STOPPED';exit 0
    }
    if($Mode -eq 'Start'){
        if(Test-Path -LiteralPath $stateFile){
            $s=Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            $existing=Get-Process -Id $s.pid -ErrorAction SilentlyContinue
            if($s.state -ceq 'READY' -and $existing -and $existing.StartTime.ToUniversalTime() -eq [datetime]::Parse($s.startedAtUtc).ToUniversalTime()){Status;exit 0}
        }
        if(Get-NetTCPConnection -State Listen -LocalPort ([uri]$owner.origin).Port -ErrorAction SilentlyContinue){throw 'HTTPS_PORT_OCCUPIED; NO_PROCESS_WILL_BE_STOPPED'}
        $probe=[IO.File]::Open((Join-Path $run 'persistent-lease'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue}finally{$probe.Dispose()}
        # User requested a visible dedicated console. No credentials in its command line.
        # Start-Process on Windows creates a separate console; no redirected Codex pipes.
        $args='-NoLogo -NoProfile -File "'+$PSCommandPath+'" -Mode Foreground -RunId '+$RunId+' -Dotnet "'+$dotnetExe+'" -PostgresBin "'+$pg+'"'
        $terminal=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $args -WorkingDirectory $root -WindowStyle Normal -PassThru
        try {
            for($i=0;$i -lt 120;$i++){
                if(Test-Path -LiteralPath $stateFile){
                    $s=Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
                    if($s.state -ceq 'FAILED'){throw 'DEDICATED_PREFLIGHT_FAILED'}
                    $readyProcess=Get-Process -Id $s.pid -ErrorAction SilentlyContinue
                    if($s.state -ceq 'READY' -and $readyProcess -and $readyProcess.StartTime.ToUniversalTime() -eq [datetime]::Parse($s.startedAtUtc).ToUniversalTime()){Status;exit 0}
                }
                if($terminal.HasExited){throw 'DEDICATED_TERMINAL_EXITED'}
                Start-Sleep -Milliseconds 500
            }
            Write-Output "TERMINAL_PID=$($terminal.Id) STATE=STARTING; CHECK_DEDICATED_TERMINAL"
        } finally {$terminal.Dispose()}
        exit 0
    }
    $lease=[IO.File]::Open((Join-Path $run 'persistent-lease'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    [Console]::Title='TradingAgent local-only BFF '+$RunId.Substring(0,8)
    Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue
    if((Get-Location).Path -cne $root){throw 'REPOSITORY_ROOT_REQUIRED'}
    if((& $dotnetExe --version) -cne '10.0.402'){throw 'EXACT_SDK_REQUIRED'}
    foreach($name in @('DOTNET_CLI_TELEMETRY_OPTOUT','DOTNET_GENERATE_ASPNET_CERTIFICATE')){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
    $env:DOTNET_CLI_TELEMETRY_OPTOUT='1';$env:DOTNET_GENERATE_ASPNET_CERTIFICATE='false'
    $project=Join-Path $PSScriptRoot 'BrowserFixture/BrowserFixture.csproj'
    & $dotnetExe restore $project --locked-mode *> (Join-Path $run 'persistent-restore.log')
    if($LASTEXITCODE){throw 'LOCKED_RESTORE_FAILED'}
    & $dotnetExe build $project --no-restore -c Release --warnaserror *> (Join-Path $run 'persistent-build.log')
    if($LASTEXITCODE){throw 'STRICT_BUILD_FAILED'}
    $react=Join-Path $root 'frontend-react/dist'
    if(!(Test-Path -LiteralPath (Join-Path $react 'index.html')) -or !@(Get-ChildItem -LiteralPath (Join-Path $react 'assets') -Filter '*.js').Count){throw 'COMPILED_REACT_REQUIRED'}
    $cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2((Join-Path $run 'root.cer'))
    try{if($cert.Thumbprint -cne $prepared.rootThumbprint -or [datetimeoffset]::UtcNow -ge [datetimeoffset]::Parse($prepared.expiresAt)){throw 'CERTIFICATE_IDENTITY_OR_EXPIRY_REJECTED'}}finally{$cert.Dispose()}
    $public=Get-Content -LiteralPath (Join-Path $root 'tmp/m013b/hosted-development.public.json') -Raw | ConvertFrom-Json
    if($public.confirmedReference -cne 'ocwabwmzhpedyxlkjpje' -or $public.project.TrimEnd('/') -cne 'https://ocwabwmzhpedyxlkjpje.supabase.co'){throw 'DEVELOPMENT_CONFIGURATION_REJECTED'}
    $secret=Unprotect ((Get-Content -LiteralPath (Join-Path $run 'secrets.dpapi') -Raw).Trim()) | ConvertFrom-Json
    $settings=@{INTERACTIVE_APPROVAL='LOCAL_STARTUP_CHECKS_ONLY';PROJECT_REF=$public.confirmedReference;PROJECT_URL=$public.project;PUBLISHABLE_KEY=$public.publishableKey;ORIGIN=$owner.origin;SQL_PORT="$($owner.sqlPort)";SQL_DATABASE=$prepared.database;RUNTIME_USER=$prepared.runtimeUser;RUNTIME_PASSWORD=$secret.runtime;ISSUER_USER=$prepared.issuerUser;ISSUER_PASSWORD=$secret.issuer;TLS_PFX=(Join-Path $run 'loopback.pfx');TLS_PASSWORD=$secret.tls;REACT_DIST=$react;STATE_FILE=$stateFile;STOP_FILE=$stopFile}
    foreach($key in $settings.Keys){$name='M014B_B2_'+$key;$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process');[Environment]::SetEnvironmentVariable($name,$settings[$key],'Process')}
    & (Join-Path $pg 'pg_ctl.exe') -D $data status *> $null
    if($LASTEXITCODE -eq 0){throw 'CLUSTER_ALREADY_RUNNING; IMPLICIT_ATTACH_DENIED'}
    Remove-Item -LiteralPath $stopFile -ErrorAction SilentlyContinue
    $args='-D "'+$data+'" -l "'+(Join-Path $run 'postgres.log')+'" -w start'
    $controller=Start-Process -FilePath (Join-Path $pg 'pg_ctl.exe') -ArgumentList $args -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'persistent-pgctl.log') -RedirectStandardError (Join-Path $run 'persistent-pgctl-error.log')
    try{$null=$controller.Handle;if(!$controller.WaitForExit(45000) -or $controller.ExitCode -ne 0){throw 'OWNED_POSTGRES_START_FAILED'}}finally{$controller.Dispose()}
    $started=$true
    Write-Output "URL=$($owner.origin) STATE=PREFLIGHT LOGIN_DISABLED OFFLINE / NO_TRADE"
    & $dotnetExe (Join-Path $PSScriptRoot 'BrowserFixture/bin/Release/net10.0/BrowserFixture.dll') --hosted-local-checks
    if($LASTEXITCODE){throw 'LOCAL_BFF_PREFLIGHT_FAILED'}
} catch {
    # Fixed diagnostic only; never echo native exceptions, variables or secrets.
    if($ownedValidated -and $Mode -eq 'Foreground' -and $lease){
        $codes=@('EXACT_SDK_REQUIRED','LOCKED_RESTORE_FAILED','STRICT_BUILD_FAILED','COMPILED_REACT_REQUIRED','CERTIFICATE_IDENTITY_OR_EXPIRY_REJECTED','DEVELOPMENT_CONFIGURATION_REJECTED','CLUSTER_ALREADY_RUNNING; IMPLICIT_ATTACH_DENIED','OWNED_POSTGRES_START_FAILED','LOCAL_BFF_PREFLIGHT_FAILED')
        $diagnostic='UNEXPECTED_LOCAL_PREFLIGHT'
        if($_.Exception.Message -cin $codes){$diagnostic=$_.Exception.Message}
        @{state='FAILED';pid=0;diagnostic=$diagnostic;stageLine=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
        Write-Output "DIAGNOSTIC=$diagnostic"
    }
    Write-Output 'STATE=FAILED; LOCAL_STARTUP_REJECTED; INSPECT_PRIVATE_PREFLIGHT'
    exit 1
} finally {
    if($started){
        Assert-Owned
        & (Join-Path $pg 'pg_ctl.exe') -D $data -m fast -w stop *> (Join-Path $run 'persistent-pg-stop.log')
    }
    foreach($name in $previous.Keys){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
    $settings=$null;$secret=$null
    if($lease){$lease.Dispose()}
}
