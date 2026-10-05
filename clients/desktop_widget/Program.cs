using Sora.DesktopWidget;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var options = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Use --token-file PATH, --core-url URL and optionally --settings-file PATH.");
            options[args[index]] = args[index + 1];
        }

        var tokenFile = options.GetValueOrDefault("--token-file") ??
            Path.Combine(Environment.CurrentDirectory, ".local", "sora-api-token");
        var settingsFile = options.GetValueOrDefault("--settings-file") ??
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "SORA", "widget", "settings.json");
        var coreUrl = new Uri(options.GetValueOrDefault("--core-url") ?? "http://127.0.0.1:8765");
        using var api = new WidgetApiClient(coreUrl, tokenFile, "widget-owner");
        Application.Run(new WidgetForm(new WidgetSync(api), settingsFile));
    }
}
