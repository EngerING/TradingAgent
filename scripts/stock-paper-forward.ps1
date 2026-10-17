param([Parameter(Mandatory=$true)][ValidateSet('Inspect','Study','Status','Authorize','Run','Stop','Revoke')][string]$Action)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$priorPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH=Join-Path $root 'python'
    $python=Join-Path $root '.venv/Scripts/python.exe'
    if($Action -eq 'Authorize') {
        # This must pass every gate, including the unchanged productive ceiling,
        # before prompting or writing a grant. Never uses Forex authorization.
        $result=& $python -m trading_agent.stock_paper_forward Inspect --root $root
        if($LASTEXITCODE -ne 0){throw 'STOCK_FORWARD_INSPECTION_FAILED'}
        $report=$result | ConvertFrom-Json
        if($report.identity_verified -ne $true -or $report.complete -ne $true -or @($report.blockers).Count -ne 0){
            Write-Output ($report.blockers | ConvertTo-Json -Compress)
            throw 'STOCK_FORWARD_AUTHORIZATION_BLOCKED_NO_GRANT_WRITTEN'
        }
        foreach($name in @('paper-lab.emergency','paper-auto.stop','stock-paper-forward.stop')){
            if(Test-Path -LiteralPath (Join-Path $root ('.local/'+$name))){throw 'PROTECTED_EMERGENCY_REVIEW_REQUIRED_NO_GRANT_WRITTEN'}
        }
        if((Read-Host 'Verifica Paper, API habilitada y exclusividad de Ford. H40 no acredita rentabilidad. Escribe AUTHORIZE_H40_PAPER_FORWARD_ONLY') -cne 'AUTHORIZE_H40_PAPER_FORWARD_ONLY'){throw 'OWNER_AUTHORIZATION_REQUIRED'}
        # Operator input cannot turn a stale quote/account query into readiness.
        $fresh=& $python -m trading_agent.stock_paper_forward Inspect --root $root
        if($LASTEXITCODE -ne 0){throw 'STOCK_FORWARD_INSPECTION_FAILED'}
        $report=$fresh | ConvertFrom-Json
        if($report.identity_verified -ne $true -or @($report.blockers).Count -ne 0){throw 'FRESH_STOCK_FORWARD_READINESS_BLOCKED'}
        Add-Type -AssemblyName System.Security
        $path=Join-Path $root '.local/ibkr-account-binding.dpapi'
        $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($path),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        try {$binding=[Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json} finally {[Array]::Clear($plain,0,$plain.Length)}
        $transport=Get-Content -LiteralPath (Join-Path $root 'config/ibkr-session.json') -Raw | ConvertFrom-Json
        $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $transport.port | Select-Object -ExpandProperty OwningProcess -Unique)
        if($listeners.Count -ne 1 -or $binding.binding_id -cne $report.binding_id){throw 'TWS_EXACT_SESSION_REQUIRED'}
        $tws=Get-Process -Id $listeners[0]
        $hashes=& $python -c 'import json; from pathlib import Path; from trading_agent.stock_paper_forward import source_hashes; print(json.dumps(source_hashes(Path.cwd())))'
        if($LASTEXITCODE -ne 0){throw 'SOURCE_ATTESTATION_FAILED'}
        $c=Get-Content (Join-Path $root 'config/stock-paper-forward.json') -Raw | ConvertFrom-Json
        $now=[DateTimeOffset]::UtcNow
        $grant=[ordered]@{schema_version=1;scope='H40_STOCK_PAPER_FORWARD_ONLY';environment='PAPER_TRADING';live_enabled=$false;
            account=$binding.account;binding_id=$binding.binding_id;strategy_version=$c.strategy_version;capital_usd=100;maximum_exposure=1;risk_percent=2;
            config_sha256=(Get-FileHash (Join-Path $root 'config/stock-paper-forward.json') -Algorithm SHA256).Hash.ToLowerInvariant();
            source_hashes=($hashes | ConvertFrom-Json);host=$transport.host;port=$transport.port;client_id=93;
            tws_pid=$tws.Id;tws_start_filetime=$tws.StartTime.ToFileTimeUtc().ToString();read_only_disabled_checked=$true;
            issued_at=$now.ToString('o');expires_at=$now.AddHours($c.authorization_hours).ToString('o');revoked=$false;manage_owned_after_stop=$true}
        $dest=Join-Path $root '.local/stock-paper-forward.dpapi'
        if(Test-Path -LiteralPath $dest){throw 'EXISTING_STOCK_GRANT_MUST_BE_REVIEWED_NO_OVERWRITE'}
        $bytes=[Text.Encoding]::UTF8.GetBytes(($grant | ConvertTo-Json -Depth 12 -Compress))
        try {
            $sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
            $stream=[IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try {$stream.Write($sealed,0,$sealed.Length);$stream.Flush($true)} finally {$stream.Dispose()}
        } finally {[Array]::Clear($bytes,0,$bytes.Length)}
        Write-Output 'H40_PAPER_FORWARD_AUTHORIZED; NO_ORDER_SENT; LIVE_DISABLED'
    } else {
        & $python -m trading_agent.stock_paper_forward $Action --root $root
        if($LASTEXITCODE -ne 0){throw 'STOCK_FORWARD_BLOCKED_SEE_SANITIZED_REASON'}
    }
} finally {$env:PYTHONPATH=$priorPath}
