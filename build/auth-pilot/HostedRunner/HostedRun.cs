using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Web.Auth;

namespace TradingAgent.HostedPilot;

internal static class HostedRun
{
    private static readonly Dictionary<string, object> evidence = new(StringComparer.Ordinal);
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private static string ResultPath { get; set; } = "tmp/m013b/hosted-interactive-result.json";
    internal static void UseDiagnosticSelfTestOutput() => ResultPath = "tmp/m013b/hosted-observer-self-test.json";
    internal static void Failure(string code) { evidence["status"] = code; Save(); }
    private static void Save() => File.WriteAllText(ResultPath, JsonSerializer.Serialize(evidence, JsonOptions));
    private static void Pass(string check) { evidence[check] = "PASS"; evidence["status"] = "RUNNING"; Save(); }
    private static void Require(bool allowed, string code) { if (!allowed) throw new PilotFailure(code); }
    internal static void Observe(string name, object value) { evidence[name] = value; Save(); }
    internal static async Task ExecuteAsync(string email, string password, PilotForm ui, CancellationToken token)
    {
        evidence.Clear(); evidence["mode"] = "OFFLINE"; evidence["decision"] = "NO_TRADE";
        evidence["executionAuthorized"] = false; evidence["scope"] = "REAL_DEVELOPMENT_AUTH_AND_DISPOSABLE_SQL";
        evidence["secrets_logged"] = false; evidence["status"] = "PREFLIGHT"; Save();
        using var source = JsonDocument.Parse(await File.ReadAllBytesAsync("tmp/m013b/hosted-development.public.json", token));
        var p = source.RootElement;
        var settings = HostedPilotSettings.FromExternalValues(p.GetProperty("environment").GetString()!, p.GetProperty("confirmedReference").GetString()!, new Uri(p.GetProperty("project").GetString()!), p.GetProperty("publishableKey").GetString()!, new Uri(p.GetProperty("browserOrigin").GetString()!));
        var services = new ServiceCollection(); services.AddSupabaseAuth(settings.Authentication).AddHttpMessageHandler(() => new RedactedAuthObserver(settings.Authentication.Issuer));
        await using var provider = services.BuildServiceProvider(); var auth = provider.GetRequiredService<SupabaseAuthClient>();
        var verifier = provider.GetRequiredService<JwtVerifier>(); var transport = provider.GetRequiredService<AuthTransport>();
        using (var document = await transport.SendAsync(HttpMethod.Get, "/auth/v1/settings", null, null, token))
        {
            Require(document.RootElement.GetProperty("disable_signup").GetBoolean(), "SIGNUP_NOT_DISABLED");
            var external = document.RootElement.GetProperty("external");
            Require(external.GetProperty("email").GetBoolean() && !external.EnumerateObject().Any(k => k.Name != "email" && k.Value.ValueKind == JsonValueKind.True), "PROVIDER_PROFILE_INCOMPATIBLE");
        }
        Pass("hosted_settings"); ui.Progress("Validando password y JWT con Supabase de desarrollo…");
        AccessCredential? first = null;
        Guid? createdFactor = null;
        try
        {
            first = await auth.PasswordAsync(email, password, token); Require(first.Identity.Aal == 1, "PASSWORD_NOT_AAL1");
            var factors = await auth.CheckUserAsync(first, token); Pass("password_user_and_signed_aal1_jwt");
            await using var database = new HostedDatabase(); await database.InitializeAsync(token); await database.SeedAsync(first.Identity.Identity, token);
            var issuer = new SessionIssuer(database.Database(DatabasePurpose.SessionIssuer), verifier);
            var denied = await issuer.CreateAsync(first.Token.AsMemory(), token); Require(denied.Reference is null && denied.Outcome == StoreOutcome.Denied, "AAL1_SQL_NOT_DENIED"); Pass("aal1_cannot_create_sql_session");
            Guid factor; string? enrollmentSecret = null;
            var verified = factors.Where(f => f.Verified).ToArray(); Require(verified.Length <= 1, "MULTIPLE_FACTORS_REQUIRE_MANUAL_SELECTION");
            if (verified.Length == 1) { factor = verified[0].Id; evidence["enrollment"] = "EXISTING_VERIFIED_FACTOR; no new enrollment performed"; }
            else
            {
                Require(factors.Count == 0, "UNVERIFIED_FACTOR_REQUIRES_EXPLICIT_RECOVERY");
                var enrollment = await auth.EnrollAsync(first, token); factor = enrollment.FactorId; createdFactor = factor; enrollmentSecret = enrollment.Secret; Pass("real_totp_enrollment");
            }
            var challengeAt = DateTimeOffset.UtcNow; var challenge = await auth.ChallengeAsync(first, factor, token);
            var code = ui.Otp(enrollmentSecret is null ? "Introduce un código actual del autenticador de esta cuenta ficticia." : "Añade manualmente este secreto al autenticador (TOTP), guarda la entrada y escribe su código actual. El secreto solo aparece aquí.", enrollmentSecret);
            enrollmentSecret = null;
            first = await auth.VerifyAsync(first, factor, challenge.Id, code, token); code = "";
            createdFactor = null; // Provider verification succeeded: never delete this verified factor.
            Require(first.Identity.Aal == 2 && first.Identity.MfaAt >= challengeAt.AddSeconds(-1) && first.Identity.MfaAt <= DateTimeOffset.UtcNow, "MFA_SIGNED_FRESHNESS_INCOMPATIBLE");
            Pass("real_mfa_aal2_signed_and_fresh");
            var creation = await issuer.CreateAsync(first.Token.AsMemory(), token); Require(creation.Outcome == StoreOutcome.Success && creation.Reference is not null, "AAL2_SQL_SESSION_FAILED");
            var sessions = new SessionRepository(database.Database(DatabasePurpose.Runtime)); var reference = creation.Reference!;
            Require(await sessions.FindSelfAsync(reference, token) is not null, "SQL_SELF_FAILED");
            Require((await sessions.AuthorizeAsync(reference, ResourceKind.Study, database.Resource, EnvironmentScope.Paper, Capability.Read, token)).Allowed, "SQL_EXACT_GRANT_FAILED");
            Require(!(await sessions.AuthorizeAsync(reference, ResourceKind.Study, database.Resource, EnvironmentScope.Live, Capability.Read, token)).Allowed, "SQL_LIVE_SCOPE_BYPASS");
            Require((await sessions.RevokeAsync(reference, token)).Outcome == StoreOutcome.Success && await sessions.FindSelfAsync(reference, token) is null, "LOCAL_SQL_REVOCATION_FAILED"); Pass("real_identity_sql_roles_grants_local_revocation");
            // Provider auth only; fixed documented scopes, never an admin/Data API call.
            AccessCredential? other = null;
            try
            {
                other = await auth.PasswordAsync(email, password, token);
                using (var loggedOut = await transport.SendAsync(HttpMethod.Post, "/auth/v1/logout?scope=others", null, first.Token, token)) { }
                var otherStatus = await UserStatusAsync(auth, other, token); evidence["get_user_other_session_after_scope_others"] = otherStatus;
                var callerStatus = await UserStatusAsync(auth, first, token); evidence["get_user_calling_session_after_scope_others"] = callerStatus;
                using (var loggedOut = await transport.SendAsync(HttpMethod.Post, "/auth/v1/logout?scope=global", null, first.Token, token)) { }
                var globalStatus = await UserStatusAsync(auth, first, token); evidence["get_user_after_global_logout"] = globalStatus;
                evidence["signed_jwt_after_global_logout"] = (await verifier.ValidateAsync(first.Token, token)).Aal == 2 ? "STILL_CRYPTOGRAPHICALLY_VALID_UNTIL_EXPIRY" : "UNEXPECTED";
                evidence["remote_logout_scopes_measurement"] = new[] { otherStatus, callerStatus, globalStatus }.Any(s => s.StartsWith("INCONCLUSIVE", StringComparison.Ordinal)) ? "INCONCLUSIVE_DEPENDENCY_OR_RATE_LIMIT; requires another measurement" : "OBSERVED_ONLY; not universal session-liveness assurance";
                token.ThrowIfCancellationRequested(); Save();
            }
            finally { if (other is not null) await SafeLogoutAsync(auth, other); }
            await SafeLogoutAsync(auth, first); first = null;
            // HTTPS BFF remains pending an externally provisioned compatible certificate.
            Require(await database.SentinelAsync(token), "FINANCIAL_SENTINEL_CHANGED");
            token.ThrowIfCancellationRequested(); Pass("disposable_financial_sentinel_unchanged");
            evidence["status"] = "DIRECT_HOSTED_AUTH_SQL_EXECUTED; HTTPS_BFF_PENDING_COMPATIBLE_CERTIFICATE";
            evidence["pending"] = new[] { "Compatible externally provisioned loopback HTTPS certificate", "Real HTTPS BFF cookie/session integration", "Hosted cross-user MFA", "Password change and elapsed JWT expiry", "Hosted signing-key rotation", "Outage injection and OS restart" };
            evidence["providerSessionConfirmedActive"] = false; Save();
        }
        finally
        {
            if (first is not null)
            {
                if (createdFactor is { } factor)
                {
                    using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                    try { await auth.RemoveUnverifiedFactorAsync(first, factor, cleanup.Token); evidence["unverified_factor_cleanup"] = "REMOVED_OWN_UNVERIFIED_FACTOR"; }
                    catch (Exception) { evidence["unverified_factor_cleanup"] = "UNCONFIRMED_OR_ALREADY_VERIFIED; no verified factor removed"; }
                }
                await SafeLogoutAsync(auth, first);
            }
            Save();
        }
    }
    private static async Task<string> UserStatusAsync(SupabaseAuthClient auth, AccessCredential credential, CancellationToken token)
    {
        try { await auth.CheckUserAsync(credential, token); return "ACCEPTED; NOT PROOF OF SESSION LIVENESS"; }
        catch (AuthException error) { return error.Failure == AuthFailure.Invalid ? "REJECTED_INVALID_IDENTITY_OR_SESSION" : "INCONCLUSIVE_" + error.Failure; }
    }
    private static async Task SafeLogoutAsync(SupabaseAuthClient auth, AccessCredential credential)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        try { await auth.LogoutAsync(credential, timeout.Token); } catch (Exception) { evidence["remote_cleanup"] = "UNCONFIRMED; access token still expires normally"; Save(); }
    }
}
