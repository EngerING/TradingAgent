$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    dotnet build TradingAgent.sln -m:1
    if($LASTEXITCODE -ne 0){throw 'Build failed'}
    dotnet test TradingAgent.sln --no-build -m:1 --logger 'trx;LogFileName=phase2.trx' --results-directory artifacts/test-results
    if($LASTEXITCODE -ne 0){throw 'C# tests failed'}
    $env:PYTHONPATH=Join-Path $repoRoot 'python'
    $pythonExe=if(Test-Path '.venv/Scripts/python.exe'){Join-Path $repoRoot '.venv/Scripts/python.exe'}else{'python'}
    & $pythonExe -m unittest discover -s python/tests -v
    if($LASTEXITCODE -ne 0){throw 'Python tests failed'}
    & $pythonExe -m compileall -q python/trading_agent
    if($LASTEXITCODE -ne 0){throw 'Python compile failed'}
    dotnet run --project src/TradingAgent.Api --no-build -- --demo
    if($LASTEXITCODE -ne 0){throw 'Risk demo failed'}
    if(-not $env:TRADING_TEST_DB){Write-Warning 'Database tests SKIPPED: set TRADING_TEST_DB to run the complete suite.'}
} finally {Pop-Location}
