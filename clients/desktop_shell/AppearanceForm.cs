namespace Sora.DesktopShell;

// Native, model-independent UI controls. Core configuration is deliberately not editable here.
internal sealed class AppearanceForm : Form
{
    private readonly ShellPreferencesStore store;
    private readonly Func<string> shortcutStatus;
    private readonly Action resetPlacement;
    private readonly ComboBox theme = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Top,
        AccessibleName = "Panel theme" };
    private readonly ComboBox shortcut = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Top,
        AccessibleName = "Chat shortcut" };
    private readonly NumericUpDown textScale = new() { Minimum = 85, Maximum = 175, Increment = 5,
        Dock = DockStyle.Top, AccessibleName = "Panel text size percent" };
    private readonly CheckBox compact = new() { Text = "Use compact Chat", AutoSize = true };
    private readonly CheckBox pinned = new() { Text = "Pin Chat above other windows (your choice)", AutoSize = true };
    private readonly CheckBox technical = new() { Text = "Show technical detail in Chat", AutoSize = true };
    private readonly CheckBox reduced = new() { Text = "Reduced motion (current panels are static)", AutoSize = true };
    private readonly Label status = new() { AutoSize = true, Dock = DockStyle.Fill };
    private readonly Label importInfo = new() { AutoSize = true, Dock = DockStyle.Fill };
    private readonly Button save = ShellTheme.Button("Save UI preferences", "Save UI preferences");
    private readonly Button recover = ShellTheme.Button("Preserve invalid file / use defaults…", "Recover invalid UI preferences");
    private readonly Button reset = ShellTheme.Button("Reset panel placement…", "Reset panel placement only");
    private ShellPreferences baseline = new();
    private bool loading;
    private bool dirty;
    public bool HasUnsavedChanges => dirty;
    public AppearanceForm(ShellPreferencesStore store, Func<string> shortcutStatus, Action resetPlacement)
    {
        this.store = store; this.shortcutStatus = shortcutStatus; this.resetPlacement = resetPlacement;
        Text = "SORA · Appearance and panels";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f); ClientSize = new Size(600, 640); MinimumSize = new Size(400, 420);
        StartPosition = FormStartPosition.CenterScreen;
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, ColumnCount = 1, Padding = new Padding(16) };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var body = new TableLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, ColumnCount = 1,
            AutoSize = false, Padding = new Padding(0, 8, 16, 8) };
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        void Add(Control control)
        {
            body.RowStyles.Add(new RowStyle(SizeType.AutoSize)); body.Controls.Add(control, 0, body.RowCount++);
            control.Margin = new Padding(0, 4, 0, 8);
        }
        foreach (var item in Enum.GetValues<ShellPalette>()) theme.Items.Add(item);
        foreach (var item in Enum.GetValues<ShellShortcut>()) shortcut.Items.Add(item);
        root.Controls.Add(new Label { Text = "UI-only preferences · no model, access, voice or agent settings are changed.",
            AutoSize = true, Dock = DockStyle.Fill }, 0, 0);
        Add(new Label { Text = "Theme · System uses Windows system colours; high contrast always wins.", AutoSize = true });
        Add(theme); Add(new Label { Text = "Panel text size (%)", AutoSize = true }); Add(textScale);
        Add(new Label { Text = "Chat shortcut · None disables registration; the command menu stays available.", AutoSize = true });
        Add(shortcut); Add(compact); Add(pinned); Add(technical); Add(reduced); Add(importInfo); Add(status);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        var cancel = ShellTheme.Button("Cancel", "Cancel unsaved UI preferences");
        var reload = ShellTheme.Button("Reload saved values…", "Reload saved UI preferences");
        actions.Controls.AddRange([save, cancel, reload, reset, recover]);
        root.Controls.Add(body, 0, 1); root.Controls.Add(actions, 0, 2); Controls.Add(root); ShellTheme.Apply(this);
        foreach (var control in new Control[] { theme, shortcut, textScale, compact, pinned, technical, reduced })
        {
            if (control is ComboBox combo) combo.SelectedIndexChanged += DraftChanged;
            if (control is NumericUpDown number) number.ValueChanged += DraftChanged;
            if (control is CheckBox check) check.CheckedChanged += DraftChanged;
        }
        save.Click += (_, _) => Save();
        cancel.Click += (_, _) => { dirty = false; Close(); };
        reload.Click += (_, _) => {
            if (dirty && MessageBox.Show(this, "Discard unsaved UI preference edits and reload?", "SORA",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            store.Reload(); LoadDraft();
        };
        reset.Click += (_, _) => {
            if (MessageBox.Show(this, "Clear saved panel positions and bring open panels into the current work area? " +
                "Other preferences, drafts and Core settings are unchanged.", "SORA", MessageBoxButtons.YesNo,
                MessageBoxIcon.Question) != DialogResult.Yes) return;
            this.resetPlacement(); ShowStatus();
        };
        recover.Click += (_, _) => {
            if (MessageBox.Show(this, "Preserve the invalid UI file in a dated byte-identical backup and replace only UI " +
                "preferences with defaults? Core configuration is unchanged.", "SORA", MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning) != DialogResult.Yes) return;
            if (store.TryRecoverDefaults(out var error)) LoadDraft(); else status.Text = error;
        };
        FormClosing += (_, e) => {
            if (dirty && MessageBox.Show(this, "Keep editing unsaved UI preferences? Choose No to discard this draft.",
                "SORA", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes) e.Cancel = true;
        };
        store.Changed += StoreChanged;
        FormClosed += (_, _) => store.Changed -= StoreChanged;
        Resize += (_, _) => {
            var width = Math.Max(120, ClientSize.Width - (int)(64 * DeviceDpi / 96f));
            foreach (var label in body.Controls.OfType<Label>()) label.MaximumSize = new Size(width, 0);
        };
        LoadDraft();
    }
    private void DraftChanged(object? sender, EventArgs args) { if (!loading) dirty = true; }
    private void StoreChanged(object? sender, EventArgs args)
    {
        if (IsDisposed) return;
        if (!dirty && !loading) LoadDraft(); else ShowStatus();
    }
    private void ShowStatus()
    {
        save.Enabled = reset.Enabled = !store.ReadOnly; recover.Visible = store.ReadOnly;
        status.Text = (store.Diagnostic.Length == 0 ? "UI preferences revision " + store.Current.Revision : store.Diagnostic)
            + "\n" + shortcutStatus() + "\n" + store.FilePath;
    }
    private void LoadDraft()
    {
        loading = true; baseline = store.Current;
        theme.SelectedItem = baseline.Theme; shortcut.SelectedItem = baseline.Shortcut;
        textScale.Value = (decimal)(baseline.TextScale * 100); compact.Checked = baseline.ChatCompact;
        pinned.Checked = baseline.ChatPinned; technical.Checked = baseline.ShowTechnicalDetail; reduced.Checked = baseline.ReducedMotion;
        var imported = baseline.Imports.Where(item => item.Status == "imported").ToArray();
        importInfo.Text = (baseline.ImportAttempted ? "Legacy import: " + imported.Length +
            " file(s) imported once; originals/backup bytes retained.\n"
            : "Legacy import not attempted; recover UI preferences first.\n")
            + (baseline.Imports.Any(item => item.Status == "invalid") ? "Unrecognized/corrupt legacy file ignored.\n" : "")
            + (imported.Any(item => item.AlwaysOnTop == true) ? "Old widget topmost was NOT applied; use Pin Chat explicitly.\n" : "")
            + (imported.Any(item => item.Quiet.HasValue || item.SelectedTab.HasValue)
                ? "Legacy quiet/tab choices are recorded only; no ambient/secondary-view parity is claimed.\n" : "")
            + (baseline.LegacyChat is not null ? "Old physical coordinates have no recorded DPI; first placement is best effort and clamped." : "");
        loading = false; dirty = false; ShowStatus();
    }
    private bool Save()
    {
        var draft = baseline with { Theme = (ShellPalette)theme.SelectedItem!, Shortcut = (ShellShortcut)shortcut.SelectedItem!,
            TextScale = (double)textScale.Value / 100, ChatCompact = compact.Checked, ChatPinned = pinned.Checked,
            ShowTechnicalDetail = technical.Checked, ReducedMotion = reduced.Checked };
        if (!store.TrySaveAppearance(draft, baseline, out var error)) { status.Text = error; return false; }
        LoadDraft(); status.Text = "Saved UI preferences. " + shortcutStatus(); return true;
    }
    public bool CanCloseForHostShutdown()
    {
        if (!dirty) return true;
        var choice = MessageBox.Show(this, "Save UI preferences before quitting the desktop host? Cancel keeps editing.",
            "SORA", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question);
        if (choice == DialogResult.Cancel) return false;
        if (choice == DialogResult.Yes) return Save();
        dirty = false; return true;
    }
}
