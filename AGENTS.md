# TradingAgent branch and preservation rules

Use `develop` as the integration base. Fetch remote refs and update develop only by
fast-forward when safe. New work uses feature/, fixes use fix/, approved release
preparation uses release/. Preserve all historical M01/Core branches.

`main` is stable and requires separately approved integration. No direct experimental
push, forced push, branch deletion, automatic merge, deployment or financial activation.
Create PRs to develop; review CI and preservation before requesting integration approval.
No merge is authorized merely by a green workflow. Run integration regressions after
an authorized merge. Do not change GitHub's default branch without explicit approval.

Bootstrap develop was explicitly authorized at cd25a103b177d43a59f9d99c8047c0db3d20abbb.
It includes experimental M01.3B and is not approved for deployment or real trading.

For M01.4A, add React only in frontend-react/. Preserve all843 baseline tracked files,
the three preexisting untracked documents/scripts, Vue, Core, Market Analyst, all
financial services and eleven historical SQL migrations. OFFLINE / NO_TRADE.
Never connect hosted Supabase, IBKR, financial databases or AI to validate frontend fixtures.
Never collect real passwords or TOTP codes for the development UI. Browser callbacks
remain fail-closed until a separately reviewed BFF exchange is implemented.
