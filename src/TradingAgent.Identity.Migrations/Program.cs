using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;

if (args.Length != 1 || args[0] != "--disposable-only")
{
    Console.Error.WriteLine("Explicit --disposable-only required. No operational migration mode exists."); return 2;
}
try
{
    var target = new DisposableTarget("127.0.0.1", int.Parse(Environment.GetEnvironmentVariable("M012_TEST_PORT")!, System.Globalization.CultureInfo.InvariantCulture), Environment.GetEnvironmentVariable("M012_TEST_DATABASE")!);
    var database = new SecurityDatabase(target, Environment.GetEnvironmentVariable("M012_MIGRATION_USER")!, Environment.GetEnvironmentVariable("M012_MIGRATION_PASSWORD")!, DatabasePurpose.Migration);
    await MigrationRunner.ApplyAsync(database, CancellationToken.None); Console.WriteLine("DISPOSABLE_MIGRATIONS_VERIFIED"); return 0;
}
catch (Exception error) when (error is ArgumentException or InvalidOperationException or Npgsql.NpgsqlException or FormatException)
{
    Console.Error.WriteLine("M012_MIGRATION_REJECTED"); return 1;
}
