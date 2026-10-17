param([ValidateSet('Start','Stop','Status')][string]$Action='Start',[string]$PgBin='C:\Program Files\PostgreSQL\17\bin',[int]$Port=55432)
$ErrorActionPreference='Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $repoRoot '.local'
$dataPath = Join-Path $testRoot 'postgres-test'
if ($Action -eq 'Start') {
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $dataPath 'PG_VERSION'))) {
        & (Join-Path $PgBin 'initdb.exe') -D $dataPath -U trading_test --auth=trust --encoding=UTF8 --locale=C
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
    }
    & (Join-Path $PgBin 'pg_ctl.exe') status -D $dataPath 2>$null
    if ($LASTEXITCODE -ne 0) {
        $argsList = @('start','-D',('"'+$dataPath+'"'),'-l',('"'+(Join-Path $testRoot 'postgres-test.log')+'"'),'-o',('"-h 127.0.0.1 -p '+$Port+'"'),'-w')
        # Start-Process -Wait waits for the entire process tree, including the server.
        # Wait only for pg_ctl itself, which exits once the server is ready.
        $process = Start-Process -FilePath (Join-Path $PgBin 'pg_ctl.exe') -ArgumentList $argsList -WindowStyle Hidden -PassThru
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) { throw 'PostgreSQL failed to start; inspect .local/postgres-test.log' }
    }
    Write-Output ('Disposable local DB: Host=127.0.0.1;Port='+$Port+';Username=trading_test;Database=postgres')
    Write-Output 'Test-only trust authentication on loopback. Stop after testing; never use this cluster for broker data or secrets.'
} elseif ($Action -eq 'Stop') {
    & (Join-Path $PgBin 'pg_ctl.exe') stop -D $dataPath -m fast -w
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop test cluster' }
} else {
    & (Join-Path $PgBin 'pg_ctl.exe') status -D $dataPath
}
