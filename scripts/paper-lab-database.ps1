param([ValidateSet('Prepare','Load')][string]$Action='Load',[string]$PgBin='C:\Program Files\PostgreSQL\17\bin')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$secret=Join-Path $root '.local/paper-lab-db.secret.xml'
if($Action -eq 'Prepare') {
    & (Join-Path $root 'scripts/paper-database.ps1') -Action Start
    $migration=Import-Clixml -LiteralPath (Join-Path $root '.local/paper-db.secret.xml')
    try {
        $env:PGPASSWORD=$migration.GetNetworkCredential().Password
        if(-not(Test-Path -LiteralPath $secret)) {
            $password=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
            $credential=[pscredential]::new('paper_lab_app',(ConvertTo-SecureString $password -AsPlainText -Force))
            # Generated password contains only hex characters, never user-controlled SQL.
            "CREATE ROLE paper_lab_app LOGIN PASSWORD '$password';" | & (Join-Path $PgBin 'psql.exe') -h 127.0.0.1 -p 55433 -U paper_migration -d postgres -q -v ON_ERROR_STOP=1
            if($LASTEXITCODE -ne 0){throw 'LAB_ROLE_CREATION_FAILED'}
            $credential | Export-Clixml -LiteralPath $secret
            $password=$null
        }
        @'
GRANT USAGE ON SCHEMA paper_lab TO paper_lab_app;
GRANT SELECT,INSERT,UPDATE ON paper_lab.states TO paper_lab_app;
GRANT SELECT,INSERT ON paper_lab.events,paper_lab.experience TO paper_lab_app;
GRANT SELECT,INSERT ON paper_lab.ford_diagnostic_events TO paper_lab_app;
GRANT USAGE ON SCHEMA research_shadow TO paper_lab_app;
GRANT SELECT,INSERT ON research_shadow.events TO paper_lab_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM paper_lab_app;
'@ | & (Join-Path $PgBin 'psql.exe') -h 127.0.0.1 -p 55433 -U paper_migration -d postgres -q -v ON_ERROR_STOP=1
        if($LASTEXITCODE -ne 0){throw 'LAB_GRANTS_FAILED'}
    } finally {Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue;Remove-Item Env:TRADING_DB -ErrorAction SilentlyContinue}
}
if(-not(Test-Path -LiteralPath $secret)){throw 'LAB_DATABASE_NOT_PREPARED'}
$credential=Import-Clixml -LiteralPath $secret
$env:TRADING_LAB_DB='Host=127.0.0.1;Port=55433;Username=paper_lab_app;Database=postgres;Password='+$credential.GetNetworkCredential().Password
Write-Output 'Journal Paper configurado en loopback:55433; credencial omitida; originales sin permisos de escritura.'
