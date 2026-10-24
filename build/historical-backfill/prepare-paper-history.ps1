param(
    [Parameter(Mandatory=$true)][string]$StartUtc,
    [Parameter(Mandatory=$true)][string]$EndUtc,
    [string]$Python = '.venv/Scripts/python.exe',
    [string]$ApprovalDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) {
    throw 'M032_WINDOWS_REQUIRED'
}
if (-not $env:LOCALAPPDATA) { throw 'M032_LOCALAPPDATA_REQUIRED' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $repo

Write-Output 'M03-A.2 / PREPARACION LOCAL, SOLO HISTORICOS PAPER. NO ABRE TWS.'
$paper = Read-Host 'Confirmas visualmente que TWS esta en PAPER? (SI/NO)'
$market = Read-Host 'Confirmas permisos de lectura historica en TWS? (SI/NO)'
$readonly = Read-Host 'Confirmas que Read-Only API esta DESMARCADO? (SI/NO)'
if ($paper -cne 'SI' -or $market -cne 'SI' -or $readonly -cne 'SI') {
    throw 'M032_HOST_CONFIRMATION_REQUIRED'
}

if (-not $ApprovalDirectory) {
    $parent = Join-Path $env:LOCALAPPDATA 'TradingAgent/history-approvals'
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $unique = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' +
        [Guid]::NewGuid().ToString('N').Substring(0, 10)
    $ApprovalDirectory = Join-Path $parent $unique
}
if (Test-Path -LiteralPath $ApprovalDirectory) {
    throw 'M032_NEW_EMPTY_DIRECTORY_REQUIRED'
}
New-Item -ItemType Directory -Path $ApprovalDirectory -ErrorAction Stop | Out-Null
$approval = (Resolve-Path -LiteralPath $ApprovalDirectory).Path
if ((Get-Item -LiteralPath $approval).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'M032_LOCAL_REPARSE_POINT'
}

# Remove inherited permissions BEFORE writing the signing key.
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$ids = @(
    [Security.Principal.WindowsIdentity]::GetCurrent().User,
    (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')),
    (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544'))
)
$inherit = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
foreach ($id in $ids) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $id,
        [Security.AccessControl.FileSystemRights]::FullControl,
        $inherit,
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $approval -AclObject $acl
$previous = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo 'python'
    & $Python -B -m trading_agent.market_data.backfill.host_provisioner `
        --start-utc $StartUtc `
        --end-utc $EndUtc `
        --approval-directory $approval `
        --confirm-paper --confirm-market-data --confirm-read-only-disabled
    if ($LASTEXITCODE -ne 0) { throw 'M032_PREPARATION_FAILED' }
    Write-Output 'Permiso firmado localmente. Sin conexión TWS ni ordenes.'
    Write-Output ('Directorio de permisos: ' + $approval)
    Write-Output 'Validez de 30 minutos. Para lectura historica futura usa run-approved.ps1 bajo supervision.'
} finally {
    $env:PYTHONPATH = $previous
}
