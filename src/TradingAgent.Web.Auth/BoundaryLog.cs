using Microsoft.Extensions.Logging;

namespace TradingAgent.Web.Auth;

internal static partial class BoundaryLog
{
    [LoggerMessage(EventId = 1302, Level = LogLevel.Warning, Message = "BFF Auth rejection {DiagnosticCode}")]
    internal static partial void AuthRejected(ILogger logger, TradingAgent.Identity.Supabase.AuthDiagnostic diagnosticCode);
    [LoggerMessage(EventId = 1303, Level = LogLevel.Information, Message = "BFF JWT and user accepted; factors verified {VerifiedCount}, unverified {UnverifiedCount}")]
    internal static partial void Inventory(ILogger logger, int verifiedCount, int unverifiedCount);
    // Closed operation category and numeric status only: no request path, identity, body or headers.
    [LoggerMessage(EventId = 1301, Level = LogLevel.Information, Message = "BFF boundary {OperationCode} completed with {StatusCode}")]
    internal static partial void Completed(ILogger logger, string operationCode, int statusCode);
}
