using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

internal sealed class ShellForm : Form
{
    private readonly ShellSession session;
    private readonly CancellationTokenSource lifetime = new();
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 2000 };
    private readonly Label status = new() { AutoSize = true, MaximumSize = new Size(700, 0) };
    private readonly Label operation = new() { AutoSize = true, MaximumSize = new Size(700, 0) };
    private readonly ChatTranscript transcript = new();
    private readonly ChatComposer composer = new() { Dock = DockStyle.Fill, Multiline = true,
        ScrollBars = ScrollBars.Vertical, AccessibleName = "Message draft", MaxLength = 8000,
        PlaceholderText = "Write to SORA · Shift+Enter for a new line" };
    private readonly Button send = ShellTheme.Button("Send", "Send message");
    private readonly Button stop = ShellTheme.Button("Stop", "Stop response");
    private readonly Button latest = ShellTheme.Button("New messages ↓", "Jump to new messages");
    private readonly FlowLayoutPanel taskChips = new() { Dock = DockStyle.Fill, AutoSize = true, WrapContents = false,
        AutoScroll = true, MaximumSize = new Size(0, 60), AccessibleName = "Recent public task activity; expand exact task evidence" };
    private string renderedActivity = "";
    private readonly FlowLayoutPanel files = new() { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true,
        AccessibleName = "Selected files for this turn" };
    private readonly FlowLayoutPanel pathRow = new() { Dock = DockStyle.Fill, AutoSize = true, Visible = false,
        WrapContents = true };
    private readonly TextBox filePath = new() { Width = 270, AccessibleName = "Local file path to attach",
        PlaceholderText = "Paste a local file path" };
    private readonly ContextMenuStrip overflow = new();
    private readonly ToolTip tips = new();
    private SettingsProbeForm? settings;
    private string renderedFiles = "";
    private bool syncingDraft, restyleTranscript = true;
    private readonly bool hosted;
    private readonly Func<Task>? reconnect;
    private bool hostShutdown;
    private bool resourcesDisposed;
    private bool showTechnicalDetail = true;
    private bool? compactPreference;
    public event EventHandler? SettingsRequested;
    public event EventHandler? ActivityRequested;
    public event Action<string>? ActivityTaskRequested;
    public event Action<string, long>? MemoryRequested;
    public event EventHandler? AgentsRequested;
    public event EventHandler? PathsRequested;
    public event Action<string>? RetainedRequested;
    public event Action<bool>? CompactChanged;

    public ShellForm(ShellSession session, bool hosted = false, Func<Task>? reconnect = null)
    {
        this.session = session; this.hosted = hosted; this.reconnect = reconnect;
        Text = hosted ? "SORA · Chat" : "SORA · GUI-0 connected shell prototype";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f);
        ClientSize = new Size(820, 680); MinimumSize = new Size(400, 440);
        StartPosition = FormStartPosition.CenterScreen;
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4,
            Padding = new Padding(16) };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var toolbar = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        toolbar.Controls.Add(new Label { Text = "SORA", AutoSize = true, Font = new Font(Font, FontStyle.Bold),
            Padding = new Padding(0, 8, 16, 0) });
        void ShowSettings() { if (hosted) SettingsRequested?.Invoke(this, EventArgs.Empty); else OpenSettings(); }
        overflow.Items.Add("Settings / recovery", null, (_, _) => ShowSettings());
        if (hosted) overflow.Items.Add("Activity / task evidence", null, (_, _) => ActivityRequested?.Invoke(this, EventArgs.Empty));
        if (hosted) overflow.Items.Add("Voice / microphone", null, (_, _) => RetainedRequested?.Invoke("voice"));
        if (hosted) overflow.Items.Add("Memory / retained context", null, (_, _) => RetainedRequested?.Invoke("memory"));
        if (hosted) overflow.Items.Add("Agents / delegate task", null, (_, _) => AgentsRequested?.Invoke(this, EventArgs.Empty));
        if (hosted) overflow.Items.Add("Project paths / writers", null, (_, _) => PathsRequested?.Invoke(this, EventArgs.Empty));
        if (hosted) foreach (var (label, panel) in new[] { ("Note board", "board"), ("Content / registered references", "content"), ("Integrations / details", "integrations") })
            overflow.Items.Add(label, null, (_, _) => RetainedRequested?.Invoke(panel));
        overflow.Items.Add("Reconnect / retry startup", null, async (_, _) => await RefreshCoreAsync());
        overflow.Items.Add("Attach a file path…", null, (_, _) => { pathRow.Visible = true; filePath.Focus(); });
        var more = ShellTheme.Button("More", "Chat options, settings and recovery");
        more.Click += (_, _) => overflow.Show(more, new Point(0, more.Height));
        var narrow = ShellTheme.Button("Compact", "Toggle compact layout");
        narrow.Click += (_, _) => {
            var compact = ClientSize.Width / (DeviceDpi / 96f) > 600;
            SetLogicalClientSize(compact ? 460 : 820, compact ? 560 : 700);
            CompactChanged?.Invoke(compact);
        };
        toolbar.Controls.AddRange([more, narrow]);
        root.Controls.Add(toolbar, 0, 0); root.Controls.Add(status, 0, 1);
        var chatLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 7 };
        chatLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 90));
        chatLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true };
        var attach = ShellTheme.Button("Attach", "Choose files to attach to this turn");
        attach.Click += (_, _) => {
            using var picker = new OpenFileDialog { Title = "Choose files for SORA", Multiselect = true,
                CheckFileExists = true, Filter = "All files (*.*)|*.*" };
            if (picker.ShowDialog(this) != DialogResult.OK) return;
            foreach (var path in picker.FileNames) AttachPath(path);
        };
        var addPath = ShellTheme.Button("Attach path", "Attach the entered local file path");
        addPath.Click += (_, _) => { if (AttachPath(filePath.Text.Trim().Trim('"'))) filePath.Clear(); };
        pathRow.Controls.AddRange([filePath, addPath]);
        latest.Visible = false;
        latest.Click += (_, _) => { transcript.JumpToLatest(); latest.Visible = false; };
        transcript.UnseenMessages += (_, _) => latest.Visible = true;
        transcript.VScroll += (_, _) => { if (transcript.AtBottom) latest.Visible = false; };
        actions.Controls.AddRange([attach, send, stop]);
        chatLayout.Controls.Add(transcript, 0, 0); chatLayout.Controls.Add(latest, 0, 1);
        chatLayout.Controls.Add(files, 0, 2); chatLayout.Controls.Add(pathRow, 0, 3);
        chatLayout.Controls.Add(taskChips, 0, 4); chatLayout.Controls.Add(composer, 0, 5); chatLayout.Controls.Add(actions, 0, 6);
        if (hosted) root.Controls.Add(chatLayout, 0, 2);
        else
        {
            var tabs = new TabControl { Dock = DockStyle.Fill, AccessibleName = "Prototype views" };
            var chat = new TabPage("Chat") { Padding = new Padding(8) }; chat.Controls.Add(chatLayout);
            tabs.TabPages.Add(chat); tabs.TabPages.Add(CreateGraphSpike()); root.Controls.Add(tabs, 0, 2);
        }
        root.Controls.Add(operation, 0, 3); Controls.Add(root);
        ShellTheme.Apply(this);
        composer.TextChanged += (_, _) => { if (!syncingDraft) session.Draft = composer.Text; };
        composer.KeyDown += (_, e) => {
            if (composer.CanSubmit(e))
            { e.SuppressKeyPress = true; if (send.Enabled) send.PerformClick(); }
        };
        send.Click += async (_, _) => {
            var request = session.SendAsync(lifetime.Token); Render();
            try { await request; } catch (Exception) { /* Session retains truthful operation/draft. */ }
            if (IsDisposed) return;
            Render(); await RefreshCoreAsync();
        };
        stop.Click += async (_, _) => {
            stop.Enabled = false;
            try { await session.StopAsync(lifetime.Token); } catch (Exception) { }
            if (!IsDisposed) Render();
        };
        timer.Tick += async (_, _) => await RefreshCoreAsync();
        session.Changed += SessionChanged;
        Shown += async (_, _) => { SetLogicalClientSize(compactPreference == true ? 460 : 820,
            compactPreference == true ? 560 : 700); Render(); if (!hosted) { timer.Start(); await RefreshCoreAsync(); } };
        FormClosing += (_, e) => {
            if (hosted && !hostShutdown) { e.Cancel = true; Hide(); return; }
            if (session.Sending) { e.Cancel = true; operation.Text = "Stop the response before closing this prototype."; }
        };
        FormClosed += (_, _) => { timer.Stop(); lifetime.Cancel(); settings?.Close(); };
        Resize += (_, _) => {
            status.MaximumSize = operation.MaximumSize = new Size(Math.Max(100, ClientSize.Width - 40), 0);
        };
    }
    private bool AttachPath(string path)
    {
        try { session.AddAttachment(path); return true; }
        catch (Exception error) when (error is ArgumentException or IOException or UnauthorizedAccessException)
        { operation.Text = "File selection not added. " + error.Message; return false; }
    }
    public void CloseForHostShutdown() { hostShutdown = true; Close(); }
    public void ApplyPreferences(ShellPreferences preferences)
    {
        restyleTranscript = true;
        showTechnicalDetail = preferences.ShowTechnicalDetail;
        if (compactPreference.HasValue && compactPreference != preferences.ChatCompact && Visible)
            SetLogicalClientSize(preferences.ChatCompact ? 460 : 820, preferences.ChatCompact ? 560 : 700);
        compactPreference = preferences.ChatCompact; Render();
    }
    private void SessionChanged(object? sender, EventArgs args) { if (!IsDisposed) Render(); }

    private void SetLogicalClientSize(int width, int height)
    {
        var scale = DeviceDpi / 96f;
        var area = Screen.FromControl(this).WorkingArea;
        MinimumSize = new Size((int)(360 * scale), (int)(400 * scale));
        ClientSize = new Size(Math.Min((int)(width * scale), Math.Max(100, area.Width - 32)),
            Math.Min((int)(height * scale), Math.Max(100, area.Height - 80)));
    }

    private TabPage CreateGraphSpike()
    {
        var scene = GraphLayout.Arrange(Enumerable.Range(1, 12).Select(index =>
            new GraphNode($"fixture-{index:00}", $"N{index}")),
            Enumerable.Range(1, 11).Select(index => new GraphEdge($"fixture-{index:00}",
                $"fixture-{index + 1:00}", "Synthetic feasibility fixture")));
        var page = new TabPage("Graph layout fixture") { Padding = new Padding(8) };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, ColumnCount = 1 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.Controls.Add(new Label { Text = "Synthetic layout fixture · NOT SORA memory data. Arrows select; Ctrl+arrows pan.",
            Dock = DockStyle.Fill, AutoSize = true }, 0, 0);
        var body = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1 };
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 65)); body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 35));
        body.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var graph = new GraphPanel(scene);
        var list = new ListBox { Dock = DockStyle.Fill, AccessibleName = "Graph equivalent node list",
            DisplayMember = "Id", IntegralHeight = false };
        foreach (var node in scene.Nodes) list.Items.Add(node.Node);
        list.SelectedIndexChanged += (_, _) => graph.SelectId((list.SelectedItem as GraphNode)?.Id);
        graph.SelectionChanged += (_, _) => list.SelectedItem = scene.Nodes.First(node => node.Node.Id == graph.SelectedId).Node;
        if (list.Items.Count > 0) list.SelectedIndex = 0;
        body.Controls.Add(graph, 0, 0); body.Controls.Add(list, 1, 0); layout.Controls.Add(body, 0, 1);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true };
        foreach (var (text, action) in new (string, Action)[] {
            ("Zoom in", () => graph.Zoom(1.25f)), ("Zoom out", () => graph.Zoom(0.8f)), ("Centre", graph.Centre) })
        { var button = ShellTheme.Button(text, text + " graph"); button.Click += (_, _) => action(); actions.Controls.Add(button); }
        layout.Controls.Add(actions, 0, 2); page.Controls.Add(layout); return page;
    }

    private void OpenSettings()
    {
        if (settings is null || settings.IsDisposed)
            settings = new SettingsProbeForm(session, RefreshCoreAsync);
        settings.UpdateProjection(); settings.Show(this); settings.Activate();
    }
    private async Task RefreshCoreAsync()
    {
        if (reconnect is not null) { await reconnect(); return; }
        try { await session.RefreshAsync(lifetime.Token); }
        catch (OperationCanceledException) { return; }
        if (!IsDisposed) { Render(); settings?.UpdateProjection(); }
    }
    private void Render()
    {
        var snapshot = session.Snapshot;
        var activity = snapshot.PublicActivity.TakeLast(8).ToArray();
        var memories = snapshot.MemoryActivity.Where(item => item.Core == session.CoreInstanceId).TakeLast(6).ToArray();
        var activityKey = string.Join("|", activity.Select(item => item.EventId).Concat(memories.Select(item => item.Key)));
        if (renderedActivity != activityKey) {
            renderedActivity = activityKey;
            foreach (Control child in taskChips.Controls.Cast<Control>().ToArray()) { taskChips.Controls.Remove(child); child.Dispose(); }
            foreach (var item in activity) {
                var chip = ShellTheme.Button(item.Label + " · " + item.TaskId + " ›", "Inspect exact task " + item.TaskId);
                chip.MaximumSize = new Size(300, 0); chip.AutoEllipsis = true;
                tips.SetToolTip(chip, $"Recent public task activity (not associated with a specific Chat turn)\nSource: {item.Source}\nTask: {item.TaskId}\nRun: {item.RunId ?? "Not recorded"}\nEvent: {item.EventId} · sequence {item.Sequence}\nCorrelation: {item.CorrelationId}\nTime: {item.Timestamp}");
                chip.Click += (_, _) => ActivityTaskRequested?.Invoke(item.TaskId); taskChips.Controls.Add(chip);
            }
            foreach (var item in memories) {
                var chip = ShellTheme.Button(item.Label + " · " + item.MemoryId + " ›", "Request exact Memory " + item.MemoryId);
                chip.MaximumSize = new Size(320, 0); chip.AutoEllipsis = true;
                tips.SetToolTip(chip, "Canonical Memory evidence, not private reasoning or proof of model thoughts.\nMemory: "
                    + item.MemoryId + " · v" + item.Version + "\nRequest correlation: " + (item.DialogueRequest ?? "Owner panel request")
                    + "\nRetrieval: " + (item.RetrievalId ?? "Host presentation acknowledgement")
                    + "\nEvent: " + item.EventId + " · sequence " + item.Sequence + "\nTime: " + item.Timestamp
                    + "\nHistorical evidence, not current visibility. Click revalidates this exact version; drafts are protected.");
                chip.Click += (_, _) => MemoryRequested?.Invoke(item.MemoryId, item.Version); taskChips.Controls.Add(chip);
            }
            ShellTheme.Apply(taskChips);
        }
        taskChips.Visible = hosted && (activity.Length > 0 || memories.Length > 0);
        foreach (Control chip in taskChips.Controls) chip.Enabled = session.CanUseCore;
        status.Text = snapshot.Connected ? snapshot.StatusLabel + " · " + snapshot.DialogueModel :
            "Core unavailable · Settings/recovery remains accessible. Last-known transcript is stale.";
        send.Enabled = session.CanSend && !string.IsNullOrWhiteSpace(session.Draft); stop.Enabled = session.Sending;
        operation.Text = (session.HostStatus.Length > 0 ? session.HostStatus + "\n" : "") +
            session.Operation + (showTechnicalDetail ? $" · {DeviceDpi} DPI" : "");
        if (composer.Text != session.Draft)
        {
            syncingDraft = true;
            try { composer.Text = session.Draft; } finally { syncingDraft = false; }
        }
        var fileKey = string.Join(",", session.Attachments.Select(item => item.Id));
        if (fileKey != renderedFiles)
        {
            renderedFiles = fileKey;
            foreach (Control child in files.Controls.Cast<Control>().ToArray()) { files.Controls.Remove(child); child.Dispose(); }
            foreach (var item in session.Attachments)
            {
                var chip = ShellTheme.Button(item.Label + " ×", "Remove selected file " + item.Path);
                chip.MaximumSize = new Size(360, 0); tips.SetToolTip(chip, item.Path + "\nRemove from this turn; does not delete the file.");
                chip.Click += (_, _) => session.RemoveAttachment(item.Id); files.Controls.Add(chip);
            }
        }
        transcript.UpdateMessages(snapshot.Messages, restyleTranscript); restyleTranscript = false;
    }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed)
        {
            resourcesDisposed = true;
            session.Changed -= SessionChanged; timer.Dispose(); lifetime.Cancel(); lifetime.Dispose(); overflow.Dispose(); tips.Dispose();
        }
        base.Dispose(disposing);
    }
}

internal sealed class SettingsProbeForm : Form
{
    private readonly ShellSession session;
    private readonly Label status = new() { AutoSize = true, Dock = DockStyle.Fill };
    private readonly DataGridView fields = new() { Dock = DockStyle.Fill, ReadOnly = true,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, AccessibleName = "Canonical settings projection",
        SelectionMode = DataGridViewSelectionMode.FullRowSelect };
    private string? rendered;

    public SettingsProbeForm(ShellSession session, Func<Task> refresh)
    {
        this.session = session; Text = "SORA · Settings and recovery · GUI-0 probe";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f); ClientSize = new Size(760, 600); MinimumSize = new Size(400, 350);
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Padding = new Padding(16) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        fields.Columns.Add("name", "Setting"); fields.Columns.Add("saved", "Saved");
        fields.Columns.Add("active", "Active"); fields.Columns.Add("effect", "Applies");
        fields.Columns[0].FillWeight = 40; fields.Columns[0].MinimumWidth = 180;
        fields.Columns[1].FillWeight = fields.Columns[2].FillWeight = 22;
        fields.Columns[3].FillWeight = 16;
        foreach (DataGridViewColumn column in fields.Columns.Cast<DataGridViewColumn>().Skip(1))
            column.MinimumWidth = 70;
        var retry = ShellTheme.Button("Retry connection / settings", "Retry settings projection");
        retry.Click += async (_, _) => { await refresh(); if (!IsDisposed) UpdateProjection(); };
        layout.Controls.Add(status, 0, 0); layout.Controls.Add(fields, 0, 1); layout.Controls.Add(retry, 0, 2);
        Controls.Add(layout); ShellTheme.Apply(this);
        Shown += (_, _) => {
            var scale = DeviceDpi / 96f;
            var area = Screen.FromControl(this).WorkingArea;
            MinimumSize = new Size((int)(400 * scale), (int)(350 * scale));
            ClientSize = new Size(Math.Min((int)(760 * scale), area.Width - 32),
                Math.Min((int)(600 * scale), area.Height - 80));
        };
        fields.EnableHeadersVisualStyles = false;
        fields.DefaultCellStyle.BackColor = ShellTheme.Raised; fields.DefaultCellStyle.ForeColor = ShellTheme.Text;
        fields.DefaultCellStyle.SelectionBackColor = ShellTheme.Accent;
        fields.DefaultCellStyle.SelectionForeColor = ShellTheme.Surface;
        fields.ColumnHeadersDefaultCellStyle.BackColor = ShellTheme.Surface;
        fields.ColumnHeadersDefaultCellStyle.ForeColor = ShellTheme.Text;
        fields.BackgroundColor = ShellTheme.Surface;
    }
    public void UpdateProjection()
    {
        if (IsDisposed) return;
        status.Text = "GUI-0 read-only projection · No settings saves or model reloads.\n" +
            (session.HostStatus.Length > 0 ? session.HostStatus + "\n" : "") +
            (session.SettingsError.Length == 0 ? "Canonical settings available from Core." : session.SettingsError) +
            (!session.Snapshot.Connected ? "\nConnection: " + session.Snapshot.Error : "");
        var raw = session.Settings?.GetRawText();
        if (raw == rendered) return;
        rendered = raw; fields.Rows.Clear();
        if (session.Settings is not JsonElement projection || !projection.TryGetProperty("fields", out var rows)) return;
        foreach (var row in rows.EnumerateArray())
        {
            var index = fields.Rows.Add(row.GetProperty("key").GetString() ?? "", row.GetProperty("value").ToString(),
                row.GetProperty("active_value").ToString(), row.GetProperty("tier").GetString() ?? "");
            foreach (DataGridViewCell cell in fields.Rows[index].Cells)
                cell.ToolTipText = cell.Value?.ToString() ?? "";
        }
    }
}
