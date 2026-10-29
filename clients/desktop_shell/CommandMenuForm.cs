namespace Sora.DesktopShell;

// A transient launcher surface, not another Core/state owner. Secondary launches forward bounded IPC.
internal sealed class CommandMenuForm : Form
{
    private readonly Label status;
    private Button? quitButton;
    public CommandMenuForm(Func<string, Task<bool>> send, bool ownsCore = false, Func<string>? hostStatus = null)
    {
        Text = "SORA · Command menu";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f); ClientSize = new Size(460, 430);
        StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false; KeyPreview = true;
        var root = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown,
            WrapContents = false, AutoScroll = true, Padding = new Padding(16) };
        root.Controls.Add(new Label { Text = "Open a panel · no model or avatar required", AutoSize = true });
        status = new Label { Text = hostStatus?.Invoke() ?? "Quit closes this desktop host, not its attached Core or tasks.",
            AutoSize = true, MaximumSize = new Size(420, 0) };
        foreach (var (label, panel) in new[] { ("Open Chat", "chat"), ("Open Settings / recovery", "settings"),
            ("Activity / task evidence", "activity"),
            ("Voice / microphone", "voice"),
            ("Memory / retained context", "memory"),
            ("Agents / delegate task", "agents"), ("Project paths / writers", "paths"),
            ("Note board", "board"), ("Content / registered references", "content"), ("Integrations / details", "integrations"),
            ("Appearance / panels", "appearance"), ("Motion / her motion model", "motion"),
            ("Reconnect / retry startup", "retry"),
            (ownsCore ? "Quit SORA (owned services only)" : "Quit host (keep Core running)", "quit") })
        {
            var button = ShellTheme.Button(label, label);
            if (panel == "quit") quitButton = button;
            button.Click += async (_, _) => {
                button.Enabled = false;
                try
                {
                    var accepted = await send(panel);
                    if (IsDisposed) return;
                    if (accepted) Close();
                    else status.Text = hostStatus?.Invoke() ?? "Host did not accept this command. Stop a pending response or resolve unsaved UI edits before Quit.";
                }
                catch (Exception error) { if (!IsDisposed) status.Text = "Host command not confirmed. " + error.Message; }
                finally { if (!IsDisposed) button.Enabled = true; }
            };
            root.Controls.Add(button);
        }
        root.Controls.Add(status); Controls.Add(root); ShellTheme.Apply(this);
        Shown += (_, _) => {
            var scale = DeviceDpi / 96f; var area = Screen.FromControl(this).WorkingArea;
            ClientSize = new Size(Math.Min((int)(460 * scale), area.Width - 32),
                Math.Min((int)(430 * scale), area.Height - 80));
            status.MaximumSize = new Size(Math.Max(120, ClientSize.Width - (int)(40 * scale)), 0);
        };
        KeyDown += (_, e) => { if (e.KeyCode == Keys.Escape) { e.Handled = true; Close(); } };
    }
    public void UpdateHostState(bool owned, string message)
    {
        if (IsDisposed) return;
        status.Text = message;
        if (quitButton is not null) quitButton.Text = quitButton.AccessibleName = owned
            ? "Quit SORA (owned services only)" : "Quit host (keep Core running)";
    }
}
