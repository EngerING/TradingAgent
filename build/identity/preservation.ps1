$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$results = Join-Path $root 'artifacts/m012'
New-Item -ItemType Directory -Force -Path $results | Out-Null
function Read-Git([string[]]$Arguments) {
    $value = & git -C $root @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Git preservation query failed.' }
    return ($value -join "`n").Trim()
}
$baseline = '6fb5068e8ab77658530874856bdabb05b9af2316'
& git -C $root merge-base --is-ancestor $baseline HEAD
if ($LASTEXITCODE -ne 0) { throw 'Incorrect ancestry.' }
if ((Read-Git @('branch','--show-current')) -cne 'codex/m01-2-postgres-security' -and !$env:GITHUB_ACTIONS) { throw 'Wrong local branch.' }
$head = Read-Git @('rev-parse','HEAD')
if ($env:GITHUB_ACTIONS -and ($head -cne $env:GITHUB_SHA -or $env:GITHUB_REF -cne 'refs/heads/codex/m01-2-postgres-security')) { throw 'Wrong CI identity.' }
$changes = Read-Git @('diff','--name-status','--no-renames',$baseline,'HEAD')
foreach ($change in ($changes -split "`n" | Where-Object { $_ })) {
    $entry = $change -split "`t"
    if ($entry.Count -ne 2 -or $entry[0] -cne 'A' -or $entry[1] -cnotmatch '^(src/TradingAgent\.Identity\.(Persistence|Migrations)/|tests/TradingAgent\.Identity\.Tests/|build/identity/|docs/architecture/m01-2-[A-Za-z0-9-]+\.(md|json)$|\.github/workflows/m01-2-postgres-security-ci\.yml$)') { throw 'Diff exceeds M01.2 additions.' }
    if ($entry[1] -match '(^|/)(\.local|\.env|bin|obj|node_modules|TestResults)(/|$)|\.(exe|dll|zip|pfx|p12|pem|key|sqlite|db)$') { throw 'Sensitive/artifact path rejected.' }
    $content = Get-Content -LiteralPath (Join-Path $root $entry[1]) -Raw
    if ($content -match '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{12,}\.eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}') { throw 'Known credential pattern rejected; content redacted.' }
}
$paths = @('python/trading_agent/core_v3','python/trading_agent/market_analyst','src/TradingAgent.Infrastructure','src/TradingAgent.Core','src/TradingAgent.Api','src/TradingAgent.ConfigurationLab','src/TradingAgent.ResearchLab','frontend','src/TradingAgent.Web','tests/TradingAgent.Web.Tests','tests/TradingAgent.Tests','build/web','Directory.Build.props','TradingAgent.sln','.github/workflows/m01-1-bff-ci.yml')
$objects = [ordered]@{}
foreach ($path in $paths) {
    $before = Read-Git @('rev-parse',"${baseline}:$path"); $after = Read-Git @('rev-parse',"HEAD:$path")
    if ($before -cne $after) { throw "Protected object changed: $path" }; $objects[$path] = $after
}
$migrations = [ordered]@{}
foreach ($path in ((Read-Git @('ls-tree','-r','--name-only','HEAD','src/TradingAgent.Infrastructure/Migrations')) -split "`n")) {
    $migrations[$path] = (Get-FileHash -LiteralPath (Join-Path $root $path) -Algorithm SHA256).Hash.ToLowerInvariant()
}
if ($migrations.Count -ne 11) { throw 'Historical migration inventory changed.' }
[ordered]@{ baseline=$baseline; commit=$head; tree=(Read-Git @('rev-parse','HEAD^{tree}')); preservation='PASS'; protected_objects=$objects; historical_migration_sha256=$migrations; mode='OFFLINE'; decision='NO_TRADE' } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $results 'identity.json') -Encoding UTF8
