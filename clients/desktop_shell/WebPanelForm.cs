using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Sora.DesktopShell;

// Translucency routes for the W0 spike. The owner judges which looks right on their machine:
//   system  Windows 11 system backdrop (DWM acrylic, "transient window" material). Default.
//   accent  Composition accent blur (SetWindowCompositionAttribute). Older route, also Win10.
//   none    Solid glass; what the page uses when Windows has transparency turned off.
public enum PanelBackdrop { System, Accent, None }

// One web panel window (W0: Chat). Content is clients/panels/<panel>/ served from a virtual
// host; Core calls go through PanelApiProxy so the owner token never reaches page code.
internal sealed class WebPanelForm : Form
{
    private static Task<CoreWebView2Environment>? environment;
    private readonly WebView2 view = new() { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.Transparent };
    private readonly string panel;
    private readonly string panelsFolder;
    private readonly PanelApiProxy proxy;
    private readonly string userDataFolder;
    private readonly Action<string> openPanel;
    private PanelBackdrop applied = PanelBackdrop.None;
    private bool hostShutdown;

    public WebPanelForm(string panel, string panelsFolder, PanelApiProxy proxy, string stateRoot,
        Action<string> openPanel)
    {
        this.panel = panel; this.panelsFolder = panelsFolder; this.proxy = proxy; this.openPanel = openPanel;
        userDataFolder = Path.Combine(stateRoot, "webview2");
        Text = "SORA · " + char.ToUpperInvariant(panel[0]) + panel[1..];
        AccessibleName = Text;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(480, 520);
        MinimumSize = new Size(360, 320);
        BackColor = Color.Black; // Black is "show the backdrop" once DWM owns the client area.
        ShowInTaskbar = true;
        Controls.Add(view);
        FormClosing += (_, e) => {
            if (!hostShutdown && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); }
        };
    }

    public static PanelBackdrop RequestedBackdrop() =>
        (Environment.GetEnvironmentVariable("SORA_PANEL_BACKDROP") ?? "").Trim().ToLowerInvariant() switch
        {
            "accent" => PanelBackdrop.Accent,
            "none" => PanelBackdrop.None,
            _ => PanelBackdrop.System,
        };

    protected override async void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        applied = WindowGlass.Apply(Handle, RequestedBackdrop());
        try { await InitializeAsync(); }
        catch (Exception error) when (error is WebView2RuntimeNotFoundException or COMException
            or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            Controls.Remove(view);
            Controls.Add(new Label {
                Dock = DockStyle.Fill, ForeColor = Color.White, BackColor = Color.FromArgb(16, 24, 40),
                Padding = new Padding(16), Font = new Font("Segoe UI", 10f),
                Text = "The web panel could not start, so this window cannot show SORA's new Chat.\r\n\r\n"
                    + error.Message + "\r\n\r\nClose this window and start SORA without -WebPanels to use the "
                    + "existing Chat. The WebView2 runtime ships with Windows 11.",
            });
        }
    }

    private async Task InitializeAsync()
    {
        environment ??= CoreWebView2Environment.CreateAsync(null, userDataFolder);
        await view.EnsureCoreWebView2Async(await environment);
        var core = view.CoreWebView2;
        var settings = core.Settings;
        var devTools = Environment.GetEnvironmentVariable("SORA_PANELS_DEVTOOLS") == "1";
        settings.AreDevToolsEnabled = devTools;
        settings.AreDefaultContextMenusEnabled = devTools;
        settings.IsStatusBarEnabled = false;
        settings.AreBrowserAcceleratorKeysEnabled = devTools; // No Ctrl+R reload or Ctrl+P print.
        settings.IsZoomControlEnabled = false;
        settings.IsGeneralAutofillEnabled = false;
        settings.IsPasswordAutosaveEnabled = false;
        core.SetVirtualHostNameToFolderMapping(PanelApiProxy.Host, panelsFolder,
            CoreWebView2HostResourceAccessKind.Deny);
        core.AddWebResourceRequestedFilter($"https://{PanelApiProxy.Host}/api/*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += OnApiRequest;
        core.WebMessageReceived += OnMessage;
        core.NavigationStarting += (_, args) => {
            // Panels never leave their own origin.
            if (!args.Uri.StartsWith($"https://{PanelApiProxy.Host}/", StringComparison.OrdinalIgnoreCase)) args.Cancel = true;
        };
        core.NewWindowRequested += (_, args) => args.Handled = true;
        core.Navigate($"https://{PanelApiProxy.Host}/{panel}/index.html");
    }

    private async void OnApiRequest(object? sender, CoreWebView2WebResourceRequestedEventArgs args)
    {
        using var deferral = args.GetDeferral();
        try
        {
            string? body = null;
            if (args.Request.Content is { } content)
            {
                using var reader = new StreamReader(content, Encoding.UTF8);
                body = await reader.ReadToEndAsync();
            }
            var result = await proxy.ForwardAsync(args.Request.Method, args.Request.Uri, body, CancellationToken.None);
            var stream = new MemoryStream(Encoding.UTF8.GetBytes(result.Body));
            args.Response = view.CoreWebView2.Environment.CreateWebResourceResponse(stream, result.Status,
                PanelApiProxy.ReasonPhrase(result.Status), "Content-Type: application/json\r\nCache-Control: no-store");
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or COMException)
        {
            var failure = PanelApiResponse.Error(503, "SORA's Core is not reachable.", "CORE_UNAVAILABLE");
            args.Response = view.CoreWebView2.Environment.CreateWebResourceResponse(
                new MemoryStream(Encoding.UTF8.GetBytes(failure.Body)), 503, "Service Unavailable",
                "Content-Type: application/json");
        }
    }

    private void OnMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        var command = PanelBridge.Parse(args.WebMessageAsJson);
        switch (command?.Kind)
        {
            case PanelCommandKind.Close: Hide(); break;
            case PanelCommandKind.Hide: Hide(); break;
            case PanelCommandKind.Minimize: WindowState = FormWindowState.Minimized; break;
            case PanelCommandKind.Maximize:
                WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized;
                break;
            case PanelCommandKind.Drag: WindowGlass.BeginNativeMove(Handle, 2); break;
            case PanelCommandKind.Resize: WindowGlass.BeginNativeMove(Handle, PanelBridge.HitTest(command.Edge!)); break;
            case PanelCommandKind.OpenPanel: openPanel(command.Panel!); break;
            case PanelCommandKind.Ready:
                var radius = applied == PanelBackdrop.System ? 8 : 22;
                view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new {
                    type = "host.backdrop", kind = applied.ToString().ToLowerInvariant(), cornerRadius = radius,
                }));
                break;
        }
    }

    public void CloseForHostShutdown() { hostShutdown = true; Close(); }

    protected override void Dispose(bool disposing)
    {
        if (disposing) view.Dispose();
        base.Dispose(disposing);
    }
}

internal static class WindowGlass
{
    private const int DwmwaUseImmersiveDarkMode = 20, DwmwaWindowCornerPreference = 33, DwmwaSystemBackdropType = 38;
    private const int DwmwcpRound = 2, DwmsbtTransientWindow = 3;
    private const int WmNcLButtonDown = 0x00A1;

    [StructLayout(LayoutKind.Sequential)] private struct Margins { public int Left, Right, Top, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct AccentPolicy { public int State, Flags, GradientColor, AnimationId; }
    [StructLayout(LayoutKind.Sequential)] private struct CompositionData { public int Attribute; public IntPtr Data; public int Size; }

    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("dwmapi.dll")] private static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref Margins margins);
    [DllImport("user32.dll")] private static extern int SetWindowCompositionAttribute(IntPtr hwnd, ref CompositionData data);
    [DllImport("user32.dll")] private static extern bool ReleaseCapture();
    [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr hwnd, int message, IntPtr wParam, IntPtr lParam);

    /// <summary>Applies the requested route and returns what actually took effect.</summary>
    public static PanelBackdrop Apply(IntPtr hwnd, PanelBackdrop requested)
    {
        if (!OperatingSystem.IsWindows()) return PanelBackdrop.None;
        var on = 1; DwmSetWindowAttribute(hwnd, DwmwaUseImmersiveDarkMode, ref on, sizeof(int));
        var corners = DwmwcpRound; DwmSetWindowAttribute(hwnd, DwmwaWindowCornerPreference, ref corners, sizeof(int));
        if (requested == PanelBackdrop.None || !TransparencyEnabled()) return PanelBackdrop.None;
        if (requested == PanelBackdrop.System && OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22621))
        {
            var margins = new Margins { Left = -1, Right = -1, Top = -1, Bottom = -1 };
            DwmExtendFrameIntoClientArea(hwnd, ref margins);
            var material = DwmsbtTransientWindow;
            if (DwmSetWindowAttribute(hwnd, DwmwaSystemBackdropType, ref material, sizeof(int)) == 0) return PanelBackdrop.System;
        }
        // Accent blur (ACCENT_ENABLE_ACRYLICBLURBEHIND) with a light navy tint (ABGR).
        var policy = new AccentPolicy { State = 4, Flags = 2, GradientColor = unchecked((int)0x30281408) };
        var size = Marshal.SizeOf<AccentPolicy>();
        var pointer = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(policy, pointer, false);
            var data = new CompositionData { Attribute = 19, Data = pointer, Size = size };
            return SetWindowCompositionAttribute(hwnd, ref data) != 0 ? PanelBackdrop.Accent : PanelBackdrop.None;
        }
        finally { Marshal.FreeHGlobal(pointer); }
    }

    /// <summary>Windows Settings → Personalisation → Colours → Transparency effects.</summary>
    public static bool TransparencyEnabled()
    {
        if (!OperatingSystem.IsWindows()) return false;
        using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        return key?.GetValue("EnableTransparency") is not int value || value != 0;
    }

    /// <summary>Hands a press to Windows as a caption (2) or edge press, so snapping still works.</summary>
    public static void BeginNativeMove(IntPtr hwnd, int hitTest)
    {
        ReleaseCapture();
        SendMessage(hwnd, WmNcLButtonDown, hitTest, IntPtr.Zero);
    }
}
