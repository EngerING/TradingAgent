using System.Text.Json;
using TradingAgent.Core;

namespace TradingAgent.Api;

public sealed record EconomicStudySettings(int SchemaVersion, string Instrument, decimal[] Quantities,
    decimal AssumedPrice, decimal StopDistance, decimal TargetDistance, decimal PublicFeeRate,
    decimal PublicMinimumFeeUsd, decimal ManualOpeningUsd, decimal ManualOpeningQuantity,
    string PublicCommissionSource, string Limitations);

public static class EconomicStudyRunner
{
    public static JsonElement Run(RiskPolicy policy, string configurationPath, DateTimeOffset now)
    {
        var options = new JsonSerializerOptions(Evidence.Json) {UnmappedMemberHandling=System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow};
        options.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
        var settings = JsonSerializer.Deserialize<EconomicStudySettings>(File.ReadAllText(configurationPath),options)
            ?? throw new InvalidDataException("ECONOMIC_SETTINGS_REQUIRED");
        if (settings.SchemaVersion != 1 || settings.Instrument != "EUR/USD" || settings.Quantities is null ||
            settings.Quantities.Length is < 1 or > 100 || settings.Quantities.Any(q=>q<=0) ||
            settings.Quantities.Distinct().Count()!=settings.Quantities.Length || settings.AssumedPrice<=settings.StopDistance ||
            settings.StopDistance<=0 || settings.TargetDistance<=0 || settings.PublicFeeRate<0 || settings.PublicMinimumFeeUsd<0 ||
            settings.ManualOpeningUsd<0 || settings.ManualOpeningQuantity<=0 || string.IsNullOrWhiteSpace(settings.Limitations) ||
            !Uri.TryCreate(settings.PublicCommissionSource,UriKind.Absolute,out var source) || source.Scheme!="https" ||
            source.Host!="www.interactivebrokers.com") throw new ArgumentException("INVALID_ECONOMIC_SETTINGS");
        var account = AccountState.Initial("SIM-ECONOMIC-E0",policy.AllocatedCapital,now,policy.CumulativeLossLimit);
        EconomicEvidence Fact(decimal? value, EconomicEvidenceStatus status, string source, decimal? scope=null) =>
            new(value,status,source,now,now.AddSeconds(policy.MaxDataAgeSeconds),scope);
        var unknown = Fact(null,EconomicEvidenceStatus.Unknown,"NOT_VERIFIED_FOR_ACCOUNT");
        var scenario = EconomicEvidenceStatus.Scenario;
        EconomicCommission Fee(decimal? amount, EconomicEvidenceStatus status, string evidence, decimal? scope=null) =>
            new(Fact(amount,status,evidence,scope),amount is null?null:"USD",Fact(1,scenario,"USD_IDENTITY_CONVERSION"));
        EconomicComparisonInput Input(decimal q, bool publicScenario) => new(settings.Instrument,q,1,
            Fact(settings.AssumedPrice,scenario,"ASSUMED_PRICE_NOT_A_QUOTE"),Fact(1,scenario,"USD_QUOTE_CONVERSION"),
            settings.StopDistance,settings.TargetDistance,
            publicScenario ? Fee(Math.Max(settings.PublicMinimumFeeUsd,q*settings.AssumedPrice*settings.PublicFeeRate),
                EconomicEvidenceStatus.PublicSchedule,settings.PublicCommissionSource) :
                Fee(settings.ManualOpeningUsd,EconomicEvidenceStatus.ManualEstimate,"OWNER_MANUAL_ESTIMATE",settings.ManualOpeningQuantity),
            publicScenario ? Fee(Math.Max(settings.PublicMinimumFeeUsd,q*(settings.AssumedPrice+settings.TargetDistance)*settings.PublicFeeRate),
                EconomicEvidenceStatus.PublicSchedule,settings.PublicCommissionSource) : Fee(null,EconomicEvidenceStatus.Unknown,"CLOSING_PREVIEW_PENDING"),
            publicScenario?Fact(0,scenario,"FAVORABLE_LOWER_BOUND_NOT_OBSERVED_SPREAD"):unknown,
            publicScenario?Fact(0,scenario,"FAVORABLE_LOWER_BOUND_NOT_OBSERVED_SLIPPAGE"):unknown,
            publicScenario?Fact(0,scenario,"FAVORABLE_LOWER_BOUND_NOT_OBSERVED_GAP"):unknown,
            publicScenario?Fact(1,scenario,"FULLY_FUNDED_SENSITIVITY_NOT_BROKER_MARGIN"):unknown,
            publicScenario?Fact(1,scenario,"ASSUMED_MINIMUM_NOT_ACCOUNT_PERMISSION"):unknown,
            publicScenario?Fact(1,scenario,"ASSUMED_STEP_NOT_ACCOUNT_RULE"):unknown,unknown);
        var inputs = settings.Quantities.Select(q=>new {quantity=q,accountEvidence=Input(q,false),publicFeeLowerBound=Input(q,true)}).ToArray();
        return JsonSerializer.SerializeToElement(new {schemaVersion=1,delivery="E.0",asOf=now,settings,policy,
            accountEvidenceComparisons=inputs.Select(i=>new {input=i.accountEvidence,result=EconomicComparison.Analyze(policy,account,i.accountEvidence,now)}),
            publicFeeLowerBoundComparisons=inputs.Select(i=>new {input=i.publicFeeLowerBound,result=EconomicComparison.Analyze(policy,account,i.publicFeeLowerBound,now)}),
            accountVerifiedAlternatives=Array.Empty<object>(),alternativeStatus="ACCOUNT_PERMISSIONS_AND_REQUIREMENTS_UNVERIFIED",
            paperPreparation=new {status="DESIGNED_DISABLED",separateManualAuthorizationRequired=true},
            connectedToTws=false,ordersSupported=false,liveEnabled=false,openaiEnabled=false},options);
    }
}
