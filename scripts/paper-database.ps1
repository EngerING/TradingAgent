param([ValidateSet('Start','Stop','Load','Status')][string]$Action='Start',[string]$PgBin='C:\Program Files\PostgreSQL\17\bin')
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$paperRoot=Join-Path $repoRoot '.local/postgres-paper'
$secretPath=Join-Path $repoRoot '.local/paper-db.secret.xml'
$appSecretPath=Join-Path $repoRoot '.local/paper-app-db.secret.xml'
$port=55433
function New-PaperPassword {
    $bytes=New-Object byte[] 48
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($bytes);return [Convert]::ToBase64String($bytes)} finally {$rng.Dispose()}
}
if($Action -eq 'Start') {
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot '.local') | Out-Null
    if(-not (Test-Path -LiteralPath (Join-Path $paperRoot 'PG_VERSION'))) {
        if(Test-Path -LiteralPath $secretPath){throw 'Secret exists without cluster; manual review required'}
        $password=New-PaperPassword
        $credential=[pscredential]::new('paper_migration',(ConvertTo-SecureString $password -AsPlainText -Force))
        # DPAPI encrypts the credential for this Windows user. Never committed.
        $credential | Export-Clixml -LiteralPath $secretPath
        $passwordFile=Join-Path $repoRoot '.local/paper-init-password.tmp'
        try {
            [IO.File]::WriteAllText($passwordFile,$password)
            & (Join-Path $PgBin 'initdb.exe') -D $paperRoot -U paper_migration --auth=scram-sha-256 --pwfile=$passwordFile --encoding=UTF8 --locale=C
            if($LASTEXITCODE -ne 0){throw 'Paper initdb failed'}
        } finally {Remove-Item -LiteralPath $passwordFile -ErrorAction SilentlyContinue;$password=$null}
    }
    & (Join-Path $PgBin 'pg_ctl.exe') status -D $paperRoot 2>$null
    if($LASTEXITCODE -ne 0) {
        $pgArgs=@('start','-D',('"'+$paperRoot+'"'),'-l',('"'+(Join-Path $repoRoot '.local/postgres-paper.log')+'"'),'-o','"-h 127.0.0.1 -p 55433"','-w')
        $pgProcess=Start-Process -FilePath (Join-Path $PgBin 'pg_ctl.exe') -ArgumentList $pgArgs -WindowStyle Hidden -PassThru
        $pgProcess.WaitForExit();if($pgProcess.ExitCode -ne 0){throw 'Paper PostgreSQL failed to start'}
    }
}
if($Action -in @('Start','Load')) {
    if($Action -eq 'Start') {
        $migration=Import-Clixml -LiteralPath $secretPath
        $env:TRADING_DB='Host=127.0.0.1;Port=55433;Username=paper_migration;Database=postgres;Password='+$migration.GetNetworkCredential().Password
        Push-Location $repoRoot
        try {
            dotnet run --project src/TradingAgent.Api --no-build -- --migrate
            if($LASTEXITCODE -ne 0){throw 'Paper migrations failed'}
        } finally {Pop-Location;Remove-Item Env:TRADING_DB -ErrorAction SilentlyContinue}
        $env:PGPASSWORD=$migration.GetNetworkCredential().Password
        try {
            if(-not (Test-Path -LiteralPath $appSecretPath)) {
                $appPassword=New-PaperPassword
                $appCredential=[pscredential]::new('paper_data',(ConvertTo-SecureString $appPassword -AsPlainText -Force))
                # Random base64 contains no SQL quotes. Password never enters a command argument.
                ('CREATE ROLE paper_data LOGIN PASSWORD '''+$appPassword+''';') | & (Join-Path $PgBin 'psql.exe') -h 127.0.0.1 -p $port -U paper_migration -d postgres -q -v ON_ERROR_STOP=1
                if($LASTEXITCODE -ne 0){throw 'Paper application role creation failed'}
                $appCredential | Export-Clixml -LiteralPath $appSecretPath
                $appPassword=$null
            }
            @'
GRANT USAGE ON SCHEMA public TO paper_data;
GRANT SELECT ON schema_migrations TO paper_data;
GRANT SELECT,INSERT ON paper_observations,market_candles TO paper_data;
GRANT SELECT,INSERT ON market_snapshots,strategies,strategy_versions,backtest_runs,backtest_trades,trading_decisions,risk_evaluations TO paper_data;
'@ | & (Join-Path $PgBin 'psql.exe') -h 127.0.0.1 -p $port -U paper_migration -d postgres -q -v ON_ERROR_STOP=1
            if($LASTEXITCODE -ne 0){throw 'Paper grants failed'}
        } finally {Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue}
    }
    if(-not (Test-Path -LiteralPath $appSecretPath)){throw 'Paper application credential missing; run Start first'}
    $credential=Import-Clixml -LiteralPath $appSecretPath
    $env:TRADING_DB='Host=127.0.0.1;Port=55433;Username=paper_data;Database=postgres;Password='+$credential.GetNetworkCredential().Password
    $env:TRADING_DB_AUTO_MIGRATE='false'
    Write-Output 'Secure Paper database configured on loopback:55433 (credential omitted).'
} elseif($Action -eq 'Stop') {
    & (Join-Path $PgBin 'pg_ctl.exe') stop -D $paperRoot -m fast -w
    if($LASTEXITCODE -ne 0){throw 'Paper database stop failed'}
    Remove-Item Env:TRADING_DB -ErrorAction SilentlyContinue
} else {& (Join-Path $PgBin 'pg_ctl.exe') status -D $paperRoot}
