namespace TradingAgent.HostedPilot;

internal sealed class PilotForm : Form
{
    private readonly TextBox email = new() { Width = 520, MaxLength = 320 };
    private readonly TextBox password = new() { Width = 520, UseSystemPasswordChar = true, MaxLength = 1024 };
    private readonly Button begin = new() { Text = "Validar Auth / JWT / MFA / PostgreSQL", AutoSize = true };
    private readonly Label status = new() { Width = 540, Height = 120, Text = "Solo cuenta ficticia. Contraseña/TOTP permanecen en memoria. Se medirán logout local/otros/global de ESTA cuenta de desarrollo. HTTPS BFF pendiente de certificado compatible. OFFLINE / NO_TRADE." };
    private readonly CancellationTokenSource cancellation = new(TimeSpan.FromMinutes(20));
    private bool running;
    internal int ExitCode { get; private set; } = 1;
    internal PilotForm()
    {
        File.WriteAllText("tmp/m013b/hosted-interactive-state.json", "{\"state\":\"WAITING_LOCAL_USER_INPUT\",\"scope\":\"DIRECT_AUTH_JWT_MFA_SQL_ONLY_ON_WINDOWS\",\"secrets_included\":false}");
        File.WriteAllText("tmp/m013b/hosted-interactive-result.json", "{\"status\":\"NOT_STARTED\",\"mode\":\"OFFLINE\",\"decision\":\"NO_TRADE\",\"executionAuthorized\":false,\"secrets_logged\":false}");
        Text = "TradingAgent — Piloto Auth Dev (solo identidad)"; Width = 610; Height = 430;
        StartPosition = FormStartPosition.CenterScreen; MaximizeBox = false;
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20), FlowDirection = FlowDirection.TopDown, WrapContents = false };
        layout.Controls.Add(new Label { Text = "Email de la cuenta ficticia de desarrollo", AutoSize = true }); layout.Controls.Add(email);
        layout.Controls.Add(new Label { Text = "Contraseña — entrada local; nunca al chat", AutoSize = true }); layout.Controls.Add(password);
        layout.Controls.Add(begin); layout.Controls.Add(status); Controls.Add(layout);
        begin.Click += async (_, _) =>
        {
            if (running || string.IsNullOrWhiteSpace(email.Text) || password.Text.Length == 0) return;
            running = true; begin.Enabled = false; email.Enabled = false; password.Enabled = false;
            File.WriteAllText("tmp/m013b/hosted-interactive-state.json", "{\"state\":\"USER_STARTED_DIRECT_AUTH_CHECKS\",\"secrets_included\":false}");
            var identifier = email.Text; var secret = password.Text; email.Clear(); password.Clear();
            try { await HostedRun.ExecuteAsync(identifier, secret, this, cancellation.Token); ExitCode = 0; status.Text = "Mediciones terminadas con casos pendientes. No constituye aprobación B2. Evidencia redactada guardada."; }
            catch (OperationCanceledException) { HostedRun.Failure("CANCELLED"); status.Text = "Piloto cancelado o vencido. Sin reintento automático."; }
            catch (TradingAgent.Identity.Supabase.AuthException error) { HostedRun.Failure("AUTH_" + error.Failure); status.Text = "El proveedor o su contrato rechazó el flujo: " + error.Failure + ". Detenido, sin debilitar validaciones."; }
            catch (PilotFailure error) { HostedRun.Failure(error.Code); status.Text = "Piloto detenido: " + error.Code + ". Revisa la evidencia redactada."; }
            catch (Exception) { HostedRun.Failure("DEPENDENCY_OR_CONFIGURATION_FAILURE"); status.Text = "Fallo de dependencia/configuración. Detenido; detalles sensibles no registrados."; }
            finally
            {
                identifier = ""; secret = ""; running = false;
                var closeTimer = new System.Windows.Forms.Timer { Interval = 12000 };
                closeTimer.Tick += (_, _) => { closeTimer.Stop(); closeTimer.Dispose(); Close(); }; closeTimer.Start();
            }
        };
        FormClosing += (_, args) => { if (running) { cancellation.Cancel(); args.Cancel = true; status.Text = "Cancelando y cerrando recursos temporales…"; } };
        var idleExpiry = new System.Windows.Forms.Timer { Interval = 500 };
        idleExpiry.Tick += (_, _) => { if (cancellation.IsCancellationRequested && !running && ExitCode != 0) { HostedRun.Failure("CANCELLED_OR_DEADLINE"); Close(); } }; idleExpiry.Start();
        FormClosed += (_, _) => { idleExpiry.Stop(); idleExpiry.Dispose(); cancellation.Dispose(); };
    }
    internal string Otp(string instruction, string? enrollmentSecret = null)
    {
        using var dialog = new Form { Text = "TradingAgent — intervención local TOTP", Width = 620, Height = 370, StartPosition = FormStartPosition.CenterParent, MaximizeBox = false, MinimizeBox = false };
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20), FlowDirection = FlowDirection.TopDown, WrapContents = false };
        layout.Controls.Add(new Label { Text = instruction + "\nNo envíes este código o secreto al chat. La ventana no se captura.", Width = 555, Height = 90 });
        if (enrollmentSecret is not null) layout.Controls.Add(new TextBox { Text = enrollmentSecret, ReadOnly = true, Width = 550, ShortcutsEnabled = false });
        using var input = new TextBox { Width = 200, MaxLength = 6, UseSystemPasswordChar = true, ShortcutsEnabled = false };
        layout.Controls.Add(input);
        var button = new Button { Text = "Enviar código localmente", AutoSize = true, DialogResult = DialogResult.OK }; layout.Controls.Add(button);
        dialog.Controls.Add(layout); dialog.AcceptButton = button;
        using var expiry = new System.Windows.Forms.Timer { Interval = 500 };
        expiry.Tick += (_, _) => { if (cancellation.IsCancellationRequested) dialog.Close(); }; expiry.Start();
        if (dialog.ShowDialog(this) != DialogResult.OK || input.Text.Length != 6 || input.Text.Any(c => c is < '0' or > '9')) throw new OperationCanceledException();
        var code = input.Text; input.Clear(); return code;
    }
    internal void Progress(string message) { status.Text = message; }
}

internal sealed class PilotFailure(string code) : Exception("HOSTED_PILOT_CHECK_FAILED")
{
    internal string Code { get; } = code;
}
