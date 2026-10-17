namespace TradingAgent.Api;

public sealed class LegacyOperationRetirement(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context)
    {
        var path=context.Request.Path.Value?.TrimEnd('/');
        if(HttpMethods.IsPost(context.Request.Method) &&
            new[]{"/simulation/accounts","/simulation/strategies","/simulation/decisions"}
                .Contains(path,StringComparer.OrdinalIgnoreCase))
        {
            context.Response.StatusCode=StatusCodes.Status410Gone;
            await context.Response.WriteAsJsonAsync(new{error="LEGACY_OPERATION_RETIRED_R20_ONLY",
                ordersSupported=false,liveEnabled=false});
            return;
        }
        // Authentication, read access, settlement and emergency guards remain
        // owned by their existing handlers. Passing here is not authorization.
        await next(context);
    }
}
