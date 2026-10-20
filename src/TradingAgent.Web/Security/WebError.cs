namespace TradingAgent.Web.Security;

public enum WebErrorCode { NotFound, MethodNotAllowed, ServiceUnavailable, InternalError }

/// <summary>No caller-provided message, exception, credential or correlation identifier is echoed.</summary>
public sealed class WebError
{
    private WebError(string code)
    {
        Code = code;
        CorrelationId = Guid.NewGuid();
    }

    public string Code { get; }
    public Guid CorrelationId { get; }

    public static WebError Create(WebErrorCode code) => new(code switch
    {
        WebErrorCode.NotFound => "NOT_FOUND",
        WebErrorCode.MethodNotAllowed => "METHOD_NOT_ALLOWED",
        WebErrorCode.ServiceUnavailable => "SERVICE_UNAVAILABLE",
        WebErrorCode.InternalError => "INTERNAL_ERROR",
        _ => throw new ArgumentOutOfRangeException(nameof(code))
    });
}
