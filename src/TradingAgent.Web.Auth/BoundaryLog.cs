using Microsoft.Extensions.Logging;

namespace TradingAgent.Web.Auth;

internal static partial class BoundaryLog
{
    // Closed operation category and numeric status only: no request path, identity, body or headers.
    [LoggerMessage(EventId = 1301, Level = LogLevel.Information, Message = "BFF boundary {OperationCode} completed with {StatusCode}")]
    internal static partial void Completed(ILogger logger, string operationCode, int statusCode);
}
