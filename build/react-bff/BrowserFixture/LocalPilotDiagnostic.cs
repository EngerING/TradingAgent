using System.Text.Json;
using Microsoft.Extensions.Logging;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.React.BrowserFixture;

// Never call a logger formatter: it may contain exceptions, request data or credentials.
public sealed class LocalPilotDiagnostic(string path) : ILoggerProvider, ILogger
{
    private readonly object gate = new();
    private int count;
    public ILogger CreateLogger(string categoryName) => this;
    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(LogLevel logLevel) => true;
    public void Dispose() { }
    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
    {
        if (state is not IEnumerable<KeyValuePair<string, object?>> fields) return;
        object? document = null;
        if (eventId.Id == 1302)
        {
            var value = fields.FirstOrDefault(p => p.Key == "DiagnosticCode").Value;
            if (value is AuthDiagnostic diagnostic && Enum.IsDefined(diagnostic)) document = new { diagnostic = diagnostic.ToString() };
        }
        if (eventId.Id == 1301)
        {
            var operation = fields.FirstOrDefault(p => p.Key == "OperationCode").Value as string;
            var status = fields.FirstOrDefault(p => p.Key == "StatusCode").Value;
            if (operation is "AUTH" or "SESSION" or "SYNTHETIC_PROBE" or "OTHER" && status is int code && code is >= 100 and <= 599)
                document = new { operation, httpStatus = code };
        }
        if (eventId.Id == 1303 && fields.FirstOrDefault(p => p.Key == "VerifiedCount").Value is int verified &&
            fields.FirstOrDefault(p => p.Key == "UnverifiedCount").Value is int unverified &&
            verified is >= 0 and <= 10 && unverified is >= 0 and <= 10 && verified + unverified <= 10)
            document = new { stage = "JWT_USER_ACCEPTED", verifiedFactors = verified, unverifiedFactors = unverified };
        if (document is null) return;
        lock (gate)
        {
            if (count++ >= 1024) return;
            File.AppendAllText(path, JsonSerializer.Serialize(document) + "\n");
        }
    }
}
