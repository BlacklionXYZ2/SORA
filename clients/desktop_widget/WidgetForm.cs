using System.Diagnostics;
using System.Drawing;
using System.Text;

namespace Sora.DesktopWidget;

public sealed class WidgetForm : Form
{
    private readonly WidgetSync sync;
    private readonly string settingsFile;
    private WidgetSettings settings;
    private readonly System.Windows.Forms.Timer pollTimer = new() { Interval = 2400 };
    private readonly NotifyIcon tray;
    private readonly Label status = new();
    private readonly Label providers = new();
    private readonly Button activity = new();
    private readonly Button expand = new();
    private readonly Button quiet = new();
    private readonly RichTextBox transcript = new();
    private readonly TextBox input = new();
    private readonly Button send = new();
    private readonly Button delegateTask = new();
    private readonly Button look = new();
    private readonly Button stopResponse = new();
    private string? dialogueRequestId;
    private TableLayoutPanel? composerLayout;
    private readonly SplitContainer split = new();
    private readonly TabControl sidebar = new();
    private readonly ListView tasks = new();
    private readonly ListBox attachments = new();
    private readonly TextBox attachmentPath = new();
    private readonly RichTextBox preview = new();
    private readonly PictureBox imagePreview = new();
    private readonly TextBox referenceId = new();
    private readonly Label attachmentNote = new();
    private readonly Label composerHint = new();
    private readonly ContextMenuStrip menu = new();
    private readonly List<WidgetAttachment> selectedFiles = [];
    private readonly Font bodyFont = new("Segoe UI", 10.5f);
    private readonly Font roleFont = new("Segoe UI", 10.5f, FontStyle.Bold);
    private readonly Font codeFont = new("Consolas", 10);
    private bool polling;
    private bool sending;
    private bool applyingLayout;
    private bool exitRequested;
    private bool seenInitialSnapshot;
    private string lastMessages = "";
    private string lastTasks = "";
    private int pollDelay = 2400;

    public WidgetForm(WidgetSync sync, string settingsFile)
    {
        this.sync = sync;
        this.settingsFile = settingsFile;
        settings = WidgetSettingsStore.Load(settingsFile);
        Text = "SORA · Companion";
        Icon = SystemIcons.Application;
        AutoScaleMode = AutoScaleMode.Dpi;
        StartPosition = FormStartPosition.Manual;
        MinimumSize = new Size(350, 310);
        BackColor = Color.FromArgb(17, 24, 39);
        ForeColor = Color.FromArgb(237, 242, 248);
        Font = new Font("Segoe UI", 9.5f);
        TopMost = settings.AlwaysOnTop;

        BuildLayout();
        BuildMenu();
        tray = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "SORA companion",
            Visible = true,
            ContextMenuStrip = menu,
        };
        tray.DoubleClick += (_, _) => Restore();
        pollTimer.Tick += async (_, _) => await PollAsync();
        Shown += async (_, _) => { ApplyPlacement(); pollTimer.Start(); await PollAsync(); };
        Move += (_, _) => RememberPosition();
        DpiChanged += (_, _) => BeginInvoke(ApplyPlacement);
        Resize += (_, _) => { if (WindowState == FormWindowState.Minimized) Hide(); };
        FormClosing += (_, eventArgs) =>
        {
            if (exitRequested || eventArgs.CloseReason == CloseReason.WindowsShutDown) return;
            eventArgs.Cancel = true;
            Hide();
        };
        FormClosed += (_, _) =>
        {
            pollTimer.Dispose();
            tray.Visible = false;
            tray.Dispose();
            bodyFont.Dispose();
            roleFont.Dispose();
            codeFont.Dispose();
            imagePreview.Image?.Dispose();
        };
    }

    private void BuildLayout()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = BackColor,
            ColumnCount = 1,
            RowCount = 5,
            Padding = new Padding(10),
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 145));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        Controls.Add(root);

        var header = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4, BackColor = BackColor };
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 105));
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 108));
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 62));
        var identity = new Label
        {
            Text = "SORA", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft,
            Font = new Font("Segoe UI Semibold", 15), ForeColor = Color.FromArgb(225, 237, 255),
        };
        StyleButton(quiet, "Quiet");
        StyleButton(expand, "Expand");
        var options = new Button();
        StyleButton(options, "•••");
        quiet.Click += (_, _) => SetQuiet(!settings.Quiet);
        expand.Click += (_, _) => SetExpanded(!settings.Expanded);
        options.Click += (_, _) => menu.Show(options, 0, options.Height);
        header.Controls.Add(identity, 0, 0);
        header.Controls.Add(quiet, 1, 0);
        header.Controls.Add(expand, 2, 0);
        header.Controls.Add(options, 3, 0);
        root.Controls.Add(header, 0, 0);

        var presence = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, BackColor = BackColor };
        presence.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 42));
        presence.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 38));
        presence.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        status.Dock = DockStyle.Fill;
        status.Text = "Connecting…";
        status.TextAlign = ContentAlignment.MiddleLeft;
        status.ForeColor = Color.FromArgb(148, 163, 184);
        providers.Dock = DockStyle.Fill;
        providers.AutoEllipsis = true;
        providers.TextAlign = ContentAlignment.MiddleLeft;
        providers.ForeColor = Color.FromArgb(167, 190, 219);
        StyleButton(activity, "0 runs");
        activity.Click += (_, _) =>
        {
            SetExpanded(true);
            sidebar.SelectedIndex = 1;
        };
        presence.Controls.Add(status, 0, 0);
        presence.Controls.Add(providers, 1, 0);
        presence.Controls.Add(activity, 2, 0);
        root.Controls.Add(presence, 0, 1);

        split.Dock = DockStyle.Fill;
        split.BackColor = Color.FromArgb(31, 41, 55);
        split.Panel2Collapsed = true;
        transcript.Dock = DockStyle.Fill;
        transcript.BackColor = Color.FromArgb(24, 34, 50);
        transcript.ForeColor = Color.FromArgb(236, 243, 251);
        transcript.BorderStyle = BorderStyle.None;
        transcript.ReadOnly = true;
        transcript.Font = bodyFont;
        transcript.TabStop = false;
        transcript.DetectUrls = false;
        transcript.Padding = new Padding(9);
        split.Panel1.Controls.Add(transcript);
        sidebar.Dock = DockStyle.Fill;
        BuildSidebar();
        split.Panel2.Controls.Add(sidebar);
        root.Controls.Add(split, 0, 2);

        var composer = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4, RowCount = 2, BackColor = BackColor };
        composerLayout = composer;
        composer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        composer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 76));
        composer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100));
        composer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 72));
        composer.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        composer.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
        input.Multiline = true;
        input.ScrollBars = ScrollBars.Vertical;
        input.Dock = DockStyle.Fill;
        input.MaxLength = 16000;
        input.BackColor = Color.FromArgb(32, 45, 65);
        input.ForeColor = Color.White;
        input.BorderStyle = BorderStyle.FixedSingle;
        input.AccessibleName = "Message SORA";
        input.PlaceholderText = "Talk with SORA…";
        input.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && !e.Shift)
            {
                e.SuppressKeyPress = true;
                _ = SendAsync(false);
            }
        };
        StyleButton(send, "Send");
        StyleButton(delegateTask, "Delegate");
        StyleButton(look, "Look");
        look.AccessibleName = "Look at screen under cursor once";
        send.Click += async (_, _) => await SendAsync(false);
        delegateTask.Click += async (_, _) => await SendAsync(true);
        look.Click += async (_, _) => await LookAtScreenAsync();
        StyleButton(stopResponse, "Stop");
        stopResponse.AccessibleName = "Stop current SORA response";
        stopResponse.Enabled = false;
        stopResponse.Click += async (_, _) => await StopResponseAsync();
        composerHint.Dock = DockStyle.Fill;
        composerHint.ForeColor = Color.FromArgb(137, 153, 174);
        composerHint.Font = new Font("Segoe UI", 8);
        composer.Controls.Add(input, 0, 0);
        composer.SetColumnSpan(input, 4);
        composerHint.TextAlign = ContentAlignment.MiddleLeft;
        composer.Controls.Add(look, 1, 1);
        composer.Controls.Add(stopResponse, 0, 1);
        composer.Controls.Add(delegateTask, 2, 1);
        composer.Controls.Add(send, 3, 1);
        root.Controls.Add(composer, 0, 3);
        root.Controls.Add(composerHint, 0, 4);
        KeyPreview = true;
        KeyDown += (_, e) =>
        {
            if (e.Control && e.KeyCode == Keys.E) { SetExpanded(!settings.Expanded); e.Handled = true; }
            if (e.Control && e.KeyCode == Keys.L) { input.Focus(); e.Handled = true; }
        };
        UpdateControls();
    }

    private void BuildSidebar()
    {
        var contentTab = new TabPage("Files & references")
        {
            BackColor = Color.FromArgb(24, 34, 50), ForeColor = ForeColor,
        };
        var content = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 6, ColumnCount = 1 };
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 72));
        content.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        content.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
        var fileButtons = new FlowLayoutPanel { Dock = DockStyle.Fill };
        var add = new Button { Text = "Attach file" };
        var remove = new Button { Text = "Remove" };
        var open = new Button { Text = "Open selected" };
        foreach (var button in new[] { add, remove, open })
        {
            button.AutoSize = true;
            StyleButton(button, button.Text);
            fileButtons.Controls.Add(button);
        }
        add.Click += (_, _) => AddFile();
        remove.Click += (_, _) => RemoveFile();
        open.Click += (_, _) => OpenSelectedFile();
        var pathRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 106));
        attachmentPath.Dock = DockStyle.Fill;
        attachmentPath.PlaceholderText = "Paste any local file path";
        attachmentPath.AccessibleName = "Local file path to attach";
        var attachPath = new Button { Text = "Attach path" };
        StyleButton(attachPath, attachPath.Text);
        attachPath.Dock = DockStyle.Fill;
        attachPath.Click += (_, _) => AddFilePath(attachmentPath.Text);
        pathRow.Controls.Add(attachmentPath, 0, 0);
        pathRow.Controls.Add(attachPath, 1, 0);
        attachments.Dock = DockStyle.Fill;
        attachments.BackColor = Color.FromArgb(32, 45, 65);
        attachments.ForeColor = Color.White;
        attachments.SelectedIndexChanged += (_, _) => ShowPreview();
        var previewPanel = new Panel { Dock = DockStyle.Fill };
        preview.Dock = DockStyle.Fill;
        preview.ReadOnly = true;
        preview.WordWrap = false;
        preview.BackColor = Color.FromArgb(18, 27, 41);
        preview.ForeColor = ForeColor;
        preview.Font = new Font("Consolas", 9);
        imagePreview.Dock = DockStyle.Fill;
        imagePreview.SizeMode = PictureBoxSizeMode.Zoom;
        imagePreview.Visible = false;
        previewPanel.Controls.Add(preview);
        previewPanel.Controls.Add(imagePreview);
        var refRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        refRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        refRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        refRow.Controls.Add(new Label { Text = "Reference ID", AutoSize = true, Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft, ForeColor = ForeColor }, 0, 0);
        referenceId.Dock = DockStyle.Fill;
        referenceId.PlaceholderText = "Optional canonical Core reference";
        referenceId.AccessibleName = "Canonical reference ID";
        refRow.Controls.Add(referenceId, 1, 0);
        attachmentNote.Dock = DockStyle.Fill;
        attachmentNote.ForeColor = Color.FromArgb(159, 180, 204);
        attachmentNote.Font = new Font("Segoe UI", 8);
        attachmentNote.Text = "Local Core reads selected files for this turn. Images use a local vision model; file contents are not saved in chat history.";
        content.Controls.Add(fileButtons, 0, 0);
        content.Controls.Add(pathRow, 0, 1);
        content.Controls.Add(attachments, 0, 2);
        content.Controls.Add(previewPanel, 0, 3);
        content.Controls.Add(refRow, 0, 4);
        content.Controls.Add(attachmentNote, 0, 5);
        contentTab.Controls.Add(content);

        var activityTab = new TabPage("Activity")
        {
            BackColor = Color.FromArgb(24, 34, 50), ForeColor = ForeColor,
        };
        var activityLayout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2 };
        activityLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        activityLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var details = new CheckBox { Text = "Show task IDs and result references", Dock = DockStyle.Fill,
            Checked = settings.ShowTechnicalDetail, ForeColor = ForeColor };
        details.CheckedChanged += (_, _) =>
        {
            settings = settings with { ShowTechnicalDetail = details.Checked };
            SaveSettings();
            RenderTasks(sync.Current);
        };
        tasks.Dock = DockStyle.Fill;
        tasks.View = View.Details;
        tasks.FullRowSelect = true;
        tasks.BackColor = Color.FromArgb(18, 27, 41);
        tasks.ForeColor = ForeColor;
        tasks.Columns.Add("Specialist", 110);
        tasks.Columns.Add("State", 100);
        tasks.Columns.Add("Detail", 250);
        activityLayout.Controls.Add(details, 0, 0);
        activityLayout.Controls.Add(tasks, 0, 1);
        activityTab.Controls.Add(activityLayout);
        sidebar.TabPages.Add(contentTab);
        sidebar.TabPages.Add(activityTab);
    }

    private void BuildMenu()
    {
        menu.Items.Add("Show SORA", null, (_, _) => Restore());
        menu.Items.Add("Local voice…", null, (_, _) => new VoiceForm(sync).Show(this));
        menu.Items.Add("Agents and models…", null, (_, _) => new AgentCatalogueForm(sync).Show(this));
        menu.Items.Add("Project paths and writers…", null, (_, _) => new ProjectPathsForm(sync).Show(this));
        menu.Items.Add("Expand / compact", null, (_, _) => SetExpanded(!settings.Expanded));
        menu.Items.Add("Quiet mode", null, (_, _) => SetQuiet(!settings.Quiet));
        menu.Items.Add("Always on top", null, (_, _) =>
        {
            settings = settings with { AlwaysOnTop = !settings.AlwaysOnTop };
            TopMost = settings.AlwaysOnTop;
            SaveSettings();
        });
        var anchors = new ToolStripMenuItem("Anchor");
        foreach (var anchor in Enum.GetValues<WidgetAnchor>())
        {
            anchors.DropDownItems.Add(anchor.ToString(), null, (_, _) =>
            {
                settings = settings with { Anchor = anchor, SavedX = null, SavedY = null };
                ApplyPlacement();
                SaveSettings();
            });
        }
        menu.Items.Add(anchors);
        var monitors = new ToolStripMenuItem("Monitor");
        monitors.DropDownOpening += (_, _) =>
        {
            monitors.DropDownItems.Clear();
            foreach (var screen in Screen.AllScreens)
                monitors.DropDownItems.Add(screen.DeviceName, null, (_, _) =>
                {
                    settings = settings with { Monitor = screen.DeviceName, SavedX = null, SavedY = null };
                    ApplyPlacement();
                    SaveSettings();
                });
        };
        menu.Items.Add(monitors);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit SORA widget", null, (_, _) => { exitRequested = true; Close(); });
    }

    private static void StyleButton(Button button, string label)
    {
        button.Text = label;
        button.Dock = DockStyle.Fill;
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = 0;
        button.BackColor = Color.FromArgb(43, 62, 87);
        button.ForeColor = Color.FromArgb(237, 245, 255);
        button.Cursor = Cursors.Hand;
    }

    private void ApplyPlacement()
    {
        applyingLayout = true;
        try
        {
            var screen = Screen.AllScreens.FirstOrDefault(item => item.DeviceName == settings.Monitor)
                ?? Screen.PrimaryScreen ?? Screen.AllScreens[0];
            var work = screen.WorkingArea;
            // Screen.WorkingArea uses device pixels; preserve a readable logical size on mixed DPI.
            var scale = DeviceDpi / 96f;
            // WinForms can rescale absolute columns before the first placement. Restore
            // device-pixel widths alongside the window size so button labels stay readable.
            if (composerLayout is not null)
            {
                composerLayout.ColumnStyles[1].Width = 76 * scale;
                composerLayout.ColumnStyles[2].Width = 100 * scale;
                composerLayout.ColumnStyles[3].Width = 72 * scale;
            }
            var target = settings.Expanded
                ? new Size((int)(920 * scale), (int)(700 * scale))
                : new Size((int)(420 * scale), (int)(420 * scale));
            if (!settings.Expanded) split.Panel2Collapsed = true;
            Size = new Size(Math.Min(target.Width, work.Width), Math.Min(target.Height, work.Height));
            var requested = settings.SavedX.HasValue && settings.SavedY.HasValue
                ? new Point(settings.SavedX.Value, settings.SavedY.Value)
                : WidgetGeometry.AnchorTo(work, Size, settings.Anchor);
            Location = WidgetGeometry.Clamp(work, Size, requested);
            if (settings.Expanded) split.Panel2Collapsed = false;
            if (settings.Expanded) split.SplitterDistance = Math.Max(220, Width / 2);
            UpdateControls();
        }
        finally { applyingLayout = false; }
    }

    private void RememberPosition()
    {
        if (applyingLayout || !Visible || WindowState != FormWindowState.Normal) return;
        var screen = Screen.FromRectangle(Bounds);
        settings = settings with { Monitor = screen.DeviceName, SavedX = Left, SavedY = Top };
        SaveSettings();
    }

    private void SaveSettings()
    {
        try { WidgetSettingsStore.Save(settingsFile, settings); }
        catch (IOException) { status.Text = "Settings could not be saved"; }
    }

    private void SetExpanded(bool expanded)
    {
        if (settings.Expanded == expanded) return;
        settings = settings with { Expanded = expanded, SavedX = null, SavedY = null };
        ApplyPlacement();
        SaveSettings();
        Render(sync.Current);
    }

    private void SetQuiet(bool enabled)
    {
        settings = settings with { Quiet = enabled };
        UpdateControls();
        SaveSettings();
    }

    private void UpdateControls()
    {
        quiet.Text = settings.Quiet ? "Quiet ✓" : "Quiet";
        expand.Text = settings.Expanded ? "Compact" : "Expand";
        composerHint.Text = "Enter send · Shift+Enter newline · Ctrl+E " +
            (settings.Expanded ? "compact" : "expand");
    }

    private void Restore()
    {
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
        input.Focus();
    }

    private async Task PollAsync()
    {
        if (polling || IsDisposed) return;
        polling = true;
        try
        {
            var previous = sync.Current;
            var current = await sync.RefreshAsync();
            if (IsDisposed) return;
            Render(current);
            if (current.Connected)
            {
                NotifyChanges(previous, current);
                seenInitialSnapshot = true;
                pollDelay = 2400;
            }
            else pollDelay = Math.Min(15000, pollDelay * 2);
            pollTimer.Interval = pollDelay;
        }
        finally { polling = false; }
    }

    private void Render(WidgetSnapshot state)
    {
        status.Text = sending ? "Working…" : state.StatusLabel;
        status.AccessibleDescription = state.Connected ? "Core connected" : state.Error;
        providers.Text = state.DialogueModel;
        providers.AccessibleDescription = "Dialogue: " + state.DialogueModel + ". Specialists: " +
            string.Join(", ", state.Providers.Select(p =>
            $"{p.Name} {(p.Available ? "available" : "offline")}"));
        activity.Text = $"{state.ActiveWorkers} run{(state.ActiveWorkers == 1 ? "" : "s")}";
        RenderMessages(state);
        RenderTasks(state);
    }

    private void RenderMessages(WidgetSnapshot state)
    {
        var messages = settings.Expanded ? state.Messages : state.Messages.TakeLast(4).ToArray();
        var key = $"{settings.Expanded}:{string.Join('|', messages.Select(m => m.Id))}";
        if (key == lastMessages) return;
        lastMessages = key;
        transcript.Clear();
        if (messages.Count == 0)
        {
            transcript.Text = "SORA is here. Start a conversation.";
            return;
        }
        foreach (var message in messages)
        {
            transcript.SelectionColor = message.Role == "user"
                ? Color.FromArgb(145, 205, 255) : Color.FromArgb(180, 235, 211);
            transcript.SelectionFont = roleFont;
            transcript.AppendText(message.Role == "user" ? "You\n" : "SORA\n");
            foreach (var line in ChatText.Lines(message.Content, message.Role == "assistant"))
            {
                transcript.SelectionFont = line.Code ? codeFont : bodyFont;
                transcript.SelectionColor = line.Code
                    ? Color.FromArgb(228, 224, 182) : ForeColor;
                transcript.AppendText(line.Text + "\n");
            }
            transcript.AppendText("\n");
        }
        transcript.SelectionStart = transcript.TextLength;
        transcript.ScrollToCaret();
    }

    private void RenderTasks(WidgetSnapshot state)
    {
        var key = $"{settings.ShowTechnicalDetail}:{string.Join('|', state.Tasks.Select(t => t.Id + t.Status))}";
        if (key == lastTasks) return;
        lastTasks = key;
        tasks.BeginUpdate();
        try
        {
            tasks.Items.Clear();
            foreach (var task in state.Tasks)
            {
                var item = new ListViewItem(task.Backend);
                item.SubItems.Add(task.Status);
                item.SubItems.Add(settings.ShowTechnicalDetail
                    ? $"{task.Id}  {task.ResultRef}" : "Details hidden");
                tasks.Items.Add(item);
            }
        }
        finally { tasks.EndUpdate(); }
    }

    private void NotifyChanges(WidgetSnapshot previous, WidgetSnapshot current)
    {
        if (!seenInitialSnapshot || settings.Quiet || Visible && ContainsFocus) return;
        var priorTasks = previous.Tasks.ToDictionary(t => t.Id, t => t.Status);
        var completed = current.Tasks.FirstOrDefault(t =>
            priorTasks.TryGetValue(t.Id, out var old) && old != t.Status &&
            t.Status is "completed" or "failed" or "cancelled");
        if (completed is not null)
            tray.ShowBalloonTip(3000, "SORA task update",
                $"{completed.Backend}: {completed.Status}", ToolTipIcon.Info);
        else if (previous.Messages.LastOrDefault()?.Id != current.Messages.LastOrDefault()?.Id &&
                 current.Messages.LastOrDefault()?.Role == "assistant")
            tray.ShowBalloonTip(3000, "SORA replied", "A new message is ready.", ToolTipIcon.Info);
    }

    private async Task SendAsync(bool delegateWork)
    {
        if (sending) return;
        var raw = input.Text.Trim();
        if (raw.Length == 0) return;
        string content;
        try { content = delegateWork
            ? WidgetAttachments.Compose(raw, selectedFiles, referenceId.Text) : raw; }
        catch (ArgumentException error) { MessageBox.Show(this, error.Message, "SORA", MessageBoxButtons.OK); return; }
        if (delegateWork)
        {
            using var selector = new AgentCatalogueForm(sync, content, string.IsNullOrWhiteSpace(referenceId.Text)
                ? null : referenceId.Text.Trim());
            if (selector.ShowDialog(this) != DialogResult.OK) return;
            input.Clear(); selectedFiles.Clear(); attachments.Items.Clear(); referenceId.Clear(); preview.Clear();
            await PollAsync();
            return;
        }
        sending = true;
        dialogueRequestId = delegateWork ? null : Guid.NewGuid().ToString("N");
        stopResponse.Enabled = dialogueRequestId is not null;
        send.Enabled = false;
        delegateTask.Enabled = false;
        look.Enabled = false;
        input.Clear();
        status.Text = delegateWork ? "Starting specialist…" : "Thinking…";
        try
        {
            if (delegateWork)
                await sync.DelegateAsync(content, string.IsNullOrWhiteSpace(referenceId.Text)
                    ? null : referenceId.Text.Trim());
            else if (selectedFiles.Count > 0)
                await sync.DialogueWithFilesAsync(content, selectedFiles.Select(file => file.Path).ToArray(),
                    requestId: dialogueRequestId);
            else await sync.DialogueAsync(content, requestId: dialogueRequestId);
            selectedFiles.Clear();
            attachments.Items.Clear();
            referenceId.Clear();
            preview.Clear();
            await PollAsync();
        }
        catch (SoraRequestException error) when (error.Code == "DIALOGUE_CANCELLED")
        {
            if (input.Text.Length == 0) input.Text = raw;
            await PollAsync();
            status.Text = "Response stopped · draft preserved";
        }
        catch (Exception error)
        {
            if (input.Text.Length == 0) input.Text = raw;
            status.Text = "Message not sent";
            MessageBox.Show(this, error.Message, "SORA connection", MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
        finally { dialogueRequestId = null; stopResponse.Enabled = false;
            sending = false; send.Enabled = true; delegateTask.Enabled = true;
            look.Enabled = true; input.Focus(); }
    }

    private async Task LookAtScreenAsync()
    {
        if (sending) return;
        sending = true;
        var text = input.Text.Trim();
        dialogueRequestId = Guid.NewGuid().ToString("N");
        stopResponse.Enabled = true;
        send.Enabled = false;
        delegateTask.Enabled = false;
        look.Enabled = false;
        status.Text = "Looking at screen…";
        try
        {
            await sync.DesktopDialogueAsync(text, requestId: dialogueRequestId);
            if (input.Text.Trim() == text) input.Clear();
            await PollAsync();
        }
        catch (SoraRequestException error) when (error.Code == "DIALOGUE_CANCELLED")
        { await PollAsync(); status.Text = "Screen response stopped"; }
        catch (Exception error)
        {
            status.Text = "Screen view unavailable";
            MessageBox.Show(this, error.Message, "SORA desktop view",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        finally
        {
            dialogueRequestId = null;
            stopResponse.Enabled = false;
            sending = false;
            send.Enabled = true;
            delegateTask.Enabled = true;
            look.Enabled = true;
            input.Focus();
        }
    }

    private async Task StopResponseAsync()
    {
        var requestId = dialogueRequestId;
        if (requestId is null) return;
        stopResponse.Enabled = false;
        status.Text = "Stopping… dispatched actions are not undone";
        try
        {
            var result = await sync.CancelDialogueAsync(requestId);
            if (dialogueRequestId == requestId && result.GetProperty("state").GetString() == "already-finishing")
                status.Text = "Already finishing · check transcript";
        }
        catch (Exception error)
        {
            if (dialogueRequestId == requestId)
            { status.Text = "Stop not confirmed: " + error.Message; stopResponse.Enabled = true; }
        }
    }

    private void AddFile()
    {
        try
        {
            using var dialog = new OpenFileDialog
            {
                Title = "Select a file for SORA", Multiselect = true,
                CheckFileExists = true, AutoUpgradeEnabled = false, RestoreDirectory = true,
            };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            foreach (var path in dialog.FileNames) AddFilePath(path);
        }
        catch (Exception error)
        {
            status.Text = $"File picker unavailable: {error.Message}";
        }
    }

    private void AddFilePath(string selectedPath)
    {
        if (selectedFiles.Count >= 3) { status.Text = "Attach at most three files."; return; }
        try
        {
            var attachment = WidgetAttachments.Inspect(selectedPath);
            if (selectedFiles.Any(file => file.Path.Equals(attachment.Path,
                StringComparison.OrdinalIgnoreCase))) return;
            selectedFiles.Add(attachment);
            attachments.Items.Add(attachment.Label);
            attachments.SelectedIndex = attachments.Items.Count - 1;
            attachmentPath.Clear();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or
                                      InvalidDataException or System.Xml.XmlException or ArgumentException)
        {
            status.Text = $"File unavailable: {error.Message}";
        }
    }

    private void RemoveFile()
    {
        var index = attachments.SelectedIndex;
        if (index < 0) return;
        selectedFiles.RemoveAt(index);
        attachments.Items.RemoveAt(index);
        ShowPreview();
    }

    private void ShowPreview()
    {
        imagePreview.Image?.Dispose();
        imagePreview.Image = null;
        var index = attachments.SelectedIndex;
        if (index < 0 || index >= selectedFiles.Count) { preview.Clear(); return; }
        var selected = selectedFiles[index];
        imagePreview.Visible = selected.Kind == "image";
        preview.Visible = !imagePreview.Visible;
        if (!imagePreview.Visible) { preview.Text = selected.Preview; return; }
        try
        {
            using var stream = File.OpenRead(selected.Path);
            using var image = Image.FromStream(stream);
            imagePreview.Image = new Bitmap(image);
        }
        catch (Exception error) when (error is IOException or ArgumentException)
        {
            imagePreview.Visible = false;
            preview.Visible = true;
            preview.Text = error.Message;
        }
    }

    private void OpenSelectedFile()
    {
        var index = attachments.SelectedIndex;
        if (index < 0 || index >= selectedFiles.Count) return;
        try
        {
            Process.Start(new ProcessStartInfo(selectedFiles[index].Path) { UseShellExecute = true });
        }
        catch (Exception error) when (error is IOException or System.ComponentModel.Win32Exception)
        {
            MessageBox.Show(this, error.Message, "Unable to open file", MessageBoxButtons.OK);
        }
    }
}
