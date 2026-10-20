using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace TradingAgent.Auth.Tests;

public sealed class CollectedLogs : ILoggerProvider
{
    public ConcurrentQueue<string> Events { get; } = new();
    public ILogger CreateLogger(string categoryName) => new Collector(Events);
    public void Dispose() { GC.SuppressFinalize(this); }
    private sealed class Collector(ConcurrentQueue<string> events) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) => events.Enqueue(formatter(state, exception));
    }
}
