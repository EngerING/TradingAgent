using System.Text.Json;
using System.Text.Json.Nodes;
using TradingAgent.Infrastructure;
using Xunit;
namespace TradingAgent.Tests;

public class ExploratorySupervisedTests
{
    private static JsonObject Payload()=>JsonSerializer.SerializeToNode(new{state=new{
        protocol=new{protocol_version=2,max_openings=1,capital_per_profile="100",exposure_cap="100",max_authorization_minutes=30},
        opening_attempts=1,active=new{intent="own",state="SEND_PENDING",fills=new{exec1=new{quantity="1",price="1.1"}}},
        trials=Array.Empty<object>(),profiles=new{EURUSD_R1=new{reserved="0",consumed_loss="0"},EURUSD_R5=new{reserved="10",consumed_loss="1"},EURUSD_R10=new{reserved="0",consumed_loss="0"}}}})!.AsObject();
    [Fact]public void UnchangedStateCanBeAppended()=>ExploratoryInvariants.Validate(JsonSerializer.SerializeToElement(Payload()),Payload().ToJsonString());
    [Theory][InlineData("opening_attempts")][InlineData("consumed_loss")][InlineData("fill")][InlineData("intent")][InlineData("protocol")][InlineData("reservation")][InlineData("downgrade")][InlineData("remove_protocol")]
    public void DurableSafetyCannotBeReset(string change)
    {
        var before=Payload();var after=Payload();var s=after["state"]!;
        switch(change)
        {
            case "opening_attempts":s["opening_attempts"]=0;break;
            case "consumed_loss":s["profiles"]!["EURUSD_R5"]!["consumed_loss"]="0";break;
            case "fill":s["active"]!["fills"]=new JsonObject();break;
            case "intent":s["active"]=null;break;
            case "protocol":s["protocol"]!["max_openings"]=3;break;
            case "reservation":s["profiles"]!["EURUSD_R5"]!["reserved"]="101";break;
            case "downgrade":s["protocol"]!["protocol_version"]=1;break;
            case "remove_protocol":s.AsObject().Remove("protocol");break;
        }
        Assert.Throws<InvalidDataException>(()=>ExploratoryInvariants.Validate(JsonSerializer.SerializeToElement(after),before.ToJsonString()));
    }
}
