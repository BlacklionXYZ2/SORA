using Sora.DesktopApp;

namespace Sora.DesktopShell;

internal sealed class SettingsForm : Form
{
    private readonly ShellSession session;
    private readonly ModelSettingsEditor editor;
    private readonly Label connection = new() { Dock = DockStyle.Fill, AutoSize = true };
    private bool hostShutdown;
    public bool HasPendingWork => editor.HasPendingWork;
    public bool HasUnsavedChanges => editor.HasUnsavedChanges;
    public bool ShutdownPending { get; private set; }
    public void SetShutdownPending(bool value) { ShutdownPending = value; Enabled = !value; }

    public SettingsForm(ShellSession session, Func<Task> reconnect, Action<string> openPanel)
    {
        this.session = session;
        Text = "SORA · Settings"; AccessibleName = "SORA Settings";
        AutoScaleMode = AutoScaleMode.Dpi; ClientSize = new Size(1020, 720);
        editor = new ModelSettingsEditor(session.SettingsApi,
            () => session.SettingsCurrent && !session.MutationBusy, () => session.CoreInstanceId);
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Padding = new Padding(12) };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.Controls.Add(connection, 0, 0);
        var links = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        foreach (var (label, panel) in new[] { ("Appearance / UI", "appearance"), ("Voice / devices", "voice"),
            ("Memory / browse", "memory"), ("Agents / catalogue", "agents"), ("Project paths", "paths"), ("Integrations", "integrations") }) {
            var button = ShellTheme.Button(label, "Open " + label);
            button.Click += (_, _) => openPanel(panel); links.Controls.Add(button);
        }
        var retry = ShellTheme.Button("Reconnect / retry", "Reconnect the matching Core without saving this draft");
        retry.Click += async (_, _) => { retry.Enabled = false; try { await reconnect(); }
            finally { if (!IsDisposed) retry.Enabled = true; } };
        links.Controls.Add(retry); root.Controls.Add(links, 0, 1); root.Controls.Add(editor, 0, 2); Controls.Add(root);
        editor.ControlsRebuilt += (_, _) => { ShellTheme.Apply(editor); UpdateDevices(); };
        FormClosing += (_, e) => {
            if (!hostShutdown && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); }
        };
        Resize += (_, _) => connection.MaximumSize = new Size(Math.Max(120, ClientSize.Width - 32), 0);
        UpdateProjection(); ShellTheme.Apply(this);
    }
    public void UpdateProjection()
    {
        if (IsDisposed) return;
        connection.Text = session.SettingsCurrent ? "Canonical AppSettings v10 · one shared host · closing Settings retains unsaved edits."
            : session.HostStatus + " · " + session.SettingsError + " Effects unavailable; retained draft and saved details remain inspectable.";
        try {
            if (session.Settings is { } settings) editor.Render(settings);
            else editor.ReportUnavailable(connection.Text);
        }
        catch (Exception error) when (error is System.Text.Json.JsonException or KeyNotFoundException or InvalidOperationException or InvalidDataException or ArgumentException) {
            editor.ReportUnavailable("Settings projection is incomplete/unavailable. Retained draft was not submitted. " + error.Message);
        }
        UpdateDevices();
    }
    private void UpdateDevices()
    {
        var devices = session.VoiceCurrent && session.Voice is { } voice ? voice.Devices : [];
        // A key duplicated in either direction is ambiguous; never turn it into a selected device.
        var unique = devices.GroupBy(d => d.Key).Where(g => g.Count() == 1).Select(g => g.Single());
        editor.SetDeviceChoices(unique.Select(d => (d.Key, d.Inputs > 0, d.Outputs > 0)));
    }
    public bool CanCloseForHostShutdown()
    {
        if (HasPendingWork) return false;
        return !HasUnsavedChanges || MessageBox.Show(this,
            "Quit and discard the unsaved Settings draft? Saved Core settings are unchanged. Closing only this window keeps the draft.",
            "SORA · Unsaved settings", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
            MessageBoxDefaultButton.Button2) == DialogResult.Yes;
    }
    public void CloseForHostShutdown() { hostShutdown = true; Close(); }
}
