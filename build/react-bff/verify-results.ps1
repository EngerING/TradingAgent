param([Parameter(Mandatory)][string]$Trx, [Parameter(Mandatory)][string]$Assembly, [Parameter(Mandatory)][string]$Expected, [Parameter(Mandatory)][string]$Summary)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[xml]$document = Get-Content -LiteralPath $Trx -Raw
$ns = New-Object Xml.XmlNamespaceManager($document.NameTable)
$ns.AddNamespace('t','http://microsoft.com/schemas/VisualStudio/TeamTest/2010')
$counters = $document.SelectSingleNode('/t:TestRun/t:ResultSummary/t:Counters',$ns)
$results = @($document.SelectNodes('/t:TestRun/t:Results/t:UnitTestResult',$ns))
$definitions = @($document.SelectNodes('/t:TestRun/t:TestDefinitions/t:UnitTest',$ns))
$expectedTests = Get-Content -LiteralPath $Expected -Raw | ConvertFrom-Json
if ($expectedTests.Count -ne 18 -or ($expectedTests | Select-Object -Unique).Count -ne $expectedTests.Count) { throw 'Invalid expected test manifest.' }
if ($counters.total -ne $expectedTests.Count -or $counters.executed -ne $expectedTests.Count -or $counters.passed -ne $expectedTests.Count -or
    $results.Count -ne $expectedTests.Count -or $definitions.Count -ne $expectedTests.Count) { throw 'Missing or undiscovered tests.' }
foreach ($attribute in $counters.Attributes) {
    if ($attribute.Name -notin @('total','executed','passed') -and [int]$attribute.Value -ne 0) { throw 'Non-passing TRX counter.' }
}
if (@($results | Where-Object { $_.outcome -cne 'Passed' }).Count) { throw 'Non-passing TRX result.' }
if (@(Compare-Object ($expectedTests | Sort-Object) ($results.testName | Sort-Object)).Count) { throw 'Expected test identity mismatch.' }
foreach ($definition in $definitions) {
    if ([IO.Path]::GetFileName(($definition.TestMethod.codeBase -replace '\\','/')) -cne $Assembly) { throw 'Unexpected test assembly.' }
}
$times = $document.SelectSingleNode('/t:TestRun/t:Times',$ns)
$duration = ([DateTimeOffset]::Parse($times.finish) - [DateTimeOffset]::Parse($times.start)).TotalSeconds
$value = [ordered]@{ assembly=$Assembly; total=[int]$counters.total; passed=[int]$counters.passed; failed=0; skipped=0; duration_seconds=$duration; expected_test_manifest='PASS'; mode='OFFLINE'; decision='NO_TRADE' }
$value | ConvertTo-Json | Set-Content -LiteralPath $Summary -Encoding UTF8
Write-Output ($value | ConvertTo-Json -Compress)
