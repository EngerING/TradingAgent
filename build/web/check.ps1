[CmdletBinding()]
param([string] $Dotnet = 'dotnet')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$executable = (Get-Command $Dotnet -ErrorAction Stop).Source
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$results = Join-Path $root 'tmp/m011/check'
New-Item -ItemType Directory -Force -Path $results | Out-Null
$environmentNames = @('DOTNET_CLI_HOME', 'DOTNET_CLI_TELEMETRY_OPTOUT', 'DOTNET_GENERATE_ASPNET_CERTIFICATE', 'DOTNET_NOLOGO')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

Push-Location $PSScriptRoot
try {
    $env:DOTNET_CLI_HOME = Join-Path $root 'tmp/m011/cli-home'
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    $env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
    $env:DOTNET_NOLOGO = '1'
    $version = & $executable --version
    if ($LASTEXITCODE -ne 0 -or $version -ne '10.0.402') { throw 'The isolated web build requires SDK 10.0.402.' }

    # Restore/audit contacts only the public registry. No application service is started.
    & $executable restore TradingAgent.Web.slnx --locked-mode --force --no-http-cache 2>&1 |
        Tee-Object -FilePath (Join-Path $results 'restore.log')
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore or dependency audit failed.' }
    & $executable build TradingAgent.Web.slnx --no-restore --configuration Release --warnaserror 2>&1 |
        Tee-Object -FilePath (Join-Path $results 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Strict web build failed.' }
    & $executable test TradingAgent.Web.slnx --no-build --no-restore --configuration Release `
        --logger 'trx;LogFileName=m011.trx' --results-directory $results
    if ($LASTEXITCODE -ne 0) { throw 'Isolated web tests failed.' }

    $auditText = & $executable list TradingAgent.Web.slnx package --vulnerable --include-transitive --format json --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Dependency report failed.' }
    $auditText | Set-Content -LiteralPath (Join-Path $results 'dependencies.json') -Encoding UTF8
    $audit = ($auditText -join "`n") | ConvertFrom-Json
    if ($audit.version -ne 1) { throw 'Unsupported dependency report version.' }
    if ($audit.PSObject.Properties['problems'] -and @($audit.problems).Count -gt 0) { throw 'Incomplete dependency report.' }
    if (@($audit.projects).Count -ne 2) { throw 'Unexpected dependency audit scope.' }
    foreach ($project in $audit.projects) {
        if (@($project.frameworks).Count -ne 1 -or $project.frameworks[0].framework -ne 'net10.0') {
            throw 'Incomplete or unexpected framework audit scope.'
        }
        foreach ($framework in $project.frameworks) {
            foreach ($property in @('topLevelPackages', 'transitivePackages')) {
                if ($framework.PSObject.Properties[$property] -and @($framework.$property).Count -gt 0) {
                    throw 'Vulnerable dependency reported.'
                }
            }
        }
    }
    Write-Output 'M01.1: strict build, isolated tests and direct/transitive dependency audit passed. OFFLINE / NO_TRADE.'
}
finally {
    Pop-Location
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
}
