namespace TradingAgent.HostedPilot;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.SequenceEqual(new[] { "--redaction-self-test" }))
        {
            try { ObserverSelfTest.RunAsync().GetAwaiter().GetResult(); return 0; }
            catch (Exception) { return 1; }
        }
        if (args.Length != 0) return 2;
        ApplicationConfiguration.Initialize();
        using var form = new PilotForm();
        Application.Run(form);
        return form.ExitCode;
    }
}
