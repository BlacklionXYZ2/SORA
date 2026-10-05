using System.Drawing;
using System.Text;
using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopApp;

public sealed record FullAppPreferences(bool ShowTechnicalDetail = false, int SelectedTab = 0);

public sealed class FullAppForm : Form
{
    private readonly WidgetApiClient api;
    private readonly WidgetSync widget;
    private readonly FullAppSync sync;
    private readonly string settingsFile;
    private FullAppPreferences preferences;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 2500 };
    private readonly TabControl tabs = new() { Dock = DockStyle.Fill };
    private readonly Label connection = new() { Dock = DockStyle.Fill, AutoEllipsis = true,
        TextAlign = ContentAlignment.MiddleRight };
    private readonly RichTextBox transcript = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false };
    private readonly TextBox composer = new() { Dock = DockStyle.Fill, Multiline = true, ScrollBars = ScrollBars.Vertical };
    private readonly TextBox chatFile = new() { Dock = DockStyle.Fill,
        PlaceholderText = "Optional local file path to attach" };
    private readonly List<Button> chatActions = [];
    private readonly Button stopResponse = Button("Stop response");
    private string? dialogueRequestId;
    private DateTimeOffset actionStatusUntil;
    private readonly DataGridView activity = Grid();
    private readonly TextBox steerText = new() { Dock = DockStyle.Fill, PlaceholderText = "Instruction for the selected running task" };
    private readonly DataGridView content = Grid();
    private readonly TextBox reference = new() { Dock = DockStyle.Fill, PlaceholderText = "Selected or exact reference ID" };
    private readonly DataGridView integrations = Grid();
    private readonly RichTextBox integrationDetail = new() { Dock = DockStyle.Fill, ReadOnly = true };
    private readonly RichTextBox settingsText = new() { Dock = DockStyle.Fill, ReadOnly = true };
    private readonly ComboBox dialogueBackend = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
    private readonly ComboBox dialogueModel = new() { Dock = DockStyle.Fill,
        DropDownStyle = ComboBoxStyle.DropDown };
    private readonly TextBox dialogueModelFolder = new() { Dock = DockStyle.Fill,
        PlaceholderText = "LM Studio models directory" };
    private readonly TextBox dialogueEndpoint = new() { Dock = DockStyle.Fill,
        PlaceholderText = "HTTPS or local HTTP endpoint ending in /v1" };
    private readonly NumericUpDown dialogueTimeout = new() { Dock = DockStyle.Fill,
        Minimum = 1, Maximum = 300, DecimalPlaces = 1, Increment = 0.5M };
    private readonly NumericUpDown workerCount = new() { Dock = DockStyle.Fill, Minimum = 1, Maximum = 16 };
    private readonly NumericUpDown contextLimit = new() { Dock = DockStyle.Fill,
        Minimum = 256, Maximum = 65536, Increment = 256 };
    private readonly Label settingsState = new() { Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft, Text = "Waiting for Core settings…" };
    private readonly DataGridView permissions = Grid();
    private readonly CheckBox technical = new() { Text = "Show technical identifiers", AutoSize = true };
    private readonly Label actionStatus = new() { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
    private readonly Label avatarStatus = new() { AutoSize = true, MaximumSize = new Size(900, 0) };
    private string lastConnectionError = "";
    private bool polling;
    private string lastTranscript = "";
    private string lastActivity = "";
    private string lastContent = "";
    private string lastIntegrations = "";
    private string lastSettings = "";
    private int loadedSettingsRevision = -1;
    private bool loadedManagedMode;
    private ModelSettingsEditor? modelSettingsEditor;
    private TabPage? settingsPage;
    private bool settingsDirty;
    private bool settingsLoading;
    private KanbanBoardForm? board;

    public FullAppForm(WidgetApiClient api, WidgetSync widget, FullAppSync sync, string settingsFile)
    {
        this.api = api;
        this.widget = widget;
        this.sync = sync;
        this.settingsFile = settingsFile;
        preferences = LoadPreferences(settingsFile);
        dialogueBackend.Items.AddRange(["deterministic", "openai-compatible"]);
        dialogueBackend.SelectedIndex = 0;
        dialogueBackend.SelectedIndexChanged += (_, _) => MarkSettingsDirty();
        dialogueModel.TextChanged += (_, _) => MarkSettingsDirty();
        dialogueModelFolder.TextChanged += (_, _) => MarkSettingsDirty();
        dialogueEndpoint.TextChanged += (_, _) => MarkSettingsDirty();
        dialogueTimeout.ValueChanged += (_, _) => MarkSettingsDirty();
        workerCount.ValueChanged += (_, _) => MarkSettingsDirty();
        contextLimit.ValueChanged += (_, _) => MarkSettingsDirty();
        Text = "SORA · Full application";
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        Size = new Size(1190, 800);
        MinimumSize = new Size(900, 620);
        Font = new Font("Segoe UI", 10);
        BackColor = Color.FromArgb(18, 26, 40);
        ForeColor = Color.FromArgb(237, 243, 251);
        BuildLayout();
        tabs.SelectedIndex = Math.Clamp(preferences.SelectedTab, 0, tabs.TabCount - 1);
        tabs.SelectedIndexChanged += (_, _) => SavePreferences();
        technical.Checked = preferences.ShowTechnicalDetail;
        technical.CheckedChanged += (_, _) => { SavePreferences(); Render(sync.Current); };
        timer.Tick += async (_, _) => await RefreshAsync();
        Shown += async (_, _) => { timer.Start(); await RefreshAsync(); };
        FormClosed += (_, _) => timer.Dispose();
        KeyPreview = true;
        KeyDown += (_, e) =>
        {
            if (e.Control && e.KeyCode == Keys.L) { tabs.SelectedIndex = 0; composer.Focus(); e.SuppressKeyPress = true; }
        };
    }

    private void BuildLayout()
    {
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3,
            Padding = new Padding(14), BackColor = BackColor };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        Controls.Add(root);
        var header = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 60));
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 40));
        header.Controls.Add(new Label { Text = "SORA", Dock = DockStyle.Fill,
            Font = new Font("Segoe UI Semibold", 19), ForeColor = Color.FromArgb(218, 235, 255),
            TextAlign = ContentAlignment.MiddleLeft }, 0, 0);
        connection.Text = "Connecting…";
        connection.ForeColor = Color.FromArgb(166, 190, 219);
        header.Controls.Add(connection, 1, 0);
        root.Controls.Add(header, 0, 0);
        tabs.TabPages.Add(ChatPage());
        tabs.TabPages.Add(ActivityPage());
        tabs.TabPages.Add(ContentPage());
        tabs.TabPages.Add(IntegrationsPage());
        tabs.TabPages.Add(SettingsPage());
        tabs.TabPages.Add(CompanionPage());
        root.Controls.Add(tabs, 0, 1);
        actionStatus.Text = "Conversation and delegated work share the same local Core state.";
        actionStatus.ForeColor = Color.FromArgb(166, 190, 219);
        root.Controls.Add(actionStatus, 0, 2);
    }

    private TabPage ChatPage()
    {
        var page = Page("Chat");
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4 };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 95));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        StyleText(transcript);
        transcript.AccessibleName = "Conversation history";
        layout.Controls.Add(transcript, 0, 0);
        composer.AccessibleName = "Message SORA";
        composer.BackColor = Color.FromArgb(34, 47, 67);
        composer.ForeColor = Color.White;
        composer.KeyDown += async (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && !e.Shift)
            { e.SuppressKeyPress = true; await SendDialogueAsync(); }
        };
        layout.Controls.Add(composer, 0, 1);
        var fileRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        fileRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        fileRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 126));
        chatFile.AccessibleName = "Local file to attach to SORA message";
        fileRow.Controls.Add(chatFile, 0, 0);
        var browse = Button("Attach file");
        browse.Click += (_, _) => BrowseChatFile();
        fileRow.Controls.Add(browse, 1, 0);
        layout.Controls.Add(fileRow, 0, 2);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft };
        var send = Button("Send to SORA");
        var look = Button("Look at screen");
        var delegateTask = Button("Delegate as task");
        var planTask = Button("Fix this later (TODO)");
        var voice = Button("Voice…");
        voice.Click += (_, _) => new VoiceForm(widget).Show(this);
        buttons.Controls.Add(voice);
        send.Click += async (_, _) => await SendDialogueAsync();
        look.Click += async (_, _) => await LookAtScreenAsync();
        delegateTask.Click += async (_, _) => await DelegateAsync();
        planTask.Click += async (_, _) => await PlanFromChatAsync();
        buttons.Controls.Add(send);
        buttons.Controls.Add(look);
        buttons.Controls.Add(delegateTask);
        buttons.Controls.Add(planTask);
        stopResponse.Enabled = false;
        stopResponse.AccessibleName = "Stop current SORA response";
        stopResponse.Click += async (_, _) => await StopResponseAsync();
        buttons.Controls.Add(stopResponse);
        chatActions.AddRange([send, look, delegateTask, planTask]);
        layout.Controls.Add(buttons, 0, 3);
        page.Controls.Add(layout);
        return page;
    }

    private TabPage CompanionPage()
    {
        var page = Page("3D companion");
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true };
        layout.Controls.Add(avatarStatus);
        layout.Controls.Add(new Label { AutoSize = true, MaximumSize = new Size(850, 0),
            Text = "Drag SORA to move her around the desktop. These buttons preview her poses. " +
                "She shows thinking while answering and waiting while a specialist works." });
        var poses = new FlowLayoutPanel { AutoSize = true, WrapContents = true };
        foreach (var pose in new[] { ("Wave", "waving"), ("Sit", "sitting"),
            ("Lean", "leaning"), ("Climb pose", "climbing"), ("Stand / reset", "idle") })
        {
            var button = Button(pose.Item1);
            button.Click += async (_, _) => await RunActionAsync(async () =>
            {
                await api.PostAsync("/api/v1/companion", new { state = pose.Item2 }, default);
            }, "Pose requested.");
            poses.Controls.Add(button);
        }
        layout.Controls.Add(poses);
        layout.Controls.Add(new Label { AutoSize = true, MaximumSize = new Size(850, 0),
            Text = "Bundled avatar: Seed-san © VirtualCast, Inc. (VRM Public License 1.0). " +
                "To use your own VRM: Start-SORA.ps1 -AvatarPath 'C:\\path\\SORA.vrm'." });
        page.Controls.Add(layout);
        return page;
    }

    private TabPage ActivityPage()
    {
        var page = Page("Activity");
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3 };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 88));
        activity.Columns.Add("description", "Delegated work");
        activity.Columns.Add("status", "Status");
        activity.Columns.Add("backend", "Specialist");
        activity.Columns.Add("model", "Requested model");
        activity.Columns.Add("project", "Project / mode");
        activity.Columns.Add("updated", "Updated");
        activity.Columns[0].FillWeight = 34;
        activity.Columns[1].FillWeight = 12;
        activity.Columns[2].FillWeight = 14;
        activity.Columns[3].FillWeight = 22;
        activity.Columns[4].FillWeight = 32;
        activity.Columns[5].FillWeight = 14;
        activity.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize;
        activity.DefaultCellStyle.WrapMode = DataGridViewTriState.True;
        activity.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.DisplayedCells;
        layout.Controls.Add(activity, 0, 0);
        activity.CellDoubleClick += (_, _) => {
            if (activity.SelectedRows.Count > 0 && activity.SelectedRows[0].Tag is string taskId)
                new TaskEvidenceForm(widget, taskId).Show(this);
        };
        layout.Controls.Add(steerText, 0, 1);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill };
        var steer = Button("Steer selected task");
        var cancel = Button("Cancel selected task");
        var openBoard = Button("Open Kanban board");
        var agents = Button("Agents and models…");
        agents.Click += (_, _) => new AgentCatalogueForm(widget).Show(this);
        var paths = Button("Project paths and writers…");
        var results = Button("View selected result…");
        results.Click += (_, _) => {
            if (activity.SelectedRows.Count > 0 && activity.SelectedRows[0].Tag is string taskId)
                new TaskEvidenceForm(widget, taskId).Show(this);
        };
        paths.Click += (_, _) => new ProjectPathsForm(widget).Show(this);
        steer.Click += async (_, _) => await SteerAsync();
        cancel.Click += async (_, _) => await CancelAsync();
        openBoard.Click += (_, _) => {
            if (board is null || board.IsDisposed) board = new KanbanBoardForm(api, sync);
            board.Render(sync.Current, force: true);
            board.Show(this);
            board.BringToFront();
        };
        buttons.Controls.Add(steer);
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(openBoard);
        buttons.Controls.Add(agents);
        buttons.Controls.Add(paths);
        buttons.Controls.Add(results);
        layout.Controls.Add(buttons, 0, 2);
        page.Controls.Add(layout);
        return page;
    }

    private TabPage ContentPage()
    {
        var page = Page("Content");
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4 };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 45));
        content.Columns.Add("source", "Configured content");
        content.Columns.Add("reference", "Path / location");
        content.SelectionChanged += (_, _) =>
        {
            if (content.SelectedRows.Count > 0 && content.SelectedRows[0].Tag is string id)
                reference.Text = id;
        };
        layout.Controls.Add(content, 0, 0);
        layout.Controls.Add(reference, 0, 1);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill };
        foreach (var verb in new[] { "open", "show", "where" })
        {
            var button = Button(char.ToUpperInvariant(verb[0]) + verb[1..]);
            button.Click += async (_, _) => await NavigateAsync(verb);
            buttons.Controls.Add(button);
        }
        layout.Controls.Add(buttons, 0, 2);
        layout.Controls.Add(new Label { Dock = DockStyle.Fill, AutoSize = false,
            Text = "Only Core-registered content is listed. Opening uses a configured handler and Companion access settings; task result IDs are not assumed to be files.",
            ForeColor = Color.FromArgb(176, 197, 220) }, 0, 3);
        page.Controls.Add(layout);
        return page;
    }

    private TabPage IntegrationsPage()
    {
        var page = Page("Integrations");
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2 };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 65));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 35));
        integrations.Columns.Add("name", "Integration / component");
        integrations.Columns.Add("depth", "Type");
        integrations.Columns.Add("version", "Version");
        integrations.Columns.Add("enabled", "Enabled");
        integrations.SelectionChanged += (_, _) => RenderIntegrationDetail();
        layout.Controls.Add(integrations, 0, 0);
        StyleText(integrationDetail);
        layout.Controls.Add(integrationDetail, 0, 1);
        page.Controls.Add(layout);
        return page;
    }

    private TabPage SettingsPage()
    {
        var page = Page("Settings");
        settingsPage = page;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 6, ColumnCount = 1 };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 210));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 48));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 52));
        layout.Controls.Add(settingsState, 0, 0);
        var editor = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4, RowCount = 5 };
        editor.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 155));
        editor.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        editor.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 160));
        editor.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        for (var row = 0; row < 5; row++) editor.RowStyles.Add(new RowStyle(SizeType.Percent, 20));
        editor.Controls.Add(SettingsLabel("Provider"), 0, 0);
        editor.Controls.Add(dialogueBackend, 1, 0);
        editor.Controls.Add(SettingsLabel("Model"), 2, 0);
        editor.Controls.Add(dialogueModel, 3, 0);
        editor.Controls.Add(SettingsLabel("LM Studio folder"), 0, 1);
        editor.Controls.Add(dialogueModelFolder, 1, 1);
        editor.SetColumnSpan(dialogueModelFolder, 2);
        var scanModels = Button("Scan models");
        scanModels.Click += async (_, _) => await ScanModelsAsync();
        editor.Controls.Add(scanModels, 3, 1);
        editor.Controls.Add(SettingsLabel("Endpoint"), 0, 2);
        editor.Controls.Add(dialogueEndpoint, 1, 2);
        editor.SetColumnSpan(dialogueEndpoint, 3);
        editor.Controls.Add(SettingsLabel("Timeout (s)"), 0, 3);
        editor.Controls.Add(dialogueTimeout, 1, 3);
        editor.Controls.Add(SettingsLabel("Workers"), 2, 3);
        editor.Controls.Add(workerCount, 3, 3);
        editor.Controls.Add(SettingsLabel("Context (chars)"), 0, 4);
        editor.Controls.Add(contextLimit, 1, 4);
        editor.Controls.Add(SettingsLabel("characters"), 2, 4);
        layout.Controls.Add(editor, 0, 1);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight };
        var save = Button("Save for Core restart");
        save.Click += async (_, _) => await SaveRuntimeSettingsAsync();
        var discard = Button("Discard draft");
        discard.Click += (_, _) => { settingsDirty = false; loadedSettingsRevision = -1;
            RenderSettings(sync.Current); };
        actions.Controls.Add(save);
        actions.Controls.Add(discard);
        layout.Controls.Add(actions, 0, 2);
        StyleText(settingsText);
        layout.Controls.Add(settingsText, 0, 3);
        layout.Controls.Add(technical, 0, 4);
        permissions.Columns.Add("scope", "Permission / resource scope");
        permissions.Columns.Add("device", "Device / project");
        permissions.Columns.Add("status", "Status");
        permissions.Columns.Add("expires", "Expires");
        layout.Controls.Add(permissions, 0, 5);
        page.Controls.Add(layout);
        return page;
    }

    private static Label SettingsLabel(string text) => new() { Text = text, Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft };

    private void MarkSettingsDirty()
    {
        if (settingsLoading) return;
        settingsDirty = true;
        dialogueModel.Enabled = dialogueEndpoint.Enabled =
            sync.Current.Settings?.DialogueManaged != true && dialogueBackend.Text == "openai-compatible";
        settingsState.Text = "Unsaved draft · Save to validate with Core; changes activate after Core restart.";
    }

    private sealed record LocalModelOption(string Key, string Name, bool Vision)
    {
        public override string ToString() => $"{Name} ({Key})" + (Vision ? " · vision" : "");
    }

    private async Task ScanModelsAsync()
    {
        if (sync.Current.Settings?.DialogueManaged == true)
        { actionStatus.Text = "Model and projector paths are configured in the llama.cpp startup JSON."; return; }
        var folder = dialogueModelFolder.Text.Trim();
        if (folder.Length == 0) { actionStatus.Text = "Enter the LM Studio models folder first."; return; }
        await RunActionAsync(async () =>
        {
            var response = await api.PostAsync("/api/v1/models/scan", new { folder }, default);
            var previous = dialogueModel.SelectedItem is LocalModelOption selected
                ? selected.Key : dialogueModel.Text.Trim();
            settingsLoading = true;
            try
            {
                dialogueModel.Items.Clear();
                foreach (var item in response.GetProperty("models").EnumerateArray())
                {
                    var option = new LocalModelOption(
                        item.GetProperty("model_key").GetString() ?? "",
                        item.GetProperty("display_name").GetString() ?? "Model",
                        item.GetProperty("vision").GetBoolean());
                    dialogueModel.Items.Add(option);
                    if (option.Key == previous) dialogueModel.SelectedItem = option;
                }
                if (dialogueModel.SelectedItem is null) dialogueModel.Text = previous;
            }
            finally { settingsLoading = false; }
            var count = response.GetProperty("count").GetInt32();
            if (count > 0)
            {
                if (dialogueBackend.Text == "deterministic")
                    dialogueBackend.SelectedItem = "openai-compatible";
                if (string.IsNullOrWhiteSpace(dialogueEndpoint.Text))
                    dialogueEndpoint.Text = "http://127.0.0.1:1234/v1";
                MarkSettingsDirty();
            }
            actionStatus.Text = count == 0
                ? "No indexed GGUF models found. Select the directory configured in LM Studio's My Models tab."
                : $"Found {count} LM Studio models. Choose one, then save and restart Core.";
        }, "");
    }

    private async Task SaveRuntimeSettingsAsync()
    {
        var settings = sync.Current.Settings;
        if (settings is null) { actionStatus.Text = "Core settings are not available."; return; }
        await RunActionAsync(async () =>
        {
            var request = FullAppProjection.SettingsUpdate(loadedSettingsRevision,
                dialogueBackend.Text,
                dialogueModel.SelectedItem is LocalModelOption selected ? selected.Key : dialogueModel.Text,
                dialogueEndpoint.Text, (double)dialogueTimeout.Value,
                (int)workerCount.Value, (int)contextLimit.Value, dialogueModelFolder.Text);
            var saved = await api.PostAsync("/api/v1/settings", request, default);
            settingsDirty = false;
            loadedSettingsRevision = -1;
            await RefreshAsync();
            actionStatus.Text = saved.GetProperty("restart_required").GetBoolean()
                ? "Runtime settings saved. Restart Core to activate them."
                : "Runtime settings already match the active Core configuration.";
        }, "");
    }

    private async Task RefreshAsync()
    {
        if (polling) return;
        polling = true;
        try
        {
            Render(await sync.RefreshAsync());
            if (sync.Current.Companion.Connected)
            {
                try
                {
                    var avatar = await api.GetAsync("/api/v1/companion", default);
                    avatarStatus.Text = avatar.GetProperty("visible").GetBoolean()
                        ? $"3D companion connected · {(avatar.TryGetProperty("renderer_state", out var pose) ? pose.GetString() : avatar.GetProperty("state").GetString())}"
                        : avatar.GetProperty("running").GetBoolean()
                            ? "3D companion is loading / connecting…"
                            : avatar.GetProperty("error").GetString() ?? "3D companion is offline.";
                }
                catch (Exception error) when (error is HttpRequestException or OperationCanceledException or IOException)
                { avatarStatus.Text = "3D companion is unavailable; retrying…"; }
            }
            else avatarStatus.Text = "Waiting for Core…";
        }
        finally { polling = false; }
    }

    private void Render(FullAppSnapshot snapshot)
    {
        connection.Text = snapshot.Companion.Connected
            ? $"{snapshot.Companion.StatusLabel} · {snapshot.Companion.DialogueModel} · {snapshot.Companion.ActiveWorkers} runs"
            : "Reconnecting…";
        if (!string.IsNullOrWhiteSpace(snapshot.Error))
        { actionStatus.Text = snapshot.Error; lastConnectionError = snapshot.Error; }
        else if (lastConnectionError.Length > 0)
        {
            if (actionStatus.Text == lastConnectionError) actionStatus.Text = "Connected to SORA.";
            lastConnectionError = "";
        }
        else if (!actionInProgress && DateTimeOffset.UtcNow >= actionStatusUntil)
            actionStatus.Text = snapshot.Companion.StatusLabel;
        RenderChat(snapshot);
        RenderActivity(snapshot);
        RenderContent(snapshot);
        RenderIntegrations(snapshot);
        RenderSettings(snapshot);
        if (board is not null && !board.IsDisposed) board.Render(snapshot);
    }

    private void RenderChat(FullAppSnapshot snapshot)
    {
        var rendered = string.Join("\n\n", snapshot.Companion.Messages.Select(item =>
            $"{(item.Role == "assistant" ? "SORA" : "You")} · {item.CreatedAt.LocalDateTime:g}\n{ChatText.Plain(item.Content, item.Role == "assistant")}"));
        if (rendered == lastTranscript) return;
        lastTranscript = rendered;
        transcript.Text = rendered;
        transcript.SelectionStart = transcript.TextLength;
        transcript.ScrollToCaret();
    }

    private void RenderActivity(FullAppSnapshot snapshot)
    {
        var signature = string.Join('|', snapshot.Tasks.Select(item =>
            item.Id + item.Status + item.Backend + item.UpdatedAt + item.Description +
            item.ResultReference)) + preferences.ShowTechnicalDetail;
        if (signature == lastActivity) return;
        lastActivity = signature;
        var selected = activity.SelectedRows.Count > 0 ? activity.SelectedRows[0].Tag as string : null;
        activity.Rows.Clear();
        foreach (var task in snapshot.Tasks)
        {
            var label = Clip(task.Description, 140);
            if (preferences.ShowTechnicalDetail)
                label += $"\n{task.Id}" + (task.ResultReference is null ? "" : $" · result {task.ResultReference}");
            var row = activity.Rows[activity.Rows.Add(label, task.Status,
                task.Backend, task.SelectionLabel, task.ProjectLabel,
                task.UpdatedAt.LocalDateTime.ToString("g"))];
            row.Tag = task.Id;
            row.Cells[3].ToolTipText = "Requested selection, not independent execution verification: " + task.SelectionLabel;
            row.Cells[4].ToolTipText = task.ProjectLabel;
            row.Cells[0].ToolTipText = label;
            if (task.Id == selected) row.Selected = true;
        }
    }

    private void RenderContent(FullAppSnapshot snapshot)
    {
        var signature = string.Join('|', snapshot.Content.Select(item => item.Id + item.Path));
        if (signature == lastContent) return;
        lastContent = signature;
        content.Rows.Clear();
        foreach (var item in snapshot.Content)
        {
            var row = content.Rows[content.Rows.Add($"{item.Label} · {item.Kind}", item.Path)];
            row.Tag = item.Id;
        }
    }

    private void RenderIntegrations(FullAppSnapshot snapshot)
    {
        var signature = string.Join('|', snapshot.Extensions.Select(item =>
            item.Id + item.Enabled + item.Version)) + string.Join('|', snapshot.ActiveExtensions) +
            string.Join('|', snapshot.Companion.Providers.Select(item => item.Id + item.Available));
        if (signature == lastIntegrations) return;
        lastIntegrations = signature;
        integrations.Rows.Clear();
        foreach (var extension in snapshot.Extensions)
        {
            var row = integrations.Rows[integrations.Rows.Add(extension.Id, extension.Depth,
                extension.Version, extension.Enabled ? "Yes" : "No")];
            row.Tag = extension.Id;
        }
        RenderIntegrationDetail();
    }

    private void RenderIntegrationDetail()
    {
        var id = integrations.SelectedRows.Count > 0 ? integrations.SelectedRows[0].Tag as string : null;
        var extension = sync.Current.Extensions.FirstOrDefault(item => item.Id == id);
        var providers = "Specialist providers: " + string.Join(", ",
            sync.Current.Companion.Providers.Select(item =>
                $"{item.Name} ({(item.Available ? "available" : "unavailable")})"));
        if (extension is null)
        {
            integrationDetail.Text = "Select an integration to inspect its declared capabilities and required grants.\n\n" + providers;
            return;
        }
        integrationDetail.Text = $"{extension.Id} · {extension.Depth} · v{extension.Version}\n" +
            $"Enabled: {extension.Enabled}\n" +
            $"Active for this owner: {sync.Current.ActiveExtensions.Contains(extension.Id)}\n" +
            $"Capabilities: {string.Join(", ", extension.Capabilities)}\n" +
            $"Required grants: {string.Join(", ", extension.RequiredGrants)}\n\n" +
            providers + "\n\n" +
            "Configuration values and credential references are not shown. Extension management is a separate P15.10 gate.";
    }

    private void RenderSettings(FullAppSnapshot snapshot)
    {
        var settings = snapshot.Settings;
        if (settings is null) return;
        if (settings.UnifiedSettings.ValueKind == JsonValueKind.Object && settingsPage is not null)
        {
            if (modelSettingsEditor is null)
            {
                foreach (Control control in settingsPage.Controls) control.Visible = false;
                modelSettingsEditor = new ModelSettingsEditor(api,
                    () => sync.Current.Companion.Connected && sync.Current.Error.Length == 0);
                settingsPage.Controls.Add(modelSettingsEditor);
            }
            modelSettingsEditor.Visible = true;
            modelSettingsEditor.BringToFront();
            modelSettingsEditor.Render(settings.UnifiedSettings);
            return;
        }
        if (loadedManagedMode != settings.DialogueManaged) settingsDirty = false;
        if (!settingsDirty && (loadedSettingsRevision != settings.SettingsRevision ||
            loadedManagedMode != settings.DialogueManaged))
        {
            settingsLoading = true;
            try
            {
                var draft = settings.Pending ?? new FullEditableRuntimeSettings(settings.DialogueBackend,
                    settings.DialogueModel, settings.DialogueBaseUrl, settings.DialogueTimeoutSeconds,
                    settings.WorkerCount, settings.ContextMaxChars);
                dialogueBackend.SelectedItem = draft.DialogueBackend;
                dialogueModel.Text = draft.DialogueModel ?? "";
                dialogueModelFolder.Text = draft.DialogueModelFolder ?? settings.DialogueModelFolder ?? "";
                dialogueEndpoint.Text = draft.DialogueBaseUrl ?? "";
                dialogueTimeout.Value = Math.Clamp((decimal)draft.DialogueTimeoutSeconds,
                    dialogueTimeout.Minimum, dialogueTimeout.Maximum);
                workerCount.Value = Math.Clamp(draft.WorkerCount, (int)workerCount.Minimum,
                    (int)workerCount.Maximum);
                contextLimit.Value = Math.Clamp(draft.ContextMaxChars, (int)contextLimit.Minimum,
                    (int)contextLimit.Maximum);
                dialogueModel.Enabled = dialogueEndpoint.Enabled = draft.DialogueBackend == "openai-compatible";
                loadedSettingsRevision = settings.SettingsRevision;
                loadedManagedMode = settings.DialogueManaged;
            }
            finally { settingsLoading = false; }
        }
        if (!settingsDirty) settingsState.Text = settings.RestartRequired
            ? $"Saved revision {settings.SettingsRevision}; Core is running revision {settings.ActiveSettingsRevision}. Restart Core to activate."
            : $"Core settings active · revision {settings.ActiveSettingsRevision}.";
        dialogueBackend.Enabled = dialogueModelFolder.Enabled = !settings.DialogueManaged;
        dialogueModel.Enabled = dialogueEndpoint.Enabled =
            !settings.DialogueManaged && dialogueBackend.Text == "openai-compatible";
        if (settings.DialogueManaged && !settingsDirty)
        {
            settingsState.Text += " Model/projector managed by llama.cpp startup configuration.";
        }
        var text = "Protected setup (view only; credentials and grants are never saved in app preferences)\n\n" +
            $"Owner: {settings.Owner}    Project: {settings.Project}\n" +
            $"API key: {(settings.DialogueKeyConfigured ? "configured (redacted)" : "not configured")}\n" +
            $"Other secrets: {settings.SecretCount} configured (redacted)\n" +
            $"Managed coding workspace: {(settings.CodingWorkspaceConfigured ? "configured" : "not configured")}\n" +
            $"Content scopes: {string.Join("; ", settings.ContentRoots.DefaultIfEmpty("none"))}\n" +
            $"Editor scopes: {string.Join("; ", settings.EditorRoots.DefaultIfEmpty("none"))}\n" +
            $"Configured content handlers: {string.Join("; ", settings.ContentHandlers.DefaultIfEmpty("none"))}\n\n" +
            "Choose the folder configured in LM Studio's My Models tab, Scan models, then Save. " +
            "LM Studio's local server and JIT loading (or a preloaded model) are required.\n" +
            "Provider API keys and scope roots remain trusted Core setup inputs. Local access is controlled by Companion access settings; remote access remains separate.\n" +
            $"Permission records: {snapshot.PermissionTotal}" +
            (snapshot.PermissionsTruncated ? " (showing newest 100)" : "") +
            "\nPermission IDs and approval IDs are never shown here.";
        if (text != lastSettings) { lastSettings = text; settingsText.Text = text; }
        permissions.Rows.Clear();
        foreach (var item in snapshot.Permissions)
        {
            var scope = $"{item.Operation}: {item.Resource}";
            var usage = item.MaxUses is null ? "" : $" · {item.UsedCount}/{item.MaxUses} uses";
            permissions.Rows.Add(scope, item.Device + (item.Project is null ? "" : $" / {item.Project}"),
                item.Status + usage, item.ExpiresAt.LocalDateTime.ToString("g"));
        }
    }

    private async Task SendDialogueAsync()
    {
        var text = composer.Text.Trim();
        if (text.Length == 0 || actionInProgress) return;
        var path = chatFile.Text.Trim();
        await RunActionAsync(async () => {
            var requestId = Guid.NewGuid().ToString("N");
            dialogueRequestId = requestId;
            stopResponse.Enabled = true;
            composer.Clear();
            chatFile.Clear();
            try
            {
                if (path.Length == 0) await widget.DialogueAsync(text, requestId: requestId);
                else await widget.DialogueWithFilesAsync(text, [path], requestId: requestId);
            }
            catch
            {
                if (composer.Text.Length == 0) composer.Text = text;
                if (chatFile.Text.Length == 0) chatFile.Text = path;
                throw;
            }
            finally { dialogueRequestId = null; stopResponse.Enabled = false; }
            await RefreshAsync();
        },
            "Response received.");
    }

    private void BrowseChatFile()
    {
        try
        {
            using var dialog = new OpenFileDialog { Title = "Attach a file to SORA",
                CheckFileExists = true, AutoUpgradeEnabled = false, RestoreDirectory = true };
            if (dialog.ShowDialog(this) == DialogResult.OK) chatFile.Text = dialog.FileName;
        }
        catch (Exception error)
        {
            actionStatus.Text = $"File picker unavailable: {error.Message}";
        }
    }

    private async Task LookAtScreenAsync()
    {
        var text = composer.Text.Trim();
        await RunActionAsync(async () => {
            dialogueRequestId = Guid.NewGuid().ToString("N");
            stopResponse.Enabled = true;
            try
            {
                await widget.DesktopDialogueAsync(text, requestId: dialogueRequestId);
                if (composer.Text.Trim() == text) composer.Clear();
            }
            finally { dialogueRequestId = null; stopResponse.Enabled = false; }
            await RefreshAsync();
        }, "SORA viewed the current screen.");
    }

    private async Task StopResponseAsync()
    {
        var requestId = dialogueRequestId;
        if (requestId is null) return;
        stopResponse.Enabled = false;
        actionStatus.Text = "Stopping response… Already-dispatched actions are not undone.";
        try
        {
            var result = await widget.CancelDialogueAsync(requestId);
            if (dialogueRequestId == requestId && result.GetProperty("state").GetString() == "already-finishing")
                actionStatus.Text = "Response is already finishing; check the transcript.";
        }
        catch (Exception error)
        {
            if (dialogueRequestId == requestId)
            { actionStatus.Text = "Stop not confirmed: " + error.Message; stopResponse.Enabled = true; }
        }
    }

    private async Task DelegateAsync()
    {
        var text = composer.Text.Trim();
        if (text.Length == 0) return;
        using var selector = new AgentCatalogueForm(widget, text);
        if (selector.ShowDialog(this) != DialogResult.OK) return;
        await RunActionAsync(async () => { composer.Clear();
            tabs.SelectedIndex = 1; await RefreshAsync(); }, "Delegated task started.");
    }

    private async Task PlanFromChatAsync()
    {
        var text = composer.Text.Trim();
        if (text.Length == 0) return;
        await RunActionAsync(async () => {
            await api.PostAsync("/api/v1/board/cards", new {
                intent = text, idempotency_key = $"board-plan-{Guid.NewGuid()}"
            }, default);
            composer.Clear();
            await RefreshAsync();
        }, "Saved to TODO. No specialist was started.");
    }

    private async Task SteerAsync()
    {
        var id = activity.SelectedRows.Count > 0 ? activity.SelectedRows[0].Tag as string : null;
        var instruction = steerText.Text.Trim();
        if (id is null || instruction.Length == 0) { actionStatus.Text = "Select a task and enter an instruction."; return; }
        if (!CanControl(id)) { actionStatus.Text = "This task is no longer active."; return; }
        if (MessageBox.Show(this, "Send this instruction to the selected task?", "Steer task",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        await RefreshAsync();
        if (!CanControl(id)) { actionStatus.Text = "Task completed before steering was sent."; return; }
        await RunActionAsync(async () => { await api.PostAsync(FullAppProjection.TaskPath(id, "steer"),
            new { instruction }, default); steerText.Clear(); await RefreshAsync(); }, "Task instruction sent.");
    }

    private async Task CancelAsync()
    {
        var id = activity.SelectedRows.Count > 0 ? activity.SelectedRows[0].Tag as string : null;
        if (id is null) { actionStatus.Text = "Select a task to cancel."; return; }
        if (!CanControl(id)) { actionStatus.Text = "This task is no longer active."; return; }
        if (MessageBox.Show(this, "Cancel the selected task?", "Cancel task",
                MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        await RefreshAsync();
        if (!CanControl(id)) { actionStatus.Text = "Task completed before cancellation was sent."; return; }
        await RunActionAsync(async () => { await api.PostAsync(FullAppProjection.TaskPath(id, "cancel"),
            new { }, default); await RefreshAsync(); }, "Task cancellation requested.");
    }

    private async Task NavigateAsync(string verb)
    {
        var id = reference.Text.Trim();
        if (!FullAppProjection.IsSafeIdentifier(id))
        { actionStatus.Text = "Select or enter an exact content reference."; return; }
        await RunActionAsync(async () =>
        {
            var result = await api.PostAsync("/api/v1/content/navigate",
                FullAppProjection.NavigationRequest(id, verb), default);
            actionStatus.Text = result.TryGetProperty("reason", out var reason) ? reason.GetString() :
                "Core handled the content navigation request.";
        }, "");
    }

    private bool CanControl(string id) => sync.Current.Tasks.Any(task => task.Id == id &&
        task.Status is not ("planned" or "completed" or "failed" or "cancelled"));

    private bool actionInProgress;

    private async Task RunActionAsync(Func<Task> action, string success)
    {
        if (actionInProgress) { actionStatus.Text = "Please wait for the current request to finish."; return; }
        actionInProgress = true;
        foreach (var button in chatActions) button.Enabled = false;
        actionStatus.Text = "Working…";
        try { await action(); if (success.Length > 0) actionStatus.Text = success; }
        catch (SoraRequestException error) when (error.Code == "DIALOGUE_CANCELLED")
        { await RefreshAsync(); actionStatus.Text = "Response stopped. Draft preserved; dispatched actions are not undone."; }
        catch (Exception error) { actionStatus.Text = error.Message; }
        finally
        {
            actionInProgress = false;
            actionStatusUntil = DateTimeOffset.UtcNow.AddSeconds(8);
            foreach (var button in chatActions) button.Enabled = true;
        }
    }

    private void SavePreferences()
    {
        preferences = new(technical.Checked, tabs.SelectedIndex);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(settingsFile))!);
        var temporary = settingsFile + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(preferences));
        File.Move(temporary, settingsFile, true);
    }

    private static FullAppPreferences LoadPreferences(string path)
    {
        try { return JsonSerializer.Deserialize<FullAppPreferences>(File.ReadAllText(path)) ?? new(); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException)
        { return new(); }
    }

    private static TabPage Page(string name) => new(name) { Padding = new Padding(10),
        BackColor = Color.FromArgb(25, 36, 53), ForeColor = Color.FromArgb(237, 243, 251) };
    private static Button Button(string label) => new() { Text = label, AutoSize = true, Height = 36,
        BackColor = Color.FromArgb(48, 83, 129), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
    private static DataGridView Grid() => new() { Dock = DockStyle.Fill, ReadOnly = true,
        MultiSelect = false, SelectionMode = DataGridViewSelectionMode.FullRowSelect,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, AllowUserToAddRows = false,
        AllowUserToDeleteRows = false, RowHeadersVisible = false, BackgroundColor = Color.FromArgb(30, 43, 62),
        ForeColor = Color.Black };
    private static void StyleText(RichTextBox box)
    { box.BackColor = Color.FromArgb(31, 44, 63); box.ForeColor = Color.FromArgb(237, 243, 251);
      box.BorderStyle = BorderStyle.None; box.Font = new Font("Segoe UI", 10.5f); }
    private static string Clip(string value, int max) => value.Length <= max ? value : value[..max] + "…";
}
