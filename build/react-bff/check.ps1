param([string]$Dotnet = 'dotnet')
$ErrorActionPreference = 'Stop'
# Fail before package/build work if the Windows launcher is syntactically broken.
$pilotTokens=$null; $pilotErrors=$null
$null=[System.Management.Automation.Language.Parser]::ParseFile(
  (Join-Path $PSScriptRoot 'local-pilot.ps1'), [ref]$pilotTokens, [ref]$pilotErrors)
if (@($pilotErrors).Count -ne 0) { throw 'LOCAL_PILOT_POWERSHELL_SYNTAX_REJECTED' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$executable = (Get-Command $Dotnet -ErrorAction Stop).Source
$results = Join-Path $root 'artifacts/m014b'
New-Item -ItemType Directory -Force $results | Out-Null
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'; $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
Push-Location $PSScriptRoot
try {
  $sdk = & $executable --version
  if ($LASTEXITCODE -ne 0 -or $sdk -cne '10.0.402') { throw 'Exact SDK required.' }
  $sdk | Set-Content (Join-Path $results 'sdk-version.txt') -Encoding UTF8
  $projects = @('BrowserFixture/BrowserFixture.csproj','../../tests/TradingAgent.React.Integration.Tests/TradingAgent.React.Integration.Tests.csproj')
  $reports = @()
  foreach ($project in $projects) {
    & $executable restore $project --locked-mode --force --no-http-cache 2>&1 | Tee-Object -FilePath (Join-Path $results 'restore.log') -Append
    if ($LASTEXITCODE) { throw 'Locked restore/audit failed.' }
    & $executable build $project --no-restore -c Release --warnaserror 2>&1 | Tee-Object -FilePath (Join-Path $results 'build.log') -Append
    if ($LASTEXITCODE) { throw 'Strict build failed.' }
    $inventoryText = & $executable list $project package --include-transitive --format json --no-restore
    if ($LASTEXITCODE) { throw 'Inventory failed.' }
    $inventory = ($inventoryText -join "`n") | ConvertFrom-Json
    if ($inventory.version -ne 1 -or @($inventory.projects).Count -ne 1 -or @($inventory.projects[0].frameworks).Count -ne 1 -or $inventory.projects[0].frameworks[0].framework -ne 'net10.0') { throw 'Inventory framework/coverage invalid.' }
    $text = & $executable list $project package --include-transitive --vulnerable --format json --no-restore --source https://api.nuget.org/v3/index.json
    if ($LASTEXITCODE) { throw 'NuGet audit failed.' }
    $report = ($text -join "`n") | ConvertFrom-Json
    if ($report.version -ne 1 -or @($report.projects).Count -ne 1 -or ($report.PSObject.Properties['problems'] -and @($report.problems).Count)) { throw 'Audit report incomplete.' }
    foreach ($item in $report.projects) { if ($item.PSObject.Properties['frameworks']) { foreach ($framework in $item.frameworks) { foreach ($kind in @('topLevelPackages','transitivePackages')) { if ($framework.PSObject.Properties[$kind] -and @($framework.$kind).Count) { throw 'Vulnerable dependency.' } } } } }
    $reports += [ordered]@{ inventory=$inventory; audit=$report; vulnerable_packages_reported=0 }
  }
  $reports | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $results 'dependencies.json') -Encoding UTF8
  & $executable test $projects[1] --no-build --no-restore -c Release --logger 'trx;LogFileName=m014b.trx' --results-directory $results
  if ($LASTEXITCODE) { throw 'Integration regression tests failed.' }
  & (Join-Path $PSScriptRoot 'verify-results.ps1') -Trx (Join-Path $results 'm014b.trx') -Assembly TradingAgent.React.Integration.Tests.dll -Expected (Join-Path $root 'tests/TradingAgent.React.Integration.Tests/expected-tests.json') -Summary (Join-Path $results 'backend-summary.json')
} finally { Pop-Location }
