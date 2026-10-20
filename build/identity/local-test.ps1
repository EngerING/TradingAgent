param([string]$PostgresBin = 'C:/Program Files/PostgreSQL/17/bin', [string]$Dotnet = './tmp/m011/dotnet/dotnet.exe')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$directory = Join-Path $root ('tmp/m012/pg-' + [guid]::NewGuid().ToString('N'))
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
    & (Join-Path $PSScriptRoot 'check.ps1') -Dotnet $Dotnet
    $testExit = 0
} finally {
    if ($started) { & (Join-Path $PostgresBin 'pg_ctl.exe') -D $data -m fast -w stop }
    Remove-Item Env:M012_BOOTSTRAP_PASSWORD,Env:M012_TEST_PORT,Env:M012_CLUSTER_MARKER -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $passwordFile -ErrorAction SilentlyContinue
}
if ($testExit -ne 0) { throw 'M01.2 tests failed; inspect TRX.' }
