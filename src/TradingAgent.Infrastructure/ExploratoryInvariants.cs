using System.Text.Json;
namespace TradingAgent.Infrastructure;

public static class ExploratoryInvariants
{
    private static decimal Number(JsonElement e,string key)=>e.TryGetProperty(key,out var v)?decimal.Parse(v.ToString(),System.Globalization.CultureInfo.InvariantCulture):0;
    public static void Validate(JsonElement payload,string? previous)
    {
        var s=payload.GetProperty("state");
        var supervised=s.TryGetProperty("protocol",out var protocol) && protocol.TryGetProperty("protocol_version",out var version) && version.GetInt32()==2;
        if(!supervised)
        {
            if(previous is not null)
            {
                using var historical=JsonDocument.Parse(previous);
                if(historical.RootElement.GetProperty("state").TryGetProperty("protocol",out var priorProtocol) &&
                    priorProtocol.TryGetProperty("protocol_version",out var priorVersion) && priorVersion.GetInt32()==2)
                    throw new InvalidDataException("SUPERVISED_PROTOCOL_CANNOT_DOWNGRADE");
            }
            return; // Preserved historical records, never a downgrade of v2.
        }
        if(protocol.GetProperty("max_openings").GetInt32()!=1 || protocol.GetProperty("capital_per_profile").GetString()!="100" || protocol.GetProperty("exposure_cap").GetString()!="100" ||
            protocol.GetProperty("max_authorization_minutes").GetInt32()!=30 || Number(s,"opening_attempts")>1 || Number(s,"opening_attempts")<0)
            throw new InvalidDataException("SUPERVISED_SCOPE_REQUIRED");
        foreach(var p in s.GetProperty("profiles").EnumerateObject())
            if(Number(p.Value,"reserved")<0 || Number(p.Value,"reserved")>100 || Number(p.Value,"consumed_loss")<0)
                throw new InvalidDataException("EXPERIMENTAL_CAPITAL_REQUIRED");
        if(previous is null)return;
        using var old=JsonDocument.Parse(previous);var prior=old.RootElement.GetProperty("state");
        if(prior.GetProperty("protocol").GetRawText()!=protocol.GetRawText() || Number(s,"opening_attempts")<Number(prior,"opening_attempts"))
            throw new InvalidDataException("EXPERIMENT_PROTOCOL_OR_CONSUMPTION_RESET");
        foreach(var p in prior.GetProperty("profiles").EnumerateObject())
            if(Number(s.GetProperty("profiles").GetProperty(p.Name),"consumed_loss")<Number(p.Value,"consumed_loss"))
                throw new InvalidDataException("CONSUMED_LOSS_CANNOT_RESET");
        var before=prior.GetProperty("active");
        if(before.ValueKind==JsonValueKind.Null)return;
        var active=s.GetProperty("active");
        var after=active.ValueKind!=JsonValueKind.Null && active.GetProperty("intent").GetString()==before.GetProperty("intent").GetString()?active:
            s.GetProperty("trials").EnumerateArray().FirstOrDefault(t=>t.GetProperty("intent").GetString()==before.GetProperty("intent").GetString());
        if(after.ValueKind==JsonValueKind.Undefined)throw new InvalidDataException("INTENT_CANNOT_DISAPPEAR");
        foreach(var fill in before.GetProperty("fills").EnumerateObject())
            if(!after.GetProperty("fills").TryGetProperty(fill.Name,out var same) || same.GetRawText()!=fill.Value.GetRawText())
                throw new InvalidDataException("EXECUTION_CANNOT_DISAPPEAR_OR_CHANGE");
        if(active.ValueKind==JsonValueKind.Null && after.GetProperty("state").GetString() is not ("CLOSED_RECONCILED" or "CANCELLED_NO_FILL"))
            throw new InvalidDataException("RESERVATION_RECONCILIATION_REQUIRED");
    }
}
