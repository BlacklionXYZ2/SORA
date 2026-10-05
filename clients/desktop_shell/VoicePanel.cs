namespace Sora.DesktopShell;

// Host-owned status/actions. No audio capture, timer, inference or worker lifetime in the panel.
internal sealed class VoicePanel : Form
{
    private readonly ShellSession session;
    private readonly PressToTalk hold;
    private readonly CancellationTokenSource lifetime = new();
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly Label operation = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly TextBox devices = new() { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true,
        ScrollBars = ScrollBars.Both, WordWrap = false, AccessibleName = "Actual local voice device keys and channels" };
    private readonly Button start = ShellTheme.Button("Start voice", "Start existing Core-owned local speech worker; microphone stays closed");
    private readonly Button talk = ShellTheme.Button("Hold to talk", "Hold mouse or Space to record, release to send speech");
    private readonly Button output = ShellTheme.Button("Stop speaking only", "Silence voice output without cancelling generation");
    private readonly Button stop = ShellTheme.Button("Stop voice response", "Discard recording and cancel voice response, not Chat or independent tasks");
    private readonly Button closeAudio = ShellTheme.Button("Close audio worker", "Explicitly close Core-owned local audio; closing the panel only hides it");
    public event EventHandler? SettingsRequested;
    private string? holdEpoch;
    private bool shuttingDown, disposed;
    public bool HasPendingWork => hold.Held || hold.Beginning;

    public VoicePanel(ShellSession session)
    {
        this.session = session;
        hold = new PressToTalk(action => session.VoiceActionAsync(action, lifetime.Token, holdEpoch));
        Text = "SORA · Voice"; Font = new Font("Segoe UI", 10.5f);
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(840, 530); MinimumSize = new Size(450, 380);
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(16), RowCount = 5, ColumnCount = 1 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        var settings = ShellTheme.Button("Voice settings", "Open canonical Settings; this panel does not save a competing configuration");
        settings.Click += (_, _) => SettingsRequested?.Invoke(this, EventArgs.Empty);
        buttons.Controls.AddRange([start, talk, output, stop, closeAudio, settings]);
        root.Controls.Add(status, 0, 0); root.Controls.Add(buttons, 0, 1); root.Controls.Add(devices, 0, 2);
        root.Controls.Add(new Label { Dock = DockStyle.Fill, AutoSize = true,
            Text = "Start loads existing local speech assets, without opening the microphone. Release sends speech; holding again interrupts voice output. " +
                "Focus/capture loss or hiding while held discards the recording. Closing this panel otherwise only hides it. " +
                "Close audio worker is an explicit separate operation. Device selection belongs to canonical Settings; inventory is read-only here." }, 0, 3);
        root.Controls.Add(operation, 0, 4); Controls.Add(root);
        start.Click += async (_, _) => await ActAsync("start");
        output.Click += async (_, _) => await ActAsync("stop_output");
        stop.Click += async (_, _) => { if (hold.Held || hold.Beginning) await ReleaseAsync(discard: true); else await ActAsync("stop"); };
        closeAudio.Click += async (_, _) => { await ReleaseAsync(discard: true); await ActAsync("close"); };
        talk.MouseDown += async (_, args) => { if (args.Button == MouseButtons.Left) { talk.Capture = true; await BeginAsync(); } };
        talk.MouseUp += async (_, args) => { if (args.Button == MouseButtons.Left) await ReleaseAsync(); };
        talk.MouseCaptureChanged += async (_, _) => { if (!talk.Capture)
            await ReleaseAsync(discard: (Control.MouseButtons & MouseButtons.Left) != 0); };
        // SuppressKeyPress on KeyDown also suppresses KeyUp; a held microphone needs that release.
        talk.KeyDown += async (_, args) => { if (args.KeyCode == Keys.Space) { args.Handled = true; await BeginAsync(); } };
        talk.KeyPress += (_, args) => { if (args.KeyChar == ' ') args.Handled = true; };
        talk.KeyUp += async (_, args) => { if (args.KeyCode == Keys.Space) { args.Handled = true; await ReleaseAsync(); } };
        talk.LostFocus += async (_, _) => await ReleaseAsync(discard: true);
        Deactivate += async (_, _) => await ReleaseAsync(discard: true);
        FormClosing += async (_, args) => {
            if (shuttingDown) return;
            args.Cancel = true; Hide(); await ReleaseAsync(discard: true);
        };
        session.Changed += Changed; ShellTheme.Apply(this); Render();
        Resize += (_, _) => status.MaximumSize = operation.MaximumSize = new Size(Math.Max(100, ClientSize.Width - 40), 0);
    }
    private void Changed(object? sender, EventArgs args) { if (!disposed) Render(); }
    private void Render()
    {
        var voice = session.Voice;
        status.Text = session.MicrophoneLabel + "\n" + (!session.VoiceCurrent ? session.VoiceError
            : (voice!.Enabled ? voice.State + ": " + voice.Message : "Voice disabled in Settings. " + voice.Message))
            + "\nDialogue model: " + session.Snapshot.StatusLabel + " · " + session.Snapshot.DialogueModel;
        var ready = session.VoiceCurrent && !session.VoiceBusy;
        start.Enabled = ready && !session.MutationBusy && voice!.Can("start");
        // Do not disable a held native button on Begin: doing so loses mouse capture/KeyUp.
        talk.Enabled = hold.Held || hold.Beginning || ready && !session.MutationBusy && voice!.Can("begin");
        talk.Text = hold.Held ? "Release to send" : hold.Beginning ? "Releasing…" : "Hold to talk";
        output.Enabled = ready && voice!.Can("stop_output"); stop.Enabled = ready && voice!.Can("stop");
        closeAudio.Enabled = session.CanUseCore && !session.VoiceBusy;
        var inventory = voice is null ? "Device inventory unavailable." : voice.Devices.Count == 0
            ? "No devices reported yet. Start voice explicitly to enumerate the installed adapter."
            : string.Join("\r\n", voice.Devices.Select(item => $"{item.Key} · input {item.Inputs} / output {item.Outputs}"
                + (item.Index is null ? "" : " · adapter index " + item.Index)
                + (voice.Devices.Count(other => other.Key == item.Key) > 1 ? " · AMBIGUOUS KEY (not silently selected)" : "")));
        if (devices.Text != inventory) devices.Text = inventory;
    }
    private async Task BeginAsync()
    {
        if (hold.Held || hold.Beginning || !talk.Enabled) return;
        holdEpoch = session.CoreInstanceId;
        try { var task = hold.BeginAsync(); Render(); await task; }
        catch (Exception error) { if (!disposed) operation.Text = "Recording not confirmed. Use Close audio if its state is unknown. " + error.Message; }
        finally { if (!disposed) Render(); }
    }
    private async Task ReleaseAsync(bool discard = false)
    {
        try { var task = hold.ReleaseAsync(discard); if (!disposed) Render(); await task; }
        catch (Exception error) { if (!disposed) operation.Text = "Release/stop not confirmed; microphone status may be unknown. " + error.Message; }
        finally { if (!disposed) Render(); }
    }
    private async Task ActAsync(string action)
    {
        try { await session.VoiceActionAsync(action, lifetime.Token); if (!disposed) operation.Text = "Core acknowledged " + action.Replace('_', ' ') + "; current worker state is shown above."; }
        catch (Exception error) { if (!disposed) operation.Text = "Voice operation not confirmed; no automatic retry. " + error.Message; }
        finally { if (!disposed) Render(); }
    }
    public void CloseForHostShutdown() { shuttingDown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !disposed) { disposed = true; session.Changed -= Changed; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }
}
