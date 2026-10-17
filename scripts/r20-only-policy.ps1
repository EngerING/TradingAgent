# Entry-point retirement only. This never authorizes or executes an operation.
# Recovery still requires every existing scope, consent and reconciliation guard.
function Assert-R20OnlyLegacyAction {
    param([Parameter(Mandatory=$true)][string]$Entry,[Parameter(Mandatory=$true)][string]$Action)
    $allowed=@{
        'eurusd-shadow-research'=@('Status','Stop','Comparison')
        'eurusd-paper-exploratory'=@('Inspect','Assess','RecoveryInspect','Status','AuthorizeRecovery','Recovery','Stop','Revoke')
        # Run/Once also manage existing virtual inventory after Stop. Keep that
        # recovery path until entry and management are separated in its hashed engine.
        'r10-price-risk'=@('Assess','Status','Stop','PaperPlan','Run','Once')
        'eurusd-cost-aware-research'=@('Status','Stop')
        'eurusd-paper-research'=@('Backtest','Observe')
    }
    if(-not $allowed.ContainsKey($Entry) -or $Action -notin $allowed[$Entry]) {
        throw 'LEGACY_OPERATION_RETIRED_R20_ONLY: new legacy experiments, openings and entry grants are disabled at this wrapper.'
    }
}
