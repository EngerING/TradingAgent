using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Logging.Abstractions;
using TradingAgent.Api;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class PaperFeedTests
{
    private static void WithConfiguration(string account,Action check,string? gate=null,string? value=null)
    {
        var repo=Path.GetFullPath("../../../../..",AppContext.BaseDirectory);
        var settings=new Dictionary<string,string?> {
            ["IBKR_DATA_ENABLED"]="true",["IBKR_PAPER_ACCOUNT"]=account,
            ["IBKR_PAPER_ATTESTED"]="true",["IBKR_READ_ONLY_ATTESTED"]="true",
            ["IBKR_VERIFIED_TWS_PORT"]="7497",["IBKR_PORT"]="7497",["LIVE_TRADING"]="false",
            ["IBKR_CLIENT_ID"]="73",["TRADING_PYTHON"]=Path.Combine(repo,".venv","Scripts","python.exe"),
            ["TRADING_PYTHON_ROOT"]=Path.Combine(repo,"python")
        };
        if(gate is not null)settings[gate]=value;
        var prior=settings.Keys.ToDictionary(n=>n,Environment.GetEnvironmentVariable);
        try
        {
            foreach(var pair in settings)Environment.SetEnvironmentVariable(pair.Key,pair.Value);
            check();
        }
        finally {foreach(var pair in prior)Environment.SetEnvironmentVariable(pair.Key,pair.Value);}
    }

    [Theory]
    [InlineData("DU12345678")]
    [InlineData("DUR12345678")]
    public void BothAccountFormatsRequireConfiguredPaperReadOnlyGates(string account)
    {
        WithConfiguration(account,()=> {
            var config=PaperFeedConfiguration.Load();Assert.True(config.Enabled);
            var expected="PAPER-"+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(account))).ToLowerInvariant()[..16];
            Assert.Equal(expected,config.AccountId);Assert.DoesNotContain(account,config.AccountId);
        });
    }

    [Theory]
    [InlineData("")]
    [InlineData("U123")]
    [InlineData("DF123")]
    [InlineData("DU")]
    [InlineData("DUR")]
    [InlineData("DURR123")]
    [InlineData("dur123")]
    [InlineData("DU123X")]
    [InlineData("DUR123\n")]
    [InlineData(" DU123")]
    [InlineData("DU１２３")]
    public void UnknownOrMalformedConfiguredIdentitiesAreRejected(string account)
    {
        WithConfiguration(account,()=>Assert.Throws<InvalidOperationException>(()=>PaperFeedConfiguration.Load()));
    }

    [Theory]
    [InlineData("IBKR_PAPER_ATTESTED",null)]
    [InlineData("IBKR_READ_ONLY_ATTESTED",null)]
    [InlineData("LIVE_TRADING","true")]
    [InlineData("IBKR_PORT","7496")]
    [InlineData("IBKR_VERIFIED_TWS_PORT","7496")]
    public void AccountPrefixCannotBypassSafetyGates(string gate,string? value)
    {
        foreach(var account in new[]{"DU12345678","DUR12345678"})
            WithConfiguration(account,()=>Assert.Throws<InvalidOperationException>(()=>PaperFeedConfiguration.Load()),gate,value);
    }

    [DatabaseFact] public async Task RealProcessBoundaryPersistsMockObservationsAndRecoversAfterRestart()
    {
        var repo=Path.GetFullPath("../../../../..",AppContext.BaseDirectory);
        var python=Path.Combine(repo,".venv","Scripts","python.exe");
        Assert.True(File.Exists(python),"Create isolated .venv before running the process integration test");
        var fixtureAccount="DU"+DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var account="PAPER-"+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(fixtureAccount))).ToLowerInvariant()[..16];
        var prior=Environment.GetEnvironmentVariable("IBKR_PAPER_ACCOUNT");
        var envNames=new[]{"IBKR_PAPER_ATTESTED","IBKR_READ_ONLY_ATTESTED","IBKR_VERIFIED_TWS_PORT","IBKR_PORT","IBKR_CLIENT_ID"};
        var saved=envNames.ToDictionary(n=>n,Environment.GetEnvironmentVariable);
        Environment.SetEnvironmentVariable("IBKR_PAPER_ACCOUNT",fixtureAccount);
        foreach(var n in envNames)Environment.SetEnvironmentVariable(n,n.EndsWith("ATTESTED")?"true":n=="IBKR_CLIENT_ID"?"73":"7497");
        try
        {
            var store=new PostgresStore(Environment.GetEnvironmentVariable("TRADING_TEST_DB")!);await store.Migrate();
            var config=new PaperFeedConfiguration(true,account,python,Path.Combine(repo,"python","tests","fixtures"),73);
            for(var restart=0;restart<2;restart++)
            {
                using var feed=new PaperFeedService(config,store,NullLogger<PaperFeedService>.Instance);
                Assert.False(feed.Connected); // persisted CONNECTED never proves a new session
                await feed.StartAsync(CancellationToken.None);
                try
                {
                    using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(15));
                    while((await store.PaperCandles(account,240)).Count!=1 || !feed.Connected)
                        await Task.Delay(50,timeout.Token);
                    Assert.Equal(1,Assert.Single(await store.PaperCandles(account,240)).Low);
                    var snapshot=await store.LatestPaper(account,"account");Assert.NotNull(snapshot);
                    Assert.Equal("1000000",PaperData.Read<PaperAccount>(snapshot!.Data).Values.First(v=>v.Tag=="NetLiquidation").Value);
                    var quote=PaperData.Read<PaperQuote>((await store.LatestPaper(account,"quote"))!.Data);
                    Assert.Equal("FROZEN",quote.DataType);Assert.False(quote.Executable);
                    Assert.NotNull(await store.LatestPaper(account,"contract"));
                }
                finally
                {
                    using var shutdown=new CancellationTokenSource(TimeSpan.FromSeconds(25));await feed.StopAsync(shutdown.Token);
                }
                Assert.False(feed.Connected);
                Assert.Equal("DISCONNECTED",PaperData.Read<PaperConnection>((await store.LatestPaper(account,"status"))!.Data).State);
            }
            foreach(var minutes in new[]{15,60,240})Assert.Single(await store.PaperCandles(account,minutes));
        }
        finally
        {
            Environment.SetEnvironmentVariable("IBKR_PAPER_ACCOUNT",prior);
            foreach(var pair in saved)Environment.SetEnvironmentVariable(pair.Key,pair.Value);
        }
    }
}
