using System.Net;
using System.Security.Cryptography;
using System.Text;

namespace TradingAgent.Web.Auth;

public enum PilotOperation { Login, Mfa, Logout, Session }
internal sealed record PilotOperationMetadata(PilotOperation Operation);

/// <summary>Single-process fixed windows. Direct socket addresses only; no forwarded header trust.</summary>
public sealed class PilotRequestBudgets(TimeProvider clock)
{
    private sealed record Window(int Count, DateTimeOffset End);
    private sealed class Bucket
    {
        internal readonly Dictionary<string, Window> Sources = new(StringComparer.Ordinal);
        internal readonly Dictionary<string, Window> Accounts = new(StringComparer.Ordinal);
        internal Window? Global;
    }
    private readonly object gate = new();
    private readonly byte[] identityKey = RandomNumberGenerator.GetBytes(32);
    private readonly Bucket[] buckets = [new(), new(), new(), new()];
    public bool TryAdmit(PilotOperation operation, IPAddress? directAddress, string? loginIdentity = null)
    {
        if (!Enum.IsDefined(operation)) throw new ArgumentOutOfRangeException(nameof(operation));
        if (operation == PilotOperation.Login && (string.IsNullOrWhiteSpace(loginIdentity) || loginIdentity.Length > 320)) return false;
        var source = directAddress is null ? "unknown" : (directAddress.IsIPv4MappedToIPv6 ? directAddress.MapToIPv4() : directAddress).ToString();
        lock (gate)
        {
            var b = buckets[(int)operation]; var now = clock.GetUtcNow();
            Prune(b.Sources, now); Prune(b.Accounts, now);
            b.Sources.TryGetValue(source, out var origin);
            var sourceLimit = operation == PilotOperation.Mfa ? 40 : 20;
            // Do not allocate an account or debit another budget for rejected source traffic.
            if (origin?.Count >= sourceLimit || origin is null && b.Sources.Count >= 1024) return false;
            string? accountKey = null; Window? account = null;
            if (operation == PilotOperation.Login)
            {
                accountKey = Convert.ToHexString(HMACSHA256.HashData(identityKey, Encoding.UTF8.GetBytes(loginIdentity!.Trim().ToUpperInvariant())));
                b.Accounts.TryGetValue(accountKey, out account);
                if (account?.Count >= 20 || account is null && b.Accounts.Count >= 1024) return false;
            }
            var global = b.Global is { } g && g.End > now ? g : null;
            if (global?.Count >= sourceLimit * 10) return false;
            var end = now.AddMinutes(1);
            b.Sources[source] = new((origin?.Count ?? 0) + 1, origin?.End ?? end);
            if (accountKey is not null) b.Accounts[accountKey] = new((account?.Count ?? 0) + 1, account?.End ?? end);
            b.Global = new((global?.Count ?? 0) + 1, global?.End ?? end);
            return true;
        }
    }
    private static void Prune(Dictionary<string, Window> windows, DateTimeOffset now)
    {
        foreach (var key in windows.Where(p => p.Value.End <= now).Select(p => p.Key).ToArray()) windows.Remove(key);
    }
}
