namespace TradingAgent.Core;

public sealed record BrokerOptions(string Environment = "PAPER_TRADING", bool LiveEnabled = false,
    string Host = "127.0.0.1", int Port = 7497, string AuthorizedAccount = "SIM-PAPER", int VerifiedTwsPort = 7497)
{
    public void Validate()
    {
        if (LiveEnabled || Environment != "PAPER_TRADING") throw new InvalidOperationException("LIVE_DISABLED");
        if (Host != "127.0.0.1" || Port < 1 || Port > 65535 || Port != VerifiedTwsPort || string.IsNullOrWhiteSpace(AuthorizedAccount))
            throw new InvalidOperationException("UNVERIFIED_PAPER_CONFIGURATION");
    }
}
public sealed record BrokerBalance(string AccountId, decimal Equity, decimal AvailableFunds, DateTimeOffset At);
public sealed record BrokerPosition(string Instrument, decimal Quantity, decimal MarketValue);
public sealed record Quote(string Instrument, decimal Bid, decimal Ask, DateTimeOffset At);
public sealed record Candle(DateTimeOffset OpenTime, int Minutes, decimal Open, decimal High, decimal Low, decimal Close, decimal? Volume);
public interface IBrokerData
{
    bool Connected { get; }
    Task ConnectAsync(CancellationToken ct);
    Task DisconnectAsync(CancellationToken ct);
    Task<BrokerBalance> BalanceAsync(CancellationToken ct);
    Task<IReadOnlyList<BrokerPosition>> PositionsAsync(CancellationToken ct);
    Task<Quote> QuoteAsync(string instrument, CancellationToken ct);
    Task<IReadOnlyList<Candle>> HistoryAsync(string instrument, int minutes, CancellationToken ct);
    // Deliberately no order, cancel, or transmit method.
}
public sealed class SimulatedBroker(BrokerOptions options, TimeProvider clock) : IBrokerData
{
    public bool Connected { get; private set; }
    public bool FailConnection { get; set; }
    public Task ConnectAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested(); options.Validate();
        if (FailConnection) throw new IOException("SIMULATED_CONNECTION_LOSS");
        if (options.AuthorizedAccount != "SIM-PAPER") throw new InvalidOperationException("UNAUTHORIZED_ACCOUNT");
        Connected = true; return Task.CompletedTask;
    }
    public Task DisconnectAsync(CancellationToken ct) { Connected=false; return Task.CompletedTask; }
    private void Check(CancellationToken ct) { ct.ThrowIfCancellationRequested(); if (!Connected || FailConnection) { Connected=false; throw new IOException("BROKER_DISCONNECTED"); } }
    public Task<BrokerBalance> BalanceAsync(CancellationToken ct) { Check(ct); return Task.FromResult(new BrokerBalance("SIM-PAPER",100,100,clock.GetUtcNow())); }
    public Task<IReadOnlyList<BrokerPosition>> PositionsAsync(CancellationToken ct) { Check(ct); return Task.FromResult<IReadOnlyList<BrokerPosition>>([]); }
    public Task<Quote> QuoteAsync(string instrument, CancellationToken ct)
    { Check(ct); if(instrument!="EUR/USD") throw new ArgumentException("Instrument unavailable"); return Task.FromResult(new Quote(instrument,1.0999m,1.1001m,clock.GetUtcNow())); }
    public Task<IReadOnlyList<Candle>> HistoryAsync(string instrument,int minutes,CancellationToken ct)
    {
        Check(ct); if (instrument!="EUR/USD" || minutes is not (15 or 60 or 240)) throw new ArgumentException("Unsupported series");
        var end = DateTimeOffset.FromUnixTimeSeconds(clock.GetUtcNow().ToUnixTimeSeconds()/(minutes*60)*(minutes*60));
        return Task.FromResult<IReadOnlyList<Candle>>(Enumerable.Range(0,100).Select(i=>new Candle(end.AddMinutes((i-100)*minutes),minutes,1.1m,1.102m,1.098m,1.1m,null)).ToArray());
    }
}
