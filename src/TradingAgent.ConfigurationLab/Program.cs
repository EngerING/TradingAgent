using System.Diagnostics;
using System.Net;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.FileProviders;

// Standalone TEST host: no reference to broker, Infrastructure, operational API or runner.
const string origin = "http://127.0.0.1:5182";
var root = Path.GetFullPath(Environment.GetEnvironmentVariable("R20_LAB_ROOT") ?? throw new InvalidOperationException("R20_LAB_ROOT required"));
string Required(string key) => Environment.GetEnvironmentVariable(key) ?? throw new InvalidOperationException(key + " required");
var readerToken = Required("R20_LAB_READER_TOKEN");
var adminToken = Required("R20_LAB_ADMIN_TOKEN");
if (readerToken.Length < 32 || adminToken.Length < 32 || readerToken == adminToken) throw new InvalidOperationException("Distinct test credentials required");
var database = Required("R20_V2_TEST_DATABASE");
var systemId = Required("R20_V2_TEST_SYSTEM_ID");
var contextFile = Path.GetFullPath(Required("R20_V2_CONTEXT"));
var uiPath = Path.GetFullPath(Required("R20_LAB_UI"));
var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls(origin);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 16384);
builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
builder.Services.AddAuthentication("R20Lab").AddCookie("R20Lab", o => {
    o.Cookie.Name = "TradingAgent.R20.ConfigurationLab";
    o.Cookie.HttpOnly = true; o.Cookie.SameSite = SameSiteMode.Strict;
    o.ExpireTimeSpan = TimeSpan.FromMinutes(60); o.SlidingExpiration = false;
    o.Events.OnRedirectToLogin = c => { c.Response.StatusCode = 401; return Task.CompletedTask; };
    o.Events.OnRedirectToAccessDenied = c => { c.Response.StatusCode = 403; return Task.CompletedTask; };
});
builder.Services.AddAuthorization(o => o.AddPolicy("ConfigAdmin", p => p.RequireRole("config-admin")));
builder.Services.AddRateLimiter(o => {
    o.RejectionStatusCode=429;
    o.AddFixedWindowLimiter("LabLogin",policy=>{
        policy.PermitLimit=20;policy.Window=TimeSpan.FromMinutes(15);
        policy.QueueLimit=0;policy.AutoReplenishment=true;
    });
});
var bridge = new ConfigurationBridge(root, database, systemId, contextFile);
var app = builder.Build();
app.Use(async (c,next) => {
    if (c.Request.Host.Value != "127.0.0.1:5182" || c.Connection.RemoteIpAddress is not { } ip || !IPAddress.IsLoopback(ip)) { c.Response.StatusCode=403; return; }
    if (c.Request.Method != "GET" && (c.Request.Headers.Origin != origin || c.Request.Headers["X-R20-Configuration"] != "1")) { c.Response.StatusCode=403; return; }
    c.Response.Headers.ContentSecurityPolicy="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
    c.Response.Headers.XContentTypeOptions="nosniff";
    c.Response.Headers.CacheControl="no-store";
    await next();
});
app.UseAuthentication();app.UseAuthorization();
app.UseRateLimiter();
app.MapPost("/api/r20-v2/session", async (HttpContext c, Login login) => {
    static bool Match(string a,string b) => CryptographicOperations.FixedTimeEquals(SHA256.HashData(Encoding.UTF8.GetBytes(a)),SHA256.HashData(Encoding.UTF8.GetBytes(b)));
    var role=Match(login.Credential ?? "",adminToken)?"config-admin":Match(login.Credential ?? "",readerToken)?"config-reader":null;
    if(role is null)return Results.Unauthorized();
    var principal=new ClaimsPrincipal(new ClaimsIdentity(new[]{new Claim(ClaimTypes.Name,"lab-"+role),new Claim(ClaimTypes.Role,role)},"R20Lab"));
    await c.SignInAsync("R20Lab",principal);
    return Results.Ok(new {role,executionEnabled=false,ordersSupported=false});
}).RequireRateLimiting("LabLogin");
app.MapGet("/api/r20-v2/session",(HttpContext c)=>Results.Ok(new {role=c.User.FindFirstValue(ClaimTypes.Role)})).RequireAuthorization();
app.MapPost("/api/r20-v2/logout",async(HttpContext c)=>{await c.SignOutAsync("R20Lab");return Results.NoContent();}).RequireAuthorization();
app.MapGet("/api/r20-v2/configuration",(Delegate)((HttpContext c)=>bridge.Call("view",new {},c))).RequireAuthorization();
app.MapGet("/api/r20-v2/configuration/history",(Delegate)((HttpContext c)=>bridge.Call("view",new {},c))).RequireAuthorization();
app.MapGet("/api/r20-v2/shadow",(Delegate)((HttpContext c)=>bridge.Call("monitor",new {},c))).RequireAuthorization();
app.MapPost("/api/r20-v2/configuration/preview",(HttpContext c,JsonElement body)=>bridge.Call("preview",body,c)).RequireAuthorization();
app.MapGet("/api/r20-v2/preparation",(Delegate)((HttpContext c)=>bridge.Call("preparation-view",new {},c))).RequireAuthorization();
app.MapPost("/api/r20-v2/preparation/preview",(HttpContext c,JsonElement body)=>bridge.Call("preparation-preview",body,c)).RequireAuthorization();
foreach(var action in new[]{"save","validate"}) {
    var selected=action;
    app.MapPost("/api/r20-v2/preparation/"+selected,(HttpContext c,JsonElement body)=>bridge.Call("preparation-"+selected,body,c)).RequireAuthorization("ConfigAdmin");
}
// Explicit contract: visual controls cannot create operational authority in this host.
foreach(var action in new[]{"start","stop","switch","activate"}) {
    app.MapPost("/api/r20-v2/preparation/"+action,()=>Results.Json(new {error="OPERATIONAL_CONTROL_DISABLED"},statusCode:409)).RequireAuthorization("ConfigAdmin");
}
foreach(var action in new[]{"draft","validate","activate"}) {
    var selected=action;
    app.MapPost("/api/r20-v2/configuration/"+selected,(HttpContext c,JsonElement body)=>bridge.Call(selected,body,c)).RequireAuthorization("ConfigAdmin");
}
app.UseStaticFiles(new StaticFileOptions {FileProvider=new PhysicalFileProvider(uiPath)});
app.MapGet("/",()=>Results.Redirect("/r20-config.html"));
app.Run();

internal sealed record Login(string? Credential);
internal sealed class ConfigurationBridge(string root,string database,string systemId,string contextFile)
{
    private readonly SemaphoreSlim capacity=new(4,4);
    public async Task<IResult> Call(string action,object body,HttpContext context)
    {
        if(!await capacity.WaitAsync(0,context.RequestAborted))return Results.StatusCode(429);
        try {
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted);
            timeout.CancelAfter(TimeSpan.FromSeconds(45));
            var info=new ProcessStartInfo(Path.Combine(root,".venv","Scripts","python.exe")) {
                UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=root
            };
            info.ArgumentList.Add("-m");info.ArgumentList.Add("trading_agent.r20_configuration");
            info.Environment.Clear();
            foreach(var key in new[]{"PATH","SYSTEMROOT","TEMP","TMP"})if(Environment.GetEnvironmentVariable(key) is {} value)info.Environment[key]=value;
            info.Environment["PYTHONPATH"]=Path.Combine(root,"python");info.Environment["PYTHONIOENCODING"]="utf-8";
            info.Environment["R20_V2_TEST_DATABASE"]=database;info.Environment["R20_V2_TEST_SYSTEM_ID"]=systemId;info.Environment["R20_V2_CONTEXT"]=contextFile;
            // Host-selected read-only evidence, never a path supplied by HTTP.
            if(action=="monitor" && Environment.GetEnvironmentVariable("R20_AUTHENTIC_READ_EVIDENCE") is {Length:>0} evidence)
                info.Environment["R20_AUTHENTIC_READ_EVIDENCE"]=Path.GetFullPath(evidence);
            // Chosen exclusively from the authenticated server principal, never HTTP input.
            info.Environment["R20_V2_DB_ROLE"]=context.User.IsInRole("config-admin")?"profile-admin":"reader";
            using var process=Process.Start(info) ?? throw new InvalidOperationException("Bridge start failed");
            try {
                var stdout=process.StandardOutput.ReadToEndAsync(timeout.Token);
                var stderr=process.StandardError.ReadToEndAsync(timeout.Token);
                await process.StandardInput.WriteAsync(JsonSerializer.Serialize(new {action,body,actor=context.User.Identity!.Name}).AsMemory(),timeout.Token);
                process.StandardInput.Close();await process.WaitForExitAsync(timeout.Token);
                var text=await stdout;await stderr;
                if(text.Length>2_000_000)return Results.Problem("RESPONSE_LIMIT",statusCode:503);
                using var document=JsonDocument.Parse(text);var response=document.RootElement.Clone();
                if(response.TryGetProperty("error",out var error)) {
                    var code=error.GetString();
                    return Results.Json(new {error=code},statusCode:code is "CAS_CONFLICT" or "IDEMPOTENCY_CONFLICT"?409:process.ExitCode==3?503:422);
                }
                return Results.Json(response.GetProperty("result"));
            } finally { if(!process.HasExited)process.Kill(entireProcessTree:true); }
        } catch(OperationCanceledException) {return Results.Problem("CONFIGURATION_TIMEOUT",statusCode:503);}
        catch(Exception ex) when(ex is InvalidOperationException or JsonException or System.ComponentModel.Win32Exception or IOException) {return Results.Problem("CONFIGURATION_UNAVAILABLE",statusCode:503);}
        finally {capacity.Release();}
    }
}
