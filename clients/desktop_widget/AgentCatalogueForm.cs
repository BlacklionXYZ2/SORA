using System.Drawing;
using System.Text.Json;

namespace Sora.DesktopWidget;

/// <summary>One shared, explicit selector; metadata browsing never starts specialist work.</summary>
public sealed class AgentCatalogueForm : Form
{
    private sealed record Choice(string Id, string Label, JsonElement? Data = null)
    { public override string ToString() => Label; }
    private readonly IAgentWorkflow sync;
    private readonly string? intent;
    private readonly string? referenceId;
    private readonly string? plannedTaskId;
    private readonly bool hosted, editableTask;
    private readonly Func<bool> canUseCore;
    private bool shuttingDown, resourcesDisposed;
    private readonly TextBox taskText = new() { Dock = DockStyle.Fill, Multiline = true, MaxLength = 8000,
        ScrollBars = ScrollBars.Vertical, AccessibleName = "Specialist task draft",
        PlaceholderText = "Describe the work for an agent. This is separate from Chat." };
    private readonly Button purposes = new() { Text = "Edit model purposes…", AutoSize = true };
    private readonly Button newTask = new() { Text = "New task", AutoSize = true };
    private readonly ComboBox provider = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox model = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox effort = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox project = new() { Dock = DockStyle.Fill,
        PlaceholderText = "Task project directory, or blank for the saved preference" };
    private readonly ComboBox workspaceMode = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly RichTextBox detail = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false };
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoEllipsis = true, Text = "Reading cached catalogue…" };
    private readonly Button refresh = new() { Text = "Refresh models", AutoSize = true };
    private readonly Button readCached = new() { Text = "Read cached list", AutoSize = true };
    private readonly Button start = new() { Text = "Start specialist task", AutoSize = true, Enabled = false };
    private readonly Button browseProject = new() { Text = "Browse…", Dock = DockStyle.Fill };
    private readonly CancellationTokenSource lifetime = new();
    private bool loading;
    private bool busy;
    private bool submitting;
    private bool catalogueAllowsAutomatic;
    private bool catalogueCurrent, wasAvailable;
    private TaskSubmissionDraft submission = new();
    private string? currentEpoch;
    public bool HasPendingWork => busy;
    private string? CurrentIntent => editableTask ? taskText.Text.Trim() : intent;
    public JsonElement? Receipt { get; private set; }

    public AgentCatalogueForm(IAgentWorkflow sync, string? intent = null, string? referenceId = null,
        string? plannedTaskId = null, bool hosted = false, bool editableTask = false, Func<bool>? canUseCore = null)
    {
        SuspendLayout();
        this.sync = sync; this.intent = intent; this.referenceId = referenceId;
        this.plannedTaskId = plannedTaskId;
        this.hosted = hosted; this.editableTask = editableTask; this.canUseCore = canUseCore ?? (() => true);
        Text = editableTask ? "SORA · Agents and delegation" : intent is null ? "SORA · Agents and models" : "SORA · Delegate to a specialist";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10);
        StartPosition = FormStartPosition.CenterParent;
        Size = new Size(780, 620); MinimumSize = new Size(580, 480);
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14),
            ColumnCount = 2, RowCount = 10 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (var i = 0; i < 5; i++) layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, editableTask ? 90 : 0));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        AddRow(layout, "Agent", provider, 0); AddRow(layout, "Model", model, 1);
        AddRow(layout, "Effort", effort, 2);
        var projectRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        projectRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        projectRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
        browseProject.Click += (_, _) => {
            using var folder = new FolderBrowserDialog { Description = "Select the actual task project" };
            if (Directory.Exists(project.Text)) folder.SelectedPath = project.Text;
            if (folder.ShowDialog(this) == DialogResult.OK) project.Text = folder.SelectedPath;
        };
        projectRow.Controls.Add(project, 0, 0); projectRow.Controls.Add(browseProject, 1, 0);
        AddRow(layout, "Project", projectRow, 3); AddRow(layout, "Mode", workspaceMode, 4);
        project.AccessibleName = "Task project directory";
        workspaceMode.AccessibleName = "Task project mode";
        workspaceMode.Items.AddRange(new object[] { "Saved / infer from task", "direct", "isolated", "read-only" });
        workspaceMode.SelectedIndex = 0;
        projectRow.Visible = workspaceMode.Visible = intent is not null || editableTask;
        if (intent is null && !editableTask) {
            layout.GetControlFromPosition(0, 3)!.Visible = false;
            layout.GetControlFromPosition(0, 4)!.Visible = false;
            layout.RowStyles[3].Height = layout.RowStyles[4].Height = 0;
        }
        provider.AccessibleName = "Specialist agent"; model.AccessibleName = "Specialist model";
        effort.AccessibleName = "Specialist reasoning effort";
        var notice = new Label { Dock = DockStyle.Fill, AutoSize = true, Margin = new Padding(3, 5, 3, 8),
            Text = "Listing does not verify model access. Refresh runs metadata probes only; Hermes creates an empty ACP session (no prompt or MCP startup). This does not change SORA's local dialogue model." };
        if (editableTask) { AddRow(layout, "Task", taskText, 5); taskText.Text = intent ?? ""; }
        layout.Controls.Add(notice, 0, 6); layout.SetColumnSpan(notice, 2);
        detail.AccessibleName = "Specialist catalogue details";
        layout.Controls.Add(detail, 0, 7); layout.SetColumnSpan(detail, 2);
        layout.Controls.Add(status, 0, 8); layout.SetColumnSpan(status, 2);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft };
        var close = new Button { Text = hosted ? "Hide" : intent is null ? "Close" : "Cancel", AutoSize = true,
            DialogResult = DialogResult.Cancel };
        close.Click += (_, _) => Close();
        buttons.Controls.Add(close);
        if (intent is not null || editableTask) buttons.Controls.Add(start);
        if (editableTask) buttons.Controls.Add(newTask);
        newTask.Click += (_, _) => {
            if (busy || submission.Attempted && !submission.Confirmed) return;
            submission = new(); Receipt = null; taskText.Clear(); status.Text = "New task draft. Nothing submitted."; RenderDetail();
        };
        taskText.TextChanged += (_, _) => RenderDetail();
        buttons.Controls.Add(purposes);
        purposes.Click += async (_, _) => {
            if (busy || !this.canUseCore() || provider.SelectedItem is not Choice selected) return;
            string agent = selected.Id switch { "codex-app-server" => "codex", "hermes-acp" => "hermes", _ => selected.Id };
            if (agent is not ("codex" or "hermes" or "antigravity")) { status.Text = "Select Codex, Hermes or Antigravity first."; return; }
            busy = true; start.Enabled = refresh.Enabled = false;
            try {
                var settings = await sync.SettingsAsync(lifetime.Token);
                var field = settings.GetProperty("fields").EnumerateArray()
                    .First(item => item.GetProperty("key").GetString() == $"agents.{agent}.model_choices");
                var ids = selected.Data!.Value.GetProperty("models").EnumerateArray()
                    .Select(item => Get(item, "id"));
                using var form = new ModelPurposeForm(agent, field.GetProperty("value"), ids,
                    async draft => await sync.SaveModelPurposesAsync(settings.GetProperty("settings_version").GetInt32(),
                        settings.GetProperty("settings_revision").GetInt32(), agent, draft, lifetime.Token));
                if (form.ShowDialog(this) != DialogResult.OK) return;
                status.Text = "Model purposes saved. No inference run; preferred model unchanged.";
            } catch (Exception error) { if (!IsDisposed) status.Text = "Purposes were not saved: " + error.Message; }
            finally { busy = false; if (!IsDisposed) { refresh.Enabled = true; RenderDetail(); } }
            if (!IsDisposed) await LoadAsync(false);
        };
        buttons.Controls.Add(refresh); buttons.Controls.Add(readCached);
        buttons.AutoSize = true;
        layout.RowStyles[9].SizeType = SizeType.AutoSize;
        layout.Controls.Add(buttons, 0, 9); layout.SetColumnSpan(buttons, 2);
        Controls.Add(layout); CancelButton = close;
        provider.SelectedIndexChanged += (_, _) => { if (!loading) LoadModels(); };
        model.SelectedIndexChanged += (_, _) => { if (!loading) LoadEfforts(); };
        effort.SelectedIndexChanged += (_, _) => RenderDetail();
        refresh.Click += async (_, _) => await LoadAsync(true);
        readCached.Click += async (_, _) => await LoadAsync(false);
        start.Click += async (_, _) => await StartAsync();
        Shown += async (_, _) => { TopMost = Owner?.TopMost == true; BringToFront(); await LoadAsync(false); };
        FormClosing += (_, args) => {
            if (submitting) { args.Cancel = true; return; }
            if (hosted && !shuttingDown && args.CloseReason == CloseReason.UserClosing) { args.Cancel = true; Hide(); }
        };
        RenderDetail();
        ResumeLayout(true);
    }

    private static void AddRow(TableLayoutPanel panel, string text, Control control, int row)
    {
        panel.Controls.Add(new Label { Text = text, Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft }, 0, row);
        panel.Controls.Add(control, 1, row);
    }

    private async Task LoadAsync(bool probe)
    {
        if (busy || submission.Attempted && !submission.Confirmed) return;
        if (!canUseCore()) { UpdateHostAvailability(); return; }
        busy = true; refresh.Enabled = false; start.Enabled = false;
        status.Text = probe ? "Discovering models; no inference…" : "Reading cached catalogue…";
        var oldProvider = (provider.SelectedItem as Choice)?.Id;
        var oldModel = (model.SelectedItem as Choice)?.Id;
        var oldEffort = (effort.SelectedItem as Choice)?.Id;
        try
        {
            var catalogue = await sync.AgentCatalogueAsync(probe, lifetime.Token);
            if (IsDisposed) return;
            catalogueCurrent = true;
            catalogueAllowsAutomatic = catalogue.GetProperty("providers").EnumerateArray().Any(entry =>
                !entry.TryGetProperty("enabled", out var value) || value.ValueKind == JsonValueKind.True);
            loading = true; provider.Items.Clear();
            provider.Items.Add(new Choice("", "Automatic routing (configured defaults)"));
            foreach (var entry in catalogue.GetProperty("providers").EnumerateArray())
                provider.Items.Add(new Choice(Get(entry, "provider"),
                    $"{Get(entry, "display_name")} · {Get(entry, "state").Replace('_', ' ')}", entry.Clone()));
            var providerIndex = Find(provider, oldProvider);
            provider.SelectedIndex = oldProvider is not null && providerIndex < 0 ? -1 : Math.Max(0, providerIndex);
            loading = false; LoadModels();
            var index = Find(model, oldModel);
            if (oldModel is not null && index < 0) model.SelectedIndex = -1;
            else if (index >= 0) model.SelectedIndex = index;
            var effortIndex = Find(effort, oldEffort);
            if (effortIndex >= 0) effort.SelectedIndex = effortIndex;
            status.Text = oldProvider is not null && providerIndex < 0 ? "Previous agent is no longer listed. Select an agent explicitly." : oldModel is not null && index < 0
                ? "Previous model is no longer listed. Choose a model before starting."
                : probe ? "Metadata refreshed. No specialist task or inference started." : "Cached catalogue loaded. Use Refresh models to discover available entries.";
        }
        catch (OperationCanceledException) { if (!IsDisposed) status.Text = "Catalogue request cancelled."; }
        catch (Exception error) { if (!IsDisposed) status.Text = "Catalogue unavailable: " + error.Message; }
        finally { loading = false; busy = false; if (!IsDisposed) { refresh.Enabled = true; RenderDetail(); } }
    }

    private static int Find(ComboBox combo, string? id)
    {
        if (id is null) return -1;
        for (var i = 0; i < combo.Items.Count; i++) if (combo.Items[i] is Choice choice && choice.Id == id) return i;
        return -1;
    }

    private void LoadModels()
    {
        loading = true; model.Items.Clear();
        model.Items.Add(new Choice("", "Saved preference / configured default"));
        var selected = provider.SelectedItem as Choice;
        if (selected?.Data is JsonElement data)
            foreach (var entry in data.GetProperty("models").EnumerateArray())
                model.Items.Add(new Choice(Get(entry, "id"),
                    $"{Get(entry, "display_name")} [{Get(entry, "id")}]", entry.Clone()));
        model.SelectedIndex = 0; model.Enabled = selected?.Id.Length > 0;
        loading = false; LoadEfforts();
    }

    private void LoadEfforts()
    {
        loading = true; effort.Items.Clear(); effort.Items.Add(new Choice("", "Configured default / model's embedded tier"));
        if ((model.SelectedItem as Choice)?.Data is JsonElement data)
        {
            foreach (var value in data.GetProperty("efforts").EnumerateArray())
                effort.Items.Add(new Choice(value.GetString()!, value.GetString()!));
        }
        effort.SelectedIndex = 0; effort.Enabled = effort.Items.Count > 1;
        if ((model.SelectedItem as Choice)?.Data is JsonElement selected)
        {
            var recommended = Find(effort, Get(selected, "default_effort"));
            if (recommended >= 0) effort.SelectedIndex = recommended;
        }
        loading = false; RenderDetail();
    }

    private void RenderDetail()
    {
        if (IsDisposed || loading) return;
        var selected = provider.SelectedItem as Choice;
        var selectedModel = model.SelectedItem as Choice;
        bool available = canUseCore(), frozen = submission.Attempted;
        provider.Enabled = project.Enabled = workspaceMode.Enabled = browseProject.Enabled = taskText.Enabled = !busy && !frozen;
        model.Enabled = !busy && !frozen && selected?.Id.Length > 0;
        effort.Enabled = !busy && !frozen && effort.Items.Count > 1;
        refresh.Enabled = !busy && available && (!frozen || submission.Confirmed);
        readCached.Enabled = refresh.Enabled;
        purposes.Enabled = !busy && available && (!frozen || submission.Confirmed);
        newTask.Enabled = !busy && (!frozen || submission.Confirmed);
        start.Text = frozen && !submission.Confirmed ? "Retry exact submission" : "Start specialist task";
        start.Enabled = !busy && available && (catalogueCurrent || submission.Attempted) && !submission.Confirmed && selected is not null && selectedModel is not null
            && !string.IsNullOrWhiteSpace(CurrentIntent);
        if (selected?.Data is not JsonElement data)
        { start.Enabled &= catalogueAllowsAutomatic;
            detail.Text = "Automatic routing uses the configured defaults. Select an agent to inspect its model catalogue.\n" +
            (catalogueAllowsAutomatic ? "" : "No enabled specialist is listed; task start is unavailable.\n") +
            "\n" + (CurrentIntent is null ? "No task will be started from this window." : "TASK\n" + CurrentIntent) + ReceiptText(); return; }
        var caps = data.GetProperty("capabilities");
        bool enabled = !data.TryGetProperty("enabled", out var enabledValue) || enabledValue.GetBoolean();
        start.Enabled &= enabled;
        var features = new[] { "filesystem", "worktree_support", "sessions", "resume", "steer", "cancel", "tool_restrictions" }
            .Select(key => $"{key.Replace('_', ' ')}: {(caps.GetProperty(key).GetBoolean() ? "supported" : "not supported")}");
        var modelData = selectedModel?.Data;
        detail.Text = $"{Get(data, "purpose")}\n\nAgent ID: {selected.Id}\nState: {Get(data, "state")}\n" +
            $"Checked: {Get(data, "checked_at", "Not yet")}\nConfigured model: {Get(data, "configured_model", "Provider default")}\n" +
            $"Configured effort: {Get(data, "configured_effort", "Provider default")}\n" +
            $"Enabled in Settings: {enabled}\nSaved preferred model: {Get(data, "preferred_model")}\n" +
            $"Saved preferred effort: {Get(data, "preferred_effort", "configured")}\nModel purpose: {Get(data, "model_purpose")}\n" +
            $"Saved project: {Get(data, "project_root", "None")}\nProject mode: {Get(data, "workspace_mode", "direct")}\nProject boundary: {Get(data, "project_boundary")}\n" +
            $"Saved base ref: {Get(data, "base_ref", "Unavailable")}\nTask deadline: Core configuration; no per-task override in this selector.\n" +
            $"Owner roster (desired, not access verification): {string.Join(", ", data.GetProperty("owner_roster").EnumerateArray().Select(item => item.GetString()))}\n\n" +
            string.Join("\n", features) + "\n\n" + Get(data, "error", "") +
            (modelData is JsonElement md ? $"\nModel ID: {Get(md, "id")}\nPurpose: {Get(md, "purpose", Get(md, "description"))}\nPurpose source: {Get(md, "purpose_source")}\nEmbedded tier: {Get(md, "embedded_effort", "None")}\nModel state: {Get(md, "state", "not checked")}; execution not verified." : "\nSaved preference will be pinned by Core if set; otherwise the harness default is used. Edit preferences in Settings.") +
            (CurrentIntent is null ? "" : "\n\nTASK\n" + CurrentIntent) + ReceiptText();
    }

    private async Task StartAsync()
    {
        var task = CurrentIntent;
        if (busy || !canUseCore() || string.IsNullOrWhiteSpace(task) || submission.Confirmed
            || provider.SelectedItem is not Choice p || model.SelectedItem is not Choice m) return;
        var e = effort.SelectedItem as Choice;
        var selection = new AgentSelection(p.Id.Length == 0 ? null : p.Id,
            m.Id.Length == 0 ? null : m.Id, e?.Id.Length > 0 ? e.Id : null,
            string.IsNullOrWhiteSpace(project.Text) ? null : project.Text.Trim(),
            workspaceMode.SelectedIndex > 0 ? workspaceMode.Text : null);
        var summary = $"Agent: {p.Label}\nModel: {m.Label}\nEffort: {e?.Label}\nProject: {project.Text}\nMode: {workspaceMode.Text}\n\n" +
            (submission.Attempted ? "Retry the same unconfirmed task with the same key? Inspect Activity first if uncertain." : "Start this specialist task?");
        if (MessageBox.Show(this, summary, "Confirm delegation", MessageBoxButtons.YesNo,
            MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
        busy = true; submitting = true; start.Enabled = false; refresh.Enabled = false; provider.Enabled = false;
        model.Enabled = false; effort.Enabled = false; project.Enabled = false;
        workspaceMode.Enabled = browseProject.Enabled = false; status.Text = "Submitting task…";
        try
        {
            var submissionKey = submission.Begin(task, referenceId, selection);
            Receipt = plannedTaskId is null
                ? await sync.DelegateAsync(task, referenceId, lifetime.Token, selection, submissionKey)
                : await sync.StartPlannedAsync(plannedTaskId, task, selection, lifetime.Token);
            submission.Acknowledge();
            submitting = false;
            if (!IsDisposed) {
                if (!hosted) { DialogResult = DialogResult.OK; Close(); }
                else status.Text = "Core acknowledged task " + Get(Receipt.Value, "task_id") + "; execution/result is separate. Open Activity for evidence.";
            }
        }
        catch (SoraRequestException error) when (error.Code == "INVALID_INPUT") {
            submission = new();
            if (!IsDisposed) status.Text = "Core rejected the request before admission. Correct the draft; no task acknowledged. " + error.Message;
        }
        catch (Exception error) { if (!IsDisposed) status.Text = "Task not confirmed: " + error.Message; }
        finally { busy = false; submitting = false; if (!IsDisposed) RenderDetail(); }
    }

    private string ReceiptText() => Receipt.HasValue ? "\n\nACKNOWLEDGEMENT (not execution proof)\nTask: " +
        Get(Receipt.Value, "task_id") + "\nState: " + Get(Receipt.Value, "status") +
        "\nBackend: " + Get(Receipt.Value, "selected_backend", "Not reported") +
        "\nRequested model: " + Get(Receipt.Value, "requested_model", "Not reported / provider default") +
        "\nRequested effort: " + Get(Receipt.Value, "requested_effort", "Not reported / configured") +
        "\nProject: " + Get(Receipt.Value, "working_directory", "Not reported") +
        "\nMode: " + Get(Receipt.Value, "workspace_mode", "Not reported") +
        "\n" + Get(Receipt.Value, "acknowledgement") : "";
    public void UpdateHostAvailability(string? epoch = null)
    {
        if (IsDisposed) return;
        var available = canUseCore();
        if (!available) { catalogueCurrent = false; status.Text = "Core unavailable or host effects blocked. Catalogue/details are stale; draft retained. Nothing will be submitted."; }
        else if (currentEpoch is not null && currentEpoch != epoch)
        { catalogueCurrent = false; status.Text = "Core instance changed. Cached catalogue is stale; explicitly read cached list. Retained submissions cannot cross Core instances."; }
        else if (!wasAvailable) status.Text = "Core connected. Read cached list to inspect current configured agents without a discovery probe. Draft retained.";
        wasAvailable = available; currentEpoch = epoch; RenderDetail();
    }
    public void CloseForHostShutdown() { shuttingDown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed) { resourcesDisposed = true; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }

    private static string Get(JsonElement item, string key, string fallback = "") =>
        item.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback : fallback;
}
