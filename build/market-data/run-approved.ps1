param(
    [string]$Python = '.venv/Scripts/python.exe',
    [string]$ApprovalDirectory,
    [string]$ArchiveDirectory,
    [switch]$ApprovedDataOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $repo
if (-not $ApprovedDataOnly) {
    Write-Output 'OFFLINE / NO_TRADE; no endpoint contacted. Future supervised reading requires external host approval.'
    exit 0
}
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) { throw 'M03_WINDOWS_REQUIRED' }
if (-not $ApprovalDirectory -or -not $ArchiveDirectory) { throw 'M03_LOCAL_INPUTS_REQUIRED' }
$approval = (Resolve-Path -LiteralPath $ApprovalDirectory).Path
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($current,'S-1-5-18','S-1-5-32-544')
foreach ($name in @('config.json','capture-grant.json','data-permit.json','signatures.json','verification.key')) {
    $file = Get-Item -LiteralPath (Join-Path $approval $name)
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint -or $file.Length -gt 4096) { throw 'M03_LOCAL_FILE_REJECTED' }
    $acl = Get-Acl -LiteralPath $file.FullName
    foreach ($rule in $acl.Access) {
        $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($rule.AccessControlType -eq 'Allow' -and $sid -notin $allowed) { throw 'M03_LOCAL_ACL_REJECTED' }
    }
}
$previous = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'python'
    Write-Output 'IBKR_DATA_ONLY requested / NO_TRADE. Foreground process; Ctrl+C stops. Accounts and secrets remain local.'
    & $Python -B -m trading_agent.market_data --approved-data-only --approval-directory $approval --archive-directory $ArchiveDirectory
    exit $LASTEXITCODE
} finally { $env:PYTHONPATH = $previous }
