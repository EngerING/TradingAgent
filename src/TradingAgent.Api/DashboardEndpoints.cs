using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.FileProviders;
using TradingAgent.Infrastructure;
namespace TradingAgent.Api;

public sealed record DashboardLogin(string Token);
public static class DashboardEndpoints
{
    public static void AddDashboard(this WebApplicationBuilder builder)
    {
        var config=DashboardConfiguration.Load();builder.Services.AddSingleton(config);
        var connection=Environment.GetEnvironmentVariable("TRADING_LAB_DB")??Environment.GetEnvironmentVariable("TRADING_DB")??throw new InvalidOperationException("DASHBOARD_DATABASE_REQUIRED");
        builder.Services.AddSingleton(new DashboardStore(connection));
        builder.Services.AddSingleton<IDashboardSource,DashboardSource>();builder.Services.AddSingleton<SolChatService>();
        builder.Services.AddHttpClient<ISolInterpretation,OpenAiSolInterpretation>().ConfigurePrimaryHttpMessageHandler(()=>new SocketsHttpHandler{AllowAutoRedirect=false,UseCookies=false});
        builder.Services.AddSignalR(o=>{o.MaximumReceiveMessageSize=16*1024;o.EnableDetailedErrors=false;});
        builder.Services.AddHostedService<DashboardBroadcaster>();
        builder.Services.AddAuthentication("Dashboard").AddCookie("Dashboard",o=>
        {
            o.Cookie.Name="TradingAgent.ReadOnly";o.Cookie.HttpOnly=true;o.Cookie.SameSite=SameSiteMode.Strict;o.Cookie.SecurePolicy=CookieSecurePolicy.SameAsRequest;
            o.ExpireTimeSpan=TimeSpan.FromHours(8);o.SlidingExpiration=false;
            o.Events.OnRedirectToLogin=c=>{c.Response.StatusCode=401;return Task.CompletedTask;};
            o.Events.OnRedirectToAccessDenied=c=>{c.Response.StatusCode=403;return Task.CompletedTask;};
        });
        builder.Services.AddAuthorization();
        var keys=builder.Services.AddDataProtection().SetApplicationName("TradingAgent.ReadOnlyDashboard").PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(config.Root,".local","dashboard-cookie-keys")));
        if(OperatingSystem.IsWindows())keys.ProtectKeysWithDpapi();
    }
    public static bool UiPath(PathString path)=>path.StartsWithSegments("/api/ui") || path.StartsWithSegments("/hubs/dashboard");
    public static bool TrustedOrigin(string? origin)=>origin is null || origin=="http://127.0.0.1:5080" || origin=="http://127.0.0.1:5173";
    public static bool TrustedHost(HostString host)=>host.Host is "127.0.0.1" && host.Port is 5080 or 5173;
    public static bool PublicUi(HttpRequest r)=>r.Path is var p && (p=="/api/ui/session" || r.Method=="GET" &&
        !p.StartsWithSegments("/api") && !p.StartsWithSegments("/hubs") && !p.StartsWithSegments("/simulation") && !p.StartsWithSegments("/safety") && !p.StartsWithSegments("/research") && !p.StartsWithSegments("/experiences") && p!="/policy");
    public static bool SessionAuthorized(HttpContext c)=>c.User.Identity?.IsAuthenticated==true && c.User.HasClaim("scope","dashboard-readonly");
    public static void MapDashboard(this WebApplication app,string? dashboardToken)
    {
        // Retire legacy creation after the host's authentication boundary.
        app.UseMiddleware<LegacyOperationRetirement>();
        var expected=dashboardToken is not null && dashboardToken.Length>=32?SHA256.HashData(Encoding.UTF8.GetBytes(dashboardToken)):null;var failures=0;var waitUntil=DateTimeOffset.MinValue;var loginGate=new object();
        app.MapPost("/api/ui/session",async(DashboardLogin login,HttpContext c)=>
        {
            lock(loginGate)
            {
                if(expected is null)return Results.StatusCode(503);
                if(DateTimeOffset.UtcNow<waitUntil)return Results.StatusCode(429);
                if(login.Token is null || login.Token.Length>512 || !CryptographicOperations.FixedTimeEquals(expected,SHA256.HashData(Encoding.UTF8.GetBytes(login.Token))))
                {if(++failures>=5){waitUntil=DateTimeOffset.UtcNow.AddMinutes(1);failures=0;}return Results.Unauthorized();}
                failures=0;
            }
            var identity=new ClaimsIdentity(new[]{new Claim(ClaimTypes.Name,"local-operator"),new Claim("scope","dashboard-readonly")},"Dashboard");
            await c.SignInAsync("Dashboard",new ClaimsPrincipal(identity));return Results.Ok(new{authenticated=true,scope="dashboard-readonly",executionAuthorized=false});
        });
        app.MapGet("/api/ui/session",(HttpContext c)=>SessionAuthorized(c)?Results.Ok(new{authenticated=true,scope="dashboard-readonly"}):Results.Unauthorized());
        app.MapDelete("/api/ui/session",async(HttpContext c)=>{await c.SignOutAsync("Dashboard");return Results.Ok();});
        app.MapGet("/api/ui/dashboard",(IDashboardSource s,CancellationToken ct)=>s.Read(ct));
        app.MapGet("/api/ui/system/status",async(IDashboardSource s,CancellationToken ct)=>(await s.Read(ct)).GetProperty("system"));
        app.MapGet("/api/ui/experiments",async(IDashboardSource s,CancellationToken ct)=>(await s.Read(ct)).GetProperty("experiments"));
        app.MapGet("/api/ui/experiments/{id}",async(string id,IDashboardSource s,CancellationToken ct)=>
        {var e=(await s.Read(ct)).GetProperty("experiments").EnumerateArray().FirstOrDefault(x=>x.GetProperty("id").GetString()==id);return e.ValueKind==JsonValueKind.Undefined?Results.NotFound():Results.Ok(e);});
        app.MapGet("/api/ui/experiments/{id}/equity",async(string id,IDashboardSource s,CancellationToken ct)=>
        {var e=(await s.Read(ct)).GetProperty("experiments").EnumerateArray().FirstOrDefault(x=>x.GetProperty("id").GetString()==id);return e.ValueKind==JsonValueKind.Undefined?Results.NotFound():Results.Ok(e.GetProperty("equityCurve"));});
        foreach(var (path,field) in new[]{("trades","trades"),("trades/open","openPositions"),("market/eurusd","market"),("predictions/current","prediction"),("calibration","calibration"),("research","research"),("kronos","kronos")})
        {var key=field;app.MapGet("/api/ui/"+path,async(IDashboardSource s,CancellationToken ct)=>(await s.Read(ct)).GetProperty(key));}
        app.MapPost("/api/ui/sol/chat",async(SolRequest r,SolChatService sol,Microsoft.AspNetCore.SignalR.IHubContext<DashboardHub> hub,CancellationToken ct)=>
        {var response=await sol.Chat(r,ct);await hub.Clients.All.SendCoreAsync("analysisCompleted",[new{requestId=r.RequestId}],ct);return response;});
        app.MapPost("/api/ui/commands/preview",(SolRequest r)=>new{command=SolCommandParser.Parse(r.Message),executionEnabled=false});
        app.MapPost("/api/ui/commands/confirm",()=>Results.Json(new{error="COMMAND_EXECUTION_DISABLED"},statusCode:403));
        app.MapHub<DashboardHub>("/hubs/dashboard",o=>o.CloseOnAuthenticationExpiration=true);
        var config=app.Services.GetRequiredService<DashboardConfiguration>();var dist=Path.Combine(config.Root,"frontend","dist");
        if(Directory.Exists(dist))
        {
            app.UseStaticFiles(new StaticFileOptions{FileProvider=new PhysicalFileProvider(dist),OnPrepareResponse=c=>c.Context.Response.Headers.CacheControl=c.File.Name=="index.html"?"no-cache":"public,max-age=3600"});
            app.MapFallback(async c=>{if(c.Request.Path.StartsWithSegments("/api")||c.Request.Path.StartsWithSegments("/hubs")){c.Response.StatusCode=404;return;}c.Response.ContentType="text/html";await c.Response.SendFileAsync(Path.Combine(dist,"index.html"));});
        }
    }
}
