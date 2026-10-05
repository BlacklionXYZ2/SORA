using Sora.DesktopShell;
using Sora.DesktopWidget;
using System.Security.Principal;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            var options = ShellOptions.Parse(args);
            if (options.Hosted)
            {
                using var identity = WindowsIdentity.GetCurrent();
                using var instance = new ShellInstance(ShellProfile.Key(options.StateRoot!, identity.User!.Value));
                if (!instance.Primary)
                {
                    // All surfaces, including transient menus, belong to the primary profile host.
                    // A secondary window would bypass saved appearance/text scaling and duplicate UI ownership.
                    var summon = options.Managed is not null && options.Panel == "none" ? "menu" : options.Panel;
                    if (!instance.SummonAsync(summon, default).GetAwaiter().GetResult())
                        throw new InvalidOperationException("Existing profile host did not accept this command. No second host/Core was started.");
                    return;
                }
                if (options.Panel == "quit") return;
                using var core = new ShellCoreCoordinator(options);
                var selected = core.Options;
                using var hostedApi = new WidgetApiClient(selected.CoreUrl, selected.TokenFile, "device-local");
                using var hostedSession = new ShellSession(hostedApi, selected.StateRoot,
                    instanceId => hostedApi.ExpectedCoreInstanceId = instanceId);
                using var host = new ShellHost(hostedSession, instance, selected, core);
                Application.Run(host); return;
            }
            using var api = new WidgetApiClient(options.CoreUrl, options.TokenFile, "device-local");
            using var session = new ShellSession(api);
            Application.Run(new ShellForm(session));
        }
        catch (Exception error)
        { MessageBox.Show(error.Message, "SORA · startup/recovery", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
}
