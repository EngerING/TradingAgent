param(
    [string]$Python = '.venv/Scripts/python.exe',
    [string]$ApprovalDirectory,
    [string]$DatasetDirectory,
    [switch]$ApprovedHistoryOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $repo
if (-not $ApprovedHistoryOnly) {
    Write-Output 'OFFLINE / NO_TRADE; historical reader disabled. No endpoint contacted.'
    exit 0
}
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) { throw 'M032_WINDOWS_REQUIRED' }
if (-not $ApprovalDirectory -or -not $DatasetDirectory) { throw 'M032_LOCAL_INPUTS' }
$approval = (Resolve-Path -LiteralPath $ApprovalDirectory).Path
$current = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($current,'S-1-5-18','S-1-5-32-544')
foreach ($name in @('spec.json','capture-grant.json','historical-permit.json','signatures.json','verification.key')) {
    $file = Get-Item -LiteralPath (Join-Path $approval $name)
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint -or $file.Length -gt 4096) { throw 'M032_LOCAL_FILE' }
    foreach ($rule in (Get-Acl -LiteralPath $file.FullName).Access) {
        $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($rule.AccessControlType -eq 'Allow' -and $sid -notin $allowed) { throw 'M032_LOCAL_ACL' }
    }
}
$previous = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'python'
    Write-Output 'IBKR_DATA_ONLY / NO_TRADE; history only. Foreground; Ctrl+C stops.'
    & $Python -B -m trading_agent.market_data.backfill --approved-history-only --approval-directory $approval --dataset-directory $DatasetDirectory
    exit $LASTEXITCODE
} finally { $env:PYTHONPATH = $previous }
