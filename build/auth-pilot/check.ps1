[CmdletBinding()]
param([string]$Dotnet = 'dotnet')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$executable = (Get-Command $Dotnet -ErrorAction Stop).Source
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$results = Join-Path $root 'artifacts/m013b'
New-Item -ItemType Directory -Force -Path $results | Out-Null
$env:M012_RESULTS_DIRECTORY = $results
$env:DOTNET_CLI_HOME = Join-Path $root 'tmp/m013b/cli-home'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_NOLOGO = '1'
Push-Location $PSScriptRoot
try {
    $version = & $executable --version
    $version | Set-Content -LiteralPath (Join-Path $results 'sdk-version.txt') -Encoding UTF8
    if ($LASTEXITCODE -ne 0 -or $version -cne '10.0.402') { throw 'Exact SDK 10.0.402 required.' }
    & $executable restore TradingAgent.Auth.slnx --locked-mode --force --no-http-cache 2>&1 | Tee-Object -FilePath (Join-Path $results 'restore.log')
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore/audit failed.' }
    & $executable build TradingAgent.Auth.slnx --no-restore -c Release --warnaserror 2>&1 | Tee-Object -FilePath (Join-Path $results 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Strict build failed.' }
    & $executable test TradingAgent.Auth.slnx --no-build --no-restore -c Release --logger 'trx;LogFileName=m013b.trx' --results-directory $results
    if ($LASTEXITCODE -ne 0) { throw 'M01.3B B1 tests failed.' }
    $inventoryText = & $executable list TradingAgent.Auth.slnx package --include-transitive --format json --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Dependency inventory failed.' }
    $inventory = ($inventoryText -join "`n") | ConvertFrom-Json
    $auditText = & $executable list TradingAgent.Auth.slnx package --vulnerable --include-transitive --format json --no-restore --source https://api.nuget.org/v3/index.json
    if ($LASTEXITCODE -ne 0) { throw 'Dependency report failed.' }
    $audit = ($auditText -join "`n") | ConvertFrom-Json
    if ($audit.version -ne 1 -or @($audit.projects).Count -ne 5 -or ($audit.PSObject.Properties['problems'] -and @($audit.problems).Count)) { throw 'Incomplete dependency report.' }
    if ($inventory.version -ne 1 -or @($inventory.projects).Count -ne 5 -or ($inventory.PSObject.Properties['problems'] -and @($inventory.problems).Count)) { throw 'Incomplete inventory.' }
    if (@(Compare-Object ($inventory.projects.path | Sort-Object) ($audit.projects.path | Sort-Object)).Count) { throw 'Audit/inventory project mismatch.' }
    foreach ($project in $inventory.projects) {
        if (@($project.frameworks).Count -ne 1 -or $project.frameworks[0].framework -ne 'net10.0') { throw 'Wrong inventory framework.' }
    }
    foreach ($project in $audit.projects) {
        # The vulnerable-only report may omit frameworks when no vulnerable packages exist.
        # Framework coverage is established independently by the complete inventory above.
        if (!$project.PSObject.Properties['frameworks']) { continue }
        if (@($project.frameworks).Count -ne 1 -or $project.frameworks[0].framework -ne 'net10.0') { throw 'Wrong audit framework.' }
        foreach ($framework in $project.frameworks) {
            foreach ($property in @('topLevelPackages','transitivePackages')) {
                if ($framework.PSObject.Properties[$property] -and @($framework.$property).Count) { throw 'Vulnerable dependency reported.' }
            }
        }
    }
    [ordered]@{ inventory=$inventory; audit=$audit; vulnerable_packages_reported=0; result='PASS'; limitation='Known NuGet advisories only; shared runtime not covered.' } | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $results 'dependencies.json') -Encoding UTF8
    & (Join-Path $root 'build/identity/verify-results.ps1') -Trx (Join-Path $results 'm013b.trx') -Assembly 'TradingAgent.Auth.Pilot.Tests.dll' -Expected (Join-Path $PSScriptRoot 'expected-tests.json') -Summary (Join-Path $results 'summary.json')
} finally { Pop-Location }
