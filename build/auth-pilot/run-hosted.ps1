param([string]$PostgresBin = 'C:/Program Files/PostgreSQL/17/bin', [string]$Dotnet = './tmp/m011/dotnet/dotnet.exe')
$ErrorActionPreference = 'Stop'
$dotnetExecutable = (Get-Command $Dotnet -ErrorAction Stop).Source
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ((Get-Location).Path -cne $root) { throw 'Run this script from the repository root.' }
if ((& $dotnetExecutable --version) -cne '10.0.402') { throw 'Exact SDK 10.0.402 required.' }
$env:DOTNET_CLI_HOME = Join-Path $root 'tmp/m011/cli-home'; $env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'; $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$project = Join-Path $PSScriptRoot 'HostedRunner/HostedRunner.csproj'
& $dotnetExecutable restore $project --locked-mode
if ($LASTEXITCODE -ne 0) { throw 'Hosted runner locked restore failed.' }
& $dotnetExecutable build $project --no-restore -c Release --warnaserror
if ($LASTEXITCODE -ne 0) { throw 'Hosted runner strict build failed.' }
$directory = Join-Path $root ('tmp/m013b/hosted-pg-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$data = Join-Path $directory 'data'
$passwordFile = Join-Path $directory 'fixture-password'
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes); $rng.Dispose()
$password = [BitConverter]::ToString($bytes).Replace('-','')
[IO.File]::WriteAllText($passwordFile, $password, [Text.Encoding]::ASCII)
$listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)
$listener.Start(); $port = $listener.LocalEndpoint.Port; $listener.Stop()
if ($port -lt 20000 -or $port -in @(55433,55434)) { throw 'Unexpected disposable port; retry.' }
$marker = 'm012_disposable_' + [guid]::NewGuid().ToString('N')
$started = $false
try {
    & (Join-Path $PostgresBin 'initdb.exe') -D $data -U postgres -A scram-sha-256 --pwfile=$passwordFile --encoding=UTF8 --locale=C > (Join-Path $directory 'init.log')
    if ($LASTEXITCODE -ne 0) { throw 'Disposable initdb failed.' }
    Add-Content -LiteralPath (Join-Path $data 'postgresql.conf') -Value "`nlisten_addresses='127.0.0.1'`nport=$port`ncluster_name='$marker'`n"
    & (Join-Path $PostgresBin 'pg_ctl.exe') -D $data -l (Join-Path $directory 'postgres.log') -w start
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL start failed.' }
    $started = $true
    $env:M012_TEST_PORT = "$port"; $env:M012_BOOTSTRAP_PASSWORD = $password; $env:M012_CLUSTER_MARKER = $marker
    $env:DOTNET_CLI_HOME = Join-Path $root 'tmp/m011/cli-home'; $env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'; $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    & $dotnetExecutable exec (Join-Path $PSScriptRoot 'HostedRunner/bin/Release/net10.0-windows/HostedRunner.dll')
    if ($LASTEXITCODE -ne 0) { throw 'Hosted runner did not complete its measurements. Inspect only the redacted result; B2 is not approved.' }
    $result = Get-Content -LiteralPath (Join-Path $root 'tmp/m013b/hosted-interactive-result.json') -Raw | ConvertFrom-Json
    if ($result.status -cne 'DIRECT_HOSTED_AUTH_SQL_EXECUTED; HTTPS_BFF_PENDING_COMPATIBLE_CERTIFICATE' -and $result.status -cne 'EXECUTED_CHECKS_PASS_WITH_EXPLICIT_PENDING_CASES') { throw 'Hosted result is incomplete; no success inferred from process exit.' }
    Write-Output 'Selected measurements completed with explicit pending cases. This is not B2 approval.'
    $testExit = 0
} finally {
    if ($started) { & (Join-Path $PostgresBin 'pg_ctl.exe') -D $data -m fast -w stop }
    Remove-Item Env:M012_BOOTSTRAP_PASSWORD,Env:M012_TEST_PORT,Env:M012_CLUSTER_MARKER -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $passwordFile -ErrorAction SilentlyContinue
}
if ($testExit -ne 0) { throw 'Hosted pilot did not complete; inspect only redacted result.' }
