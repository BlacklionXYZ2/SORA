using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopApp;

/// <summary>Schema-driven owner preferences. Core validates and owns all persisted state.</summary>
public sealed class ModelSettingsEditor : UserControl
{
    private readonly IWidgetApi api;
    private readonly Func<bool> canUseCore;
    private readonly Func<string?> coreEpoch;
    private readonly CancellationTokenSource lifetime = new();
    private readonly SettingsDraftState draft = new();
    public bool HasUnsavedChanges => draft.Dirty;
    public bool HasPendingWork => busy || modalEditors > 0;
    public event EventHandler? ControlsRebuilt;
    private readonly TableLayoutPanel rows = new() { AutoSize = true, Dock = DockStyle.Top, ColumnCount = 3 };
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = true, Padding = new Padding(0, 4, 0, 6) };
    private readonly Label result = new() { Dock = DockStyle.Fill, AutoSize = true, Padding = new Padding(0, 4, 0, 6) };
    private readonly Button reload = new() { Text = "Reload model", AutoSize = true };
    private readonly Button save = new() { Text = "Save settings", AutoSize = true };
    private readonly ToolTip help = new();
    private readonly Panel scroll = new() { Dock = DockStyle.Fill, AutoScroll = true };
    private readonly ListBox section = new() { Dock = DockStyle.Fill, IntegralHeight = false,
        AccessibleName = "Settings category" };
    private readonly CheckBox advanced = new() { Text = "Show advanced controls", AutoSize = true };
    private readonly Label categoryInfo = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly Label modelInfo = new() { Dock = DockStyle.Fill, AutoSize = true, Padding = new Padding(6) };
    private readonly TextBox launchInfo = new() { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true,
        WordWrap = false, ScrollBars = ScrollBars.Both, AccessibleName = "Core launch arguments read only" };
    private readonly Panel launchPanel = new() { Dock = DockStyle.Fill, Height = 190 };
    private readonly Dictionary<int, (string Category, bool Advanced, float Height)> categoryRows = [];
    private readonly FlowLayoutPanel actions;
    private readonly Dictionary<string, Control> headings = [];
    private readonly Dictionary<string, (Control Control, string Type)> editors = [];
    private readonly Dictionary<string, JsonElement> original = [];
    private readonly Dictionary<string, string[]> agentModelChoices = [];
    private JsonElement snapshot;
    private int revision => draft.Revision;
    private int modalEditors;
    private bool dirty => draft.Dirty;
    private bool rendering, busy;
    private string? deviceSignature;

    public ModelSettingsEditor(IWidgetApi api, Func<bool>? canUseCore = null, Func<string?>? coreEpoch = null)
    {
        this.api = api;
        this.canUseCore = canUseCore ?? (() => true);
        this.coreEpoch = coreEpoch ?? (() => null);
        AutoScaleMode = AutoScaleMode.None;
        Dock = DockStyle.Fill;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.SizeChanged += (_, _) => {
            // Wrap long readiness/recovery lines within the current DPI-scaled panel width.
            int width = Math.Max(100, layout.ClientSize.Width - layout.Padding.Horizontal - 8);
            status.MaximumSize = new Size(width, 0);
            result.MaximumSize = new Size(width, 0);
        };
        layout.Controls.Add(status, 0, 0);
        actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink, Padding = new Padding(0, 3, 0, 8) };
        var discard = new Button { Text = "Discard draft", AutoSize = true };
        var refresh = new Button { Text = "Refresh from disk", AutoSize = true };
        var reconcile = new Button { Text = "Reconcile draft…", AutoSize = true };
        var inspect = new Button { Text = "View saved settings", AutoSize = true };
        var agentModels = new Button { Text = "Refresh agent models", AutoSize = true };
        agentModels.Click += async (_, _) => await Act(async () => {
            result.Text = "Discovering specialist metadata only; no inference is started…";
            var catalogue = await api.PostAsync("/api/v1/agents/catalogue/refresh", new { }, lifetime.Token);
            if (IsDisposed) return;
            var unavailable = new List<string>();
            rendering = true;
            try {
                foreach (var entry in catalogue.GetProperty("providers").EnumerateArray())
                {
                    string providerId = entry.GetProperty("provider").GetString()!;
                    string agent = providerId switch { "codex-app-server" => "codex", "hermes-acp" => "hermes", _ => providerId };
                    if (entry.GetProperty("state").GetString() == "unavailable") unavailable.Add(agent);
                    agentModelChoices[agent] = entry.GetProperty("models").EnumerateArray()
                        .Select(model => model.GetProperty("id").GetString()!).ToArray();
                    if (!editors.TryGetValue($"agents.{agent}.preferred_model", out var editor) || editor.Control is not ComboBox combo) continue;
                    string draft = combo.Text;
                    combo.Items.Clear(); combo.Items.Add("");
                    combo.Items.AddRange(agentModelChoices[agent]);
                    combo.Text = draft;
                }
            } finally { rendering = false; }
            result.Text = "Model choices refreshed. Provider-listed IDs are not verified access. Unsaved preferences were preserved.";
            if (unavailable.Count > 0) result.Text += " Discovery unavailable: " + string.Join(", ", unavailable) + ". Inspect Activity → Agents and models for details.";
        });
        inspect.Click += (_, _) => {
            if (snapshot.ValueKind != JsonValueKind.Object) return;
            var values = snapshot.GetProperty("fields").EnumerateArray().ToDictionary(
                f => f.GetProperty("key").GetString()!, f => f.GetProperty("value").Clone());
            using var view = new Form { Text = "Saved SORA settings · read only", Width = 800, Height = 600,
                StartPosition = FormStartPosition.CenterParent };
            view.Controls.Add(new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true,
                ScrollBars = ScrollBars.Both, WordWrap = false,
                Text = "Store: " + snapshot.GetProperty("settings_path").GetString() + Environment.NewLine +
                    JsonSerializer.Serialize(values, new JsonSerializerOptions { WriteIndented = true }) });
            TrackedModal(() => view.ShowDialog(this));
        };
        save.Click += async (_, _) => await Act(SaveAsync);
        reload.Click += async (_, _) => {
            var epoch = this.coreEpoch(); int expected = revision;
            if (TrackedModal(() => MessageBox.Show(this, "Apply the saved model settings? Dialogue pauses while the model reloads; this may take a few minutes.",
                "Reload SORA model", MessageBoxButtons.OKCancel, MessageBoxIcon.Question)) == DialogResult.OK)
                await Act(async () => {
                    if (epoch != this.coreEpoch() || expected != revision || dirty) throw new InvalidOperationException("Core/settings changed during confirmation; nothing sent.");
                    var response = await api.PostAsync("/api/v1/model/reload", new { expected_revision = expected }, lifetime.Token);
                    if (IsDisposed) return;
                    Render(response);
                    result.Text = "Reload requested. Settings will show completion or recovery; Core stays running.";
                });
        };
        discard.Click += (_, _) => {
            if (busy || dirty && TrackedModal(() => MessageBox.Show(this, "Discard the retained draft and show the latest saved values?",
                "Discard settings draft", MessageBoxButtons.OKCancel)) != DialogResult.OK) return;
            draft.Discard(); Render(snapshot); result.Text = "Draft discarded; inspect the saved state before editing again.";
        };
        refresh.Click += async (_, _) => {
            var epoch = this.coreEpoch();
            if (TrackedModal(() => MessageBox.Show(this, "Read and apply live settings from disk? This may stop voice or revoke agent runs. " +
                "An unsaved draft will be discarded only after a confirmed response; model/boot changes remain staged.", "Refresh settings",
                MessageBoxButtons.OKCancel)) != DialogResult.OK) return;
            await Act(async () => {
                if (epoch != this.coreEpoch()) throw new InvalidOperationException("Core changed during confirmation; nothing sent.");
                var response = await api.PostAsync("/api/v1/settings/refresh", new { }, lifetime.Token);
                if (IsDisposed) return;
                draft.Discard(); Render(response);
                result.Text = "Settings read from disk. Model/boot changes remain staged until applied.";
            });
        };
        reconcile.Click += async (_, _) => await Act(ReconcileAsync);
        actions.Controls.AddRange([save, discard, reconcile, refresh, reload, inspect, agentModels]);
        actions.Controls.Add(advanced);
        section.Items.AddRange(new object[] { "General", "Appearance", "Models", "Audio", "Vision", "Memory",
            "Tools", "Automation", "Performance", "Advanced" });
        section.SelectedIndex = 0;
        section.SelectedIndexChanged += (_, _) => ApplyCategory();
        advanced.CheckedChanged += (_, _) => ApplyCategory();
        layout.Controls.Add(actions, 0, 1);
        rows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 37));
        rows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 43));
        rows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        scroll.Controls.Add(rows);
        var body = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 4 };
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 130));
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        body.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        launchPanel.Controls.Add(launchInfo);
        body.Controls.Add(section, 0, 0); body.SetRowSpan(section, 4);
        body.Controls.Add(categoryInfo, 1, 0); body.Controls.Add(modelInfo, 1, 1);
        body.Controls.Add(launchPanel, 1, 2); body.Controls.Add(scroll, 1, 3);
        body.SizeChanged += (_, _) => {
            categoryInfo.MaximumSize = modelInfo.MaximumSize = new Size(Math.Max(120, body.Width - 140), 0);
        };
        layout.Controls.Add(body, 0, 2);
        layout.Controls.Add(result, 0, 3);
        Controls.Add(layout);
        FontChanged += (_, _) => ResizeRows();
        ReportUnavailable("Waiting for the canonical settings projection. No settings effects are available yet.");
    }

    public void Render(JsonElement settings)
    {
        if (IsDisposed) return;
        if (settings.ValueKind != JsonValueKind.Object || !settings.TryGetProperty("fields", out var fields)) return;
        if (!settings.TryGetProperty("settings_version", out var version) || version.GetInt32() != 9) {
            status.Text = "This editor requires canonical AppSettings v9. Legacy projection is read-only.";
            save.Enabled = reload.Enabled = rows.Enabled = false; return;
        }
        // Validate render prerequisites before replacing a last-good projection/draft.
        if (fields.ValueKind != JsonValueKind.Array || fields.GetArrayLength() > 256
            || new[] { "settings_revision", "model_state", "disk_changed", "can_reload",
                "settings_warning", "model_error", "settings_path" }.Any(key => !settings.TryGetProperty(key, out _)))
            throw new InvalidDataException("Canonical Settings render metadata is incomplete.");
        var identities = new HashSet<string>(StringComparer.Ordinal);
        foreach (var field in fields.EnumerateArray()) {
            if (field.ValueKind != JsonValueKind.Object || new[] { "key", "label", "group", "type", "tier", "help" }
                .Any(key => !field.TryGetProperty(key, out var text) || text.ValueKind != JsonValueKind.String)
                || !identities.Add(field.GetProperty("key").GetString()!)
                || !field.TryGetProperty("choices", out var choices) || choices.ValueKind != JsonValueKind.Array
                || !field.TryGetProperty("value", out _) || !field.TryGetProperty("pending", out var pending)
                || pending.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw new InvalidDataException("Canonical Settings field metadata is incomplete or duplicated.");
        }
        snapshot = settings.Clone();
        var nextRevision = settings.GetProperty("settings_revision").GetInt32();
        bool rebuild = false;
        if (dirty || draft.Busy || !busy && modalEditors == 0)
            rebuild = draft.Observe(version.GetInt32(), nextRevision, coreEpoch());
        UpdateState(settings);
        if (dirty || busy || modalEditors > 0 || !rebuild) return;
        rendering = true;
        rows.SuspendLayout();
        try
        {
            foreach (Control control in rows.Controls.Cast<Control>().ToArray()) control.Dispose();
            rows.Controls.Clear(); rows.RowStyles.Clear(); rows.RowCount = 0;
            editors.Clear(); original.Clear(); headings.Clear(); categoryRows.Clear(); deviceSignature = null;
            string group = "";
            foreach (var field in fields.EnumerateArray().OrderBy(f => Category(f))
                .ThenBy(f => f.GetProperty("key").GetString()!.StartsWith("agents.") ? 2
                    : f.GetProperty("key").GetString()!.Contains(".speculative.") ? 1 : 0)
                .ThenBy(f => f.GetProperty("group").GetString()))
            {
                string key = field.GetProperty("key").GetString()!;
                string category = Category(field);
                bool isAdvanced = SettingsCategories.Advanced(field);
                string nextGroup = category + " · " + field.GetProperty("group").GetString()!;
                if (group != nextGroup)
                {
                    group = nextGroup;
                    var title = new Label { Text = group, Dock = DockStyle.Fill,
                        Font = new Font(Font, FontStyle.Bold), TextAlign = ContentAlignment.MiddleLeft };
                    int heading = rows.RowCount++;
                    rows.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
                    rows.Controls.Add(title, 0, heading); rows.SetColumnSpan(title, 3);
                    headings[group] = title;
                    categoryRows[heading] = (category, false, 34);
                }
                int row = rows.RowCount++;
                rows.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
                categoryRows[row] = (category, isAdvanced, 38);
                string kind = field.GetProperty("type").GetString()!;
                var value = field.GetProperty("value").Clone();
                original[key] = value;
                var label = new Label { Text = field.GetProperty("label").GetString(), Dock = DockStyle.Fill,
                    TextAlign = ContentAlignment.MiddleLeft, AutoEllipsis = true };
                rows.Controls.Add(label, 0, row);
                Control editor;
                if (kind == "bool")
                {
                    var check = new CheckBox { Checked = value.GetBoolean(), Dock = DockStyle.Fill };
                    check.CheckedChanged += (_, _) => MarkDirty(); editor = check;
                }
                else if (kind == "agent-model-purposes")
                {
                    string agent = key.Split('.')[1];
                    var purposes = new ModelPurposeControl(agent, value,
                        () => agentModelChoices.TryGetValue(agent, out var choices) ? choices : []);
                    purposes.DraftChanged += (_, _) => MarkDirty(); editor = purposes;
                    purposes.EditorOpening += (_, _) => modalEditors++;
                    purposes.EditorClosed += (_, _) => { modalEditors--; if (!IsDisposed) Render(snapshot); };
                }
                else if (kind is "enum" or "gpu" or "agent-model" || key is "voice.input_device" or "voice.output_device")
                {
                    var combo = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = kind == "enum"
                        ? ComboBoxStyle.DropDownList : ComboBoxStyle.DropDown };
                    foreach (var option in field.GetProperty("choices").EnumerateArray()) combo.Items.Add(option.GetString()!);
                    if (kind == "gpu") combo.Items.Add("0");
                    if (kind == "agent-model" && agentModelChoices.TryGetValue(key.Split('.')[1], out var modelChoices))
                    { combo.Items.Add(""); combo.Items.AddRange(modelChoices); }
                    combo.Text = ValueText(value);
                    combo.TextChanged += (_, _) => MarkDirty(); editor = combo;
                }
                else if (kind is "int" or "float")
                {
                    var number = new NumericUpDown { Dock = DockStyle.Fill,
                        Minimum = field.TryGetProperty("min", out var min) ? min.GetDecimal() : 0,
                        Maximum = field.TryGetProperty("max", out var max) ? max.GetDecimal() : 1000000,
                        DecimalPlaces = kind == "float" ? 1 : 0 };
                    number.Value = Math.Clamp(value.GetDecimal(), number.Minimum, number.Maximum);
                    number.ValueChanged += (_, _) => MarkDirty(); editor = number;
                }
                else
                {
                    var text = new TextBox { Text = ValueText(value), Dock = DockStyle.Fill };
                    text.TextChanged += (_, _) => MarkDirty(); editor = text;
                }
                editors[key] = (editor, kind);
                editor.AccessibleName = key;
                editor.Enabled = field.TryGetProperty("editable", out var editable) && editable.ValueKind == JsonValueKind.True;
                if (kind.StartsWith("path-"))
                {
                    var pathRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
                    pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
                    pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 40));
                    var browse = new Button { Text = "…", Dock = DockStyle.Fill, Enabled = editor.Enabled };
                    help.SetToolTip(browse, "Browse for " + field.GetProperty("label").GetString());
                    browse.Click += async (_, _) => await BrowseAsync(key, kind, editor);
                    pathRow.Controls.Add(editor, 0, 0); pathRow.Controls.Add(browse, 1, 0);
                    rows.Controls.Add(pathRow, 1, row);
                }
                else rows.Controls.Add(editor, 1, row);
                string tier = field.GetProperty("tier").GetString() switch {
                    "live" => "Immediate", "model_reload" => "On model reload", _ => "Next SORA boot" };
                var badge = new Label { Text = tier, Dock = DockStyle.Fill,
                    TextAlign = ContentAlignment.MiddleLeft, Tag = key };
                rows.Controls.Add(badge, 2, row);
                help.SetToolTip(editor, field.GetProperty("help").GetString());
                help.SetToolTip(label, field.GetProperty("label").GetString() + "\n" + key);
            }
        }
        finally { rendering = false; rows.ResumeLayout(); }
        ResizeRows(); ControlsRebuilt?.Invoke(this, EventArgs.Empty);
        UpdateState(settings);
    }

    private static string Category(JsonElement field) => SettingsCategories.Category(field);
    private DialogResult TrackedModal(Func<DialogResult> show)
    {
        modalEditors++;
        try { return show(); }
        finally { modalEditors--; if (!IsDisposed && snapshot.ValueKind == JsonValueKind.Object) Render(snapshot); }
    }
    public void ReportUnavailable(string message)
    {
        status.Text = message;
        foreach (var button in actions.Controls.OfType<Button>())
            if (button.Text is not ("Discard draft" or "View saved settings")) button.Enabled = false;
    }
    private void ApplyCategory()
    {
        if (rendering) return;
        string category = section.SelectedItem as string ?? "General";
        modelInfo.Visible = category == "Models";
        launchPanel.Visible = category == "Advanced";
        categoryInfo.Text = category switch {
            "Appearance" => "Panel theme, text size, shortcut and placement are in Appearance (UI-only store). Avatar styling beyond supported controls is not yet implemented.",
            "Memory" => "No editable memory preferences exist in AppSettings v9. The opt-in profile host has a separate canonical Memory browser when the matching Core supports it. Correction/forget, conversational presentation and the relationship graph remain later stages.",
            "Automation" => "No scheduler defaults exist in AppSettings v9. Automation controls will be added with the real scheduler; specialist task limits are in Tools.",
            "Models" => "SORA's dialogue model and specialist agents are separate. Model IDs/purposes are exact saved preferences, not verified provider access.",
            "Audio" => "Saving voice changes stops active audio. Start audio explicitly in Voice. Device keys can be typed or selected from current actual inventory; blank uses Windows default.",
            "Vision" => "Static local access and automatic context preferences. Native desktop information and optional captures are distinct; no repeated per-file permission requests.",
            "Tools" => "Static local capabilities and specialist destinations. Direct file write does not install a writer; use agent delegation and Project paths for supported writes.",
            "Performance" => "Supported runtime tuning only. No measured VRAM telemetry is currently supplied; none is estimated here.",
            "Advanced" => "Launch configuration and unrecognized fields. Changes still follow their canonical effect tiers; no raw launch flags can be edited here.",
            _ => "Save applies immediate controls only. Model reload applies saved model controls; next-start controls require a deliberate restart. Closing this window retains the draft."
        };
        rows.SuspendLayout();
        foreach (var (row, metadata) in categoryRows) {
            bool visible = metadata.Category == category && (!metadata.Advanced || advanced.Checked);
            rows.RowStyles[row].Height = visible ? metadata.Height : 0;
            foreach (Control control in rows.Controls.Cast<Control>().Where(c => rows.GetRow(c) == row)) control.Visible = visible;
        }
        rows.ResumeLayout(); scroll.AutoScrollPosition = Point.Empty;
    }

    private void ResizeRows()
    {
        float height = Math.Max(38 * DeviceDpi / 96f, Font.Height + 16 * DeviceDpi / 96f);
        foreach (int row in categoryRows.Keys.ToArray()) {
            var metadata = categoryRows[row]; categoryRows[row] = (metadata.Category, metadata.Advanced, height);
        }
        ApplyCategory();
    }

    public void SetDeviceChoices(IEnumerable<(string Key, bool Input, bool Output)> devices)
    {
        var inventory = devices.ToArray();
        string signature = JsonSerializer.Serialize(inventory.OrderBy(d => d.Key));
        if (deviceSignature == signature) return;
        deviceSignature = signature;
        rendering = true;
        try {
            foreach (string key in new[] { "voice.input_device", "voice.output_device" }) {
                if (!editors.TryGetValue(key, out var editor) || editor.Control is not ComboBox combo) continue;
                string retained = combo.Text;
                combo.Items.Clear(); combo.Items.Add("");
                combo.Items.AddRange(inventory.Where(d => key == "voice.input_device" ? d.Input : d.Output)
                    .GroupBy(d => d.Key).Where(g => g.Count() == 1).Select(g => g.Key).Cast<object>().ToArray());
                combo.Text = retained;
            }
        } finally { rendering = false; }
    }

    private void UpdateState(JsonElement settings)
    {
        var fields = settings.GetProperty("fields").EnumerateArray().ToArray();
        int model = fields.Count(f => f.GetProperty("pending").GetBoolean() && f.GetProperty("tier").GetString() == "model_reload");
        int boot = fields.Count(f => f.GetProperty("pending").GetBoolean() && f.GetProperty("tier").GetString() == "next_boot");
        string state = settings.GetProperty("model_state").GetString()!;
        string Field(string key, string part) {
            var field = fields.FirstOrDefault(f => f.GetProperty("key").GetString() == key);
            return field.ValueKind == JsonValueKind.Object && field.TryGetProperty(part, out var value) ? ValueText(value) : "not reported";
        }
        modelInfo.Text = $"Dialogue runtime: {Field("dialogue.backend", "active_value")} · Core model state: {state}\n" +
            $"Saved GGUF: {Field("llama.model_path", "value")}\nCore-reported effective GGUF (managed runtime only): {Field("llama.model_path", "active_value")}\n" +
            $"External model (external runtime only): {Field("external.model", "active_value")}\n" +
            $"Effective context: {Field("llama.context_size", "active_value")} · K/V cache: {Field("llama.cache_type_k", "active_value")}/{Field("llama.cache_type_v", "active_value")} · Flash attention: {Field("llama.flash_attn", "active_value")}\n" +
            "Runtime support: " + (settings.TryGetProperty("runtime_support", out var support) ? ValueText(support) : "not reported") +
            " · VRAM/capability telemetry not supplied.";
        bool diskChanged = settings.GetProperty("disk_changed").GetBoolean();
        var statusLines = new List<string?> {
            $"Model: {state} · {model} saved changes need model reload · {boot} need next boot",
            diskChanged ? "Settings changed on disk — Refresh from disk before saving." :
                settings.GetProperty("settings_warning").GetString(),
            settings.GetProperty("model_error").GetString()
        };
        statusLines.Add($"Saved revision {settings.GetProperty("settings_revision")} · draft based on {revision}");
        if (draft.Conflict) statusLines.Add("Saved revision or Core changed. Draft retained; inspect saved values and explicitly discard/reconcile before saving.");
        if (draft.OutcomeUnknown) statusLines.Add("Save outcome is unconfirmed. Inspect current saved values; no automatic retry. Discard/reconcile the retained draft before another save.");
        if (settings.TryGetProperty("perception_status", out var perception))
            statusLines.Add(perception.GetString());
        status.Text = string.Join(Environment.NewLine, statusLines.Where(line => !string.IsNullOrWhiteSpace(line)));
        help.SetToolTip(status, status.Text);
        bool available = canUseCore();
        string launchText = SettingsLaunchPresentation.Format(settings, available);
        if (launchInfo.Text != launchText) launchInfo.Text = launchText;
        foreach (var button in actions.Controls.OfType<Button>()) button.Enabled = !busy && available;
        // Inspect/discard remain usable offline; only effects require the matching live Core.
        actions.Controls.OfType<Button>().First(b => b.Text == "View saved settings").Enabled = !busy;
        actions.Controls.OfType<Button>().First(b => b.Text == "Discard draft").Enabled = !busy;
        reload.Enabled = available && !busy && !dirty && !draft.Conflict && !draft.OutcomeUnknown && !diskChanged && settings.GetProperty("can_reload").GetBoolean();
        save.Enabled = available && !busy && draft.CanSave && !diskChanged && state != "reloading";
        foreach (var badge in rows.Controls.OfType<Label>().Where(label => label.Tag is string))
        {
            var field = fields.FirstOrDefault(f => f.GetProperty("key").GetString() == (string)badge.Tag!);
            if (field.ValueKind != JsonValueKind.Object) continue;
            var tier = field.GetProperty("tier").GetString() switch {
                "live" => "Immediate", "model_reload" => "On model reload", _ => "Next SORA boot" };
            badge.Text = tier + (field.GetProperty("pending").GetBoolean() ? " · pending" : "");
            help.SetToolTip(badge, "Saved: " + ValueText(field.GetProperty("value")) + "\nEffective: " +
                (field.TryGetProperty("active_value", out var active) ? ValueText(active) : "not reported"));
        }
    }

    private static string ValueText(JsonElement value) => value.ValueKind == JsonValueKind.Null ? "" :
        value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText();

    private void MarkDirty()
    {
        if (rendering) return;
        draft.Edit(); reload.Enabled = false;
        result.Text = "Unsaved draft. Save first; each row shows when its change takes effect.";
        if (snapshot.ValueKind == JsonValueKind.Object) Render(snapshot);
    }

    private async Task BrowseAsync(string key, string kind, Control editor)
    {
        if (busy || modalEditors > 0) return;
        var browseEpoch = coreEpoch(); string? selectedPath = null;
        modalEditors++;
        try {
            if (kind == "path-dir") {
                using var folder = new FolderBrowserDialog();
                if (folder.ShowDialog(this) == DialogResult.OK) selectedPath = folder.SelectedPath;
            }
            else {
                using var picker = new OpenFileDialog { Filter = kind == "path-exe" ? "Executable|*.exe" :
                    kind == "path-file" ? "Local speech assets|*.onnx;*.bin|All files|*.*" : "GGUF models|*.gguf",
                    CheckFileExists = true, Multiselect = false, Title = "Select " + key };
                if (File.Exists(editor.Text)) { picker.FileName = editor.Text; picker.InitialDirectory = Path.GetDirectoryName(editor.Text); }
                if (picker.ShowDialog(this) == DialogResult.OK) selectedPath = picker.FileName;
            }
            if (!IsDisposed && !editor.IsDisposed && selectedPath is not null) editor.Text = selectedPath;
        }
        finally { modalEditors--; if (!IsDisposed && snapshot.ValueKind == JsonValueKind.Object) Render(snapshot); }
        if (IsDisposed || editor.IsDisposed || selectedPath is null || key != "llama.model_path") return;
        if (browseEpoch != coreEpoch()) { result.Text = "Core changed during file selection. Draft retained; reconcile before further model discovery or Save."; return; }
        await Act(async () => {
            string selected = selectedPath;
            var epoch = coreEpoch();
            var found = await api.PostAsync("/api/v1/models/projectors", new { model_path = selected }, lifetime.Token);
            if (IsDisposed || editor.IsDisposed || editor.Text != selected || coreEpoch() != epoch) return;
            var paths = found.GetProperty("projectors").EnumerateArray().Select(v => v.GetString()!).ToArray();
            var projector = editors["llama.mmproj_path"].Control;
            projector.Text = "";
            if (paths.Length == 1) projector.Text = paths[0];
            else if (paths.Length > 1)
            {
                using var choose = new Form { Text = "Choose matching projector", Width = 700, Height = 160,
                    StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false };
                var options = new ComboBox { Dock = DockStyle.Top, DropDownStyle = ComboBoxStyle.DropDownList };
                options.Items.AddRange(paths); options.SelectedIndex = 0;
                var accept = new Button { Text = "Use projector", Dock = DockStyle.Bottom, DialogResult = DialogResult.OK };
                choose.Controls.Add(options); choose.Controls.Add(accept); choose.AcceptButton = accept;
                if (choose.ShowDialog(this) == DialogResult.OK) {
                    if (epoch != coreEpoch()) throw new InvalidOperationException("Core changed during projector selection; draft retained.");
                    projector.Text = options.Text;
                }
                else { result.Text = "Projector choice cancelled. Model draft retained; choose a matching projector before Save."; return; }
            }
            result.Text = paths.Length == 0 ? "No adjacent mmproj found. Browse for the matching projector before saving." :
                "Projector selected. Compatibility is verified when the model actually loads.";
        });
    }

    private async Task SaveAsync()
    {
        var changes = ReadChanges();
        var submission = draft.BeginSave(coreEpoch());
        JsonElement response;
        try { response = await api.PostAsync("/api/v1/settings", new { version = draft.Version, expected_revision = revision, changes }, lifetime.Token); }
        catch { draft.SaveFailed(); throw; }
        if (IsDisposed) return;
        if (!draft.Acknowledge(submission, response.GetProperty("settings_version").GetInt32(),
            response.GetProperty("settings_revision").GetInt32(), coreEpoch())) {
            result.Text = "Response does not confirm this draft/Core. Draft retained; inspect saved values."; return;
        }
        snapshot = response.Clone();
        result.Text = "Saved. Immediate settings are active; use Reload model for pending model changes. Boot-only changes wait for restart.";
    }

    private Dictionary<string, object?> ReadChanges()
    {
        Dictionary<string, object?> changes = [];
        foreach (var (key, (control, kind)) in editors)
        {
            object? value = kind switch {
                "bool" => ((CheckBox)control).Checked,
                "int" => (int)((NumericUpDown)control).Value,
                "float" => (double)((NumericUpDown)control).Value,
                "gpu" => int.TryParse(control.Text, out var layers) ? layers : control.Text,
                "path-gguf" => string.IsNullOrWhiteSpace(control.Text) ? null : control.Text.Trim(),
                "agent-model-purposes" => ((ModelPurposeControl)control).Value,
                _ => control.Text.Trim()
            };
            if (!JsonElement.DeepEquals(JsonSerializer.SerializeToElement(value), original[key])) changes[key] = value;
        }
        return changes;
    }

    private async Task ReconcileAsync()
    {
        var edits = ReadChanges(); var epoch = coreEpoch();
        var current = await api.GetAsync("/api/v1/projections/settings", lifetime.Token);
        if (IsDisposed || epoch != coreEpoch()) throw new InvalidOperationException("Core changed while reading; draft retained.");
        int version = current.GetProperty("settings_version").GetInt32(), next = current.GetProperty("settings_revision").GetInt32();
        if (version != 9 || next < 0) throw new InvalidDataException("Current canonical v9 settings unavailable.");
        var fields = current.GetProperty("fields").EnumerateArray().ToDictionary(f => f.GetProperty("key").GetString()!);
        if (editors.Any(e => !fields.TryGetValue(e.Key, out var field) || field.GetProperty("type").GetString() != e.Value.Type
            || !field.GetProperty("editable").GetBoolean()))
            throw new InvalidDataException("Settings field schema changed; inspect the saved state. Draft retained.");
        var savedValues = fields.ToDictionary(f => f.Key, f => f.Value.GetProperty("value").Clone());
        var reviewedValues = SettingsDraftState.ReconciledValues(original, savedValues,
            edits.ToDictionary(e => e.Key, e => JsonSerializer.SerializeToElement(e.Value)));
        snapshot = current.Clone();
        using var review = new Form { Text = "Reconcile retained Settings draft · no Save", Width = 850, Height = 600,
            StartPosition = FormStartPosition.CenterParent };
        var text = new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false,
            Text = $"Current saved revision {next}; previous draft baseline {revision}. Core: {epoch ?? "compatible unbound client"}.\r\n" +
                "Retain only the edited fields below. All untouched fields will adopt current saved values.\r\n" +
                "Saving later may replace another edit to these same fields. This review applies no settings.\r\n\r\n" +
                string.Join("\r\n\r\n", edits.Select(e => e.Key + "\r\nPrevious saved: " + ValueText(original[e.Key]) +
                    "\r\nCurrent saved: " + ValueText(fields[e.Key].GetProperty("value")) +
                    "\r\nRetained edit: " + JsonSerializer.Serialize(e.Value))) };
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, AutoSize = true };
        var accept = new Button { Text = "Use reviewed draft (not Save)", AutoSize = true, DialogResult = DialogResult.OK };
        var cancel = new Button { Text = "Cancel / keep current draft", AutoSize = true, DialogResult = DialogResult.Cancel };
        buttons.Controls.AddRange([accept, cancel]); review.Controls.Add(text); review.Controls.Add(buttons); review.CancelButton = cancel;
        if (review.ShowDialog(this) != DialogResult.OK) return;
        if (epoch != coreEpoch() || snapshot.GetProperty("settings_revision").GetInt32() != next)
            throw new InvalidOperationException("Core/saved revision changed during review; draft retained. Review again.");
        rendering = true;
        try {
            foreach (var (key, (control, kind)) in editors) {
                var value = reviewedValues[key];
                if (control is CheckBox check) check.Checked = value.GetBoolean();
                else if (control is NumericUpDown number) number.Value = Math.Clamp(value.GetDecimal(), number.Minimum, number.Maximum);
                else if (control is ModelPurposeControl purposes) purposes.SetDraft(value);
                else control.Text = ValueText(value);
                original[key] = savedValues[key];
            }
            draft.Reconcile(version, next, epoch, edits.Count > 0); snapshot = current.Clone();
        } finally { rendering = false; }
        result.Text = "Reviewed draft retained against current saved values. Nothing applied; Save explicitly when ready.";
    }

    private async Task Act(Func<Task> action)
    {
        if (busy) return;
        busy = true; actions.Enabled = rows.Enabled = section.Enabled = false;
        try { await action(); }
        catch (Exception error) { if (draft.Busy) draft.SaveFailed(); if (!IsDisposed) { result.Text = error.Message; help.SetToolTip(result, error.Message); } }
        finally { busy = false; if (!IsDisposed) {
            actions.Enabled = rows.Enabled = section.Enabled = true;
            if (snapshot.ValueKind == JsonValueKind.Object) Render(snapshot);
        } }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) { lifetime.Cancel(); lifetime.Dispose(); help.Dispose(); }
        base.Dispose(disposing);
    }
}
