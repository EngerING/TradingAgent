namespace TradingAgent.Core;

// Trading amounts are USD. Transfers are project expenses, never trading P&L.
// The loss allowance belongs to the allocation, not a day, strategy or process.
public sealed record VirtualCapital(
    decimal InitialCapital, decimal LossAllowance = 20m,
    decimal RealizedGrossPnl = 0m, decimal UnrealizedGrossPnl = 0m,
    decimal RealizedCosts = 0m, decimal OpenCosts = 0m,
    decimal CumulativeRealizedLoss = 0m, decimal TransferCosts = 0m,
    string Environment = "SIMULATION", string AllocationVersion = "allocation-v1")
{
    public decimal RealizedNetPnl => RealizedGrossPnl - RealizedCosts;
    public decimal UnrealizedNetPnl => UnrealizedGrossPnl - OpenCosts;
    public decimal Equity => InitialCapital + RealizedNetPnl + UnrealizedNetPnl;
    public decimal TradingCosts => RealizedCosts + OpenCosts;
    public decimal EconomicResult => RealizedNetPnl + UnrealizedNetPnl - TransferCosts;
    public decimal ConsumedLoss => CumulativeRealizedLoss + Math.Max(0, -UnrealizedNetPnl);
    public decimal SuspensionEquity => InitialCapital - LossAllowance;
    public decimal RemainingLoss => Math.Max(0, Math.Min(LossAllowance - ConsumedLoss, Equity - SuspensionEquity));

    public void Validate()
    {
        if (InitialCapital <= 0 || LossAllowance <= 0 || LossAllowance >= InitialCapital ||
            RealizedCosts < 0 || OpenCosts < 0 || CumulativeRealizedLoss < 0 || TransferCosts < 0 ||
            Environment is not ("SIMULATION" or "PAPER_TRADING") || string.IsNullOrWhiteSpace(AllocationVersion))
            throw new ArgumentException("INVALID_VIRTUAL_CAPITAL");
    }

    public VirtualCapital Mark(decimal equity, decimal openCosts = 0m)
    {
        if (openCosts < 0) throw new ArgumentException("Negative costs");
        return this with { UnrealizedGrossPnl = equity - InitialCapital - RealizedNetPnl + openCosts, OpenCosts = openCosts };
    }

    // Net P&L already includes observed costs. Add them back only to report gross P&L.
    public VirtualCapital Settle(decimal netPnl, decimal observedCosts)
    {
        if (observedCosts < 0) throw new ArgumentException("Negative costs");
        return this with { RealizedGrossPnl = RealizedGrossPnl + netPnl + observedCosts,
            RealizedCosts = RealizedCosts + observedCosts, UnrealizedGrossPnl = 0, OpenCosts = 0,
            CumulativeRealizedLoss = CumulativeRealizedLoss + Math.Max(0, -netPnl) };
    }
}

public sealed record CapitalProtection(string Level, decimal RiskFactor, decimal ExposureFactor);
