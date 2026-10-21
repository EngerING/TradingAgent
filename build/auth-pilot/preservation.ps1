$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$results = Join-Path $root 'artifacts/m013b'
New-Item -ItemType Directory -Force -Path $results | Out-Null
function Read-Git([string[]]$Arguments) {
    $value = & git -C $root @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Git preservation query failed.' }
    return ($value -join "`n").Trim()
}
$baseline = 'c15c49ac07bf2eec2c72d8987c1db52b18a04795'
& git -C $root merge-base --is-ancestor $baseline HEAD
if ($LASTEXITCODE -ne 0) { throw 'Incorrect ancestry.' }
if ((Read-Git @('branch','--show-current')) -cne 'codex/m01-3b-hosted-supabase-pilot' -and !$env:GITHUB_ACTIONS) { throw 'Wrong local branch.' }
$head = Read-Git @('rev-parse','HEAD')
if ($env:GITHUB_ACTIONS -and ($head -cne $env:GITHUB_SHA -or $env:GITHUB_REF -cne 'refs/heads/codex/m01-3b-hosted-supabase-pilot')) { throw 'Wrong CI identity.' }
$approvedModified = @('src/TradingAgent.Web.Auth/IntegratedHostFactory.cs','src/TradingAgent.Web.Auth/PilotRuntime.cs','src/TradingAgent.Web.Auth/PilotEndpoints.cs','src/TradingAgent.Identity.Supabase/AuthConfiguration.cs','src/TradingAgent.Identity.Supabase/AuthTransport.cs','src/TradingAgent.Identity.Supabase/SupabaseAuthClient.cs')
$changes = Read-Git @('diff','--name-status','--no-renames',$baseline,'HEAD')
foreach ($change in ($changes -split "`n" | Where-Object { $_ })) {
    $entry = $change -split "`t"
    $approvedEdit = $entry.Count -eq 2 -and $entry[0] -ceq 'M' -and $entry[1] -cin $approvedModified
    if (!$approvedEdit -and ($entry.Count -ne 2 -or $entry[0] -cne 'A' -or $entry[1] -cnotmatch '^(src/TradingAgent\.Web\.Auth/(HostedPilotSettings|PilotRequestBudgets)\.cs$|tests/TradingAgent\.Auth\.Pilot\.Tests/|build/auth-pilot/|docs/architecture/m01-3b-[A-Za-z0-9-]+\.(md|json)$|\.github/workflows/m01-3b-hosted-pilot-ci\.yml$)')) { throw 'Diff exceeds approved M01.3B preparation.' }
    if ($entry[1] -match '(^|/)(\.local|\.env|bin|obj|node_modules|TestResults)(/|$)|\.(exe|dll|zip|pfx|p12|pem|key|sqlite|db)$') { throw 'Sensitive/artifact path rejected.' }
    $content = Get-Content -LiteralPath (Join-Path $root $entry[1]) -Raw
    if ($content -match '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{12,}\.eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}') { throw 'Known credential pattern rejected; content redacted.' }
}
# Only the explicit M01.3A corrections and user-requested TOTP contract fix may differ.
$baselineFiles = (Read-Git @('ls-tree','-r','--name-only',$baseline)) -split "`n"
$objectLines = & git -C $root diff-tree -r --no-commit-id --name-status $baseline HEAD
if ($LASTEXITCODE -ne 0) { throw 'Diff query failed.' }
foreach ($line in $objectLines) { $parts = $line -split "`t"; if ($parts[0] -cne 'A' -and !($parts[0] -ceq 'M' -and $parts[1] -cin $approvedModified)) { throw 'Protected baseline file modified or deleted.' } }
$paths = @('python/trading_agent/core_v3','python/trading_agent/market_analyst','src/TradingAgent.Infrastructure','src/TradingAgent.Core','src/TradingAgent.Api','src/TradingAgent.ConfigurationLab','src/TradingAgent.ResearchLab','frontend','src/TradingAgent.Web','src/TradingAgent.Identity.Supabase/JwtVerifier.cs','src/TradingAgent.Identity.Supabase/JwksCache.cs','src/TradingAgent.Identity.Supabase/TradingAgent.Identity.Supabase.csproj','src/TradingAgent.Identity.Supabase/packages.lock.json','tests/TradingAgent.Auth.Tests','build/auth','tests/TradingAgent.Web.Tests','src/TradingAgent.Identity.Persistence','src/TradingAgent.Identity.Migrations','tests/TradingAgent.Identity.Tests','build/web','build/identity','Directory.Build.props','TradingAgent.sln','.github/workflows/m01-1-bff-ci.yml','.github/workflows/m01-2-postgres-security-ci.yml','.github/workflows/m01-3-supabase-auth-ci.yml')
$objects = [ordered]@{}
foreach ($path in $paths) {
    $before = Read-Git @('rev-parse',"${baseline}:$path"); $after = Read-Git @('rev-parse',"HEAD:$path")
    if ($before -cne $after) { throw "Protected object changed: $path" }; $objects[$path] = $after
}
$migrations = [ordered]@{}
foreach ($path in ((Read-Git @('ls-tree','-r','--name-only','HEAD','src/TradingAgent.Infrastructure/Migrations')) -split "`n")) {
    $migrations[$path] = (Get-FileHash -LiteralPath (Join-Path $root $path) -Algorithm SHA256).Hash.ToLowerInvariant()
}
if ($baselineFiles.Count -ne 804 -or $migrations.Count -ne 11) { throw 'Baseline inventory mismatch.' }
[ordered]@{ baseline=$baseline; commit=$head; tree=(Read-Git @('rev-parse','HEAD^{tree}')); preservation='PASS'; approved_modified=$approvedModified; baseline_files=$baselineFiles.Count; protected_objects=$objects; historical_migration_sha256=$migrations; mode='OFFLINE'; decision='NO_TRADE' } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $results 'identity.json') -Encoding UTF8
