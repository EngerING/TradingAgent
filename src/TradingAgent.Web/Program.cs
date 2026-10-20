using TradingAgent.Web;

await using var app = WebHostFactory.Create();
await app.RunAsync();
