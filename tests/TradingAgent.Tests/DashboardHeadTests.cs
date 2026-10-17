using System.Text.Json;
using Npgsql;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class DashboardHeadTests
{
    [DatabaseFact]
    public async Task SnapshotUsesCommittedHeadsRatherThanAnOlderEventWithALaterClock()
    {
        var connection=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
        var config=new NpgsqlConnectionStringBuilder(connection);
        Assert.Equal("127.0.0.1",config.Host);Assert.Equal(55432,config.Port);Assert.Equal("trading_test",config.Username);
        // Isolate global-head selection from fixtures belonging to other tests.
        var database="r20_dashboard_test_"+Guid.NewGuid().ToString("N");
        await using var admin=new NpgsqlConnection(connection);await admin.OpenAsync();
        await using(var create=new NpgsqlCommand($"CREATE DATABASE {database}",admin))await create.ExecuteNonQueryAsync();
        config.Database=database;config.Pooling=false;connection=config.ConnectionString;
        try
        {
        await new PostgresStore(connection).Migrate();
        var study="eurusd-shadow-"+Guid.NewGuid().ToString("N");
        var experiment="r10-price-"+Guid.NewGuid().ToString("N");
        await using var c=new NpgsqlConnection(connection);await c.OpenAsync();
        foreach(var revision in new[]{1,2})
        {
            // Synthetic storage fixtures: older observers did not enforce a monotonic clock.
            // The committed revision remains authoritative, as in the journal reader.
            var at=revision==1?"2099-01-01T00:00:00Z":"2098-01-01T00:00:00Z";
            var shadow=JsonSerializer.Serialize(new{scope="EURUSD_SHADOW_R1_R5_R10",classification="SIMULATED_SHADOW",broker_orders=0,execution_authorized=false,at,revision});
            var risk=JsonSerializer.Serialize(new{scope="R10_PRICE_RISK_EXPERIMENTAL",classification="SIMULATED_SHADOW",broker_orders=0,live_enabled=false,at,revision,experiment});
            foreach(var (table,id,payload) in new[]{("research_shadow.events",study,shadow),("price_risk.events",experiment,risk)})
            {
                await using var cmd=new NpgsqlCommand($"INSERT INTO {table} VALUES($1,$2,$3,'',$4)",c);
                cmd.Parameters.AddWithValue(id);cmd.Parameters.AddWithValue(revision);cmd.Parameters.AddWithValue(payload);cmd.Parameters.AddWithValue(new string('a',64));
                await cmd.ExecuteNonQueryAsync();
            }
        }
        var snapshot=await new DashboardStore(connection).Snapshot(study,default);
        Assert.Equal(2,snapshot.Revision);
        Assert.Equal(2,snapshot.Head!.Value.GetProperty("revision").GetInt32());
        Assert.Equal(2,snapshot.PriceRisk!.Value.GetProperty("revision").GetInt32());
        }
        finally
        {
            await using var drop=new NpgsqlCommand($"DROP DATABASE {database}",admin);await drop.ExecuteNonQueryAsync();
        }
    }
}
