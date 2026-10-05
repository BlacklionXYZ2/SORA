using System.Drawing;
using System.Text.Json;

namespace Sora.DesktopWidget;

/// <summary>Shared draft editor. Caller performs the canonical revision-checked Save.</summary>
public sealed class ModelPurposeForm : Form
{
    private readonly ModelPurposeDraft draft;
    private readonly DataGridView grid = new() { Dock = DockStyle.Fill, ReadOnly = true,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect, MultiSelect = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells };
    private readonly ComboBox model = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDown };
    private readonly TextBox purpose = new() { Dock = DockStyle.Fill, Multiline = true,
        MaxLength = 500, ScrollBars = ScrollBars.Vertical };
    private readonly Label status = new() { AutoSize = true, Dock = DockStyle.Fill };
    private readonly Button accept = new() { Text = "Use draft", AutoSize = true };
    private bool saving;
    public JsonElement Draft => draft.ToJson();

    public ModelPurposeForm(string agent, JsonElement initial, IEnumerable<string> listedModels,
        Func<JsonElement, Task>? saveDraft = null)
    {
        SuspendLayout();
        draft = new ModelPurposeDraft(initial);
        Text = "SORA · " + agent + " model purposes (draft)";
        ClientSize = new Size(800, 520); MinimumSize = new Size(640, 450);
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10); StartPosition = FormStartPosition.CenterParent;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 7,
            Padding = new Padding(12) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 95));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        accept.Text = saveDraft is null ? "Use draft" : "Save purposes";
        var notice = new Label { Text = "Describe what each model is useful for. Listed or saved IDs do not verify access. No inference or preferred-model change. " +
            "Other provider-listed models remain discoverable. " +
            (saveDraft is null ? "Use draft returns changes to Settings; Save settings persists them." : "Save purposes persists only this agent's model-purpose rows."),
            AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 0, 0, 8) };
        layout.SizeChanged += (_, _) => { notice.MaximumSize = status.MaximumSize = new Size(Math.Max(100, layout.ClientSize.Width - 32), 0); };
        layout.Controls.Add(notice, 0, 0); layout.SetColumnSpan(notice, 2);
        grid.AccessibleName = "Draft model purposes";
        grid.DefaultCellStyle.WrapMode = DataGridViewTriState.True;
        grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "model", HeaderText = "Exact model ID", FillWeight = 40 });
        grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "purpose", HeaderText = "Purpose", FillWeight = 60 });
        layout.Controls.Add(grid, 0, 1); layout.SetColumnSpan(grid, 2);
        model.Items.AddRange(listedModels.Concat(draft.Rows.Select(row => row.Id)).Distinct().ToArray());
        model.AccessibleName = "Exact model ID for purpose";
        purpose.AccessibleName = "Purpose for this model";
        layout.Controls.Add(new Label { Text = "Model ID", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 2);
        layout.Controls.Add(model, 1, 2);
        layout.Controls.Add(new Label { Text = "Purpose", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, 3);
        layout.Controls.Add(purpose, 1, 3);
        var editActions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill };
        var add = new Button { Text = "Add / update model", AutoSize = true };
        var remove = new Button { Text = "Remove selected from draft", AutoSize = true };
        editActions.Controls.AddRange([add, remove]);
        layout.Controls.Add(editActions, 0, 4); layout.SetColumnSpan(editActions, 2);
        layout.Controls.Add(status, 0, 5); layout.SetColumnSpan(status, 2);
        var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft };
        var cancel = new Button { Text = "Cancel", AutoSize = true, DialogResult = DialogResult.Cancel };
        buttons.Controls.AddRange([cancel, accept]);
        layout.Controls.Add(buttons, 0, 6); layout.SetColumnSpan(buttons, 2);
        Controls.Add(layout); CancelButton = cancel;
        grid.SelectionChanged += (_, _) => {
            if (grid.SelectedRows.Count == 1) {
                model.Text = Convert.ToString(grid.SelectedRows[0].Cells[0].Value) ?? "";
                purpose.Text = Convert.ToString(grid.SelectedRows[0].Cells[1].Value) ?? "";
            }
        };
        model.TextChanged += (_, _) => MarkEditorPending();
        purpose.TextChanged += (_, _) => MarkEditorPending();
        add.Click += (_, _) => {
            try { draft.Upsert(model.Text.Trim(), purpose.Text.Trim()); RenderRows(); }
            catch (ArgumentException error) { status.Text = error.Message; }
        };
        remove.Click += (_, _) => {
            if (grid.SelectedRows.Count == 1) {
                draft.Remove(Convert.ToString(grid.SelectedRows[0].Cells[0].Value) ?? "");
                model.Text = purpose.Text = ""; RenderRows();
            }
        };
        accept.Click += async (_, _) => {
            if (saveDraft is null) { DialogResult = DialogResult.OK; Close(); return; }
            saving = true;
            accept.Enabled = add.Enabled = remove.Enabled = model.Enabled = purpose.Enabled = grid.Enabled = cancel.Enabled = false;
            try { await saveDraft(Draft); saving = false; DialogResult = DialogResult.OK; Close(); }
            catch (Exception error) { status.Text = "Not saved; draft retained. " + error.Message; }
            finally { saving = false; if (!IsDisposed) accept.Enabled = add.Enabled = remove.Enabled = model.Enabled = purpose.Enabled = grid.Enabled = cancel.Enabled = true; }
        };
        FormClosing += (_, args) => { if (saving) args.Cancel = true; };
        RenderRows();
        Shown += (_, _) => { TopMost = Owner?.TopMost == true;
            Location = WidgetGeometry.Clamp(Screen.FromControl(Owner ?? this).WorkingArea, Size, Location); };
        ResumeLayout(true);
    }

    private void MarkEditorPending()
    {
        string id = model.Text.Trim(), description = purpose.Text.Trim();
        bool pending = (id.Length > 0 || description.Length > 0) &&
            !draft.Rows.Any(row => row.Id == id && row.Purpose == description);
        accept.Enabled = !pending;
        status.Text = pending ? "Editor changes are not in the draft yet. Click Add / update model, or Cancel." :
            $"{draft.Rows.Count}/64 model purposes in draft. Nothing saved yet.";
    }

    private void RenderRows()
    {
        grid.Rows.Clear();
        foreach (var row in draft.Rows) grid.Rows.Add(row.Id, row.Purpose);
        grid.ClearSelection(); model.Text = purpose.Text = "";
        MarkEditorPending();
    }
}

/// <summary>Schema-backed settings row: open the shared draft dialog, then save with other fields.</summary>
public sealed class ModelPurposeControl : UserControl
{
    private readonly Button edit = new() { Dock = DockStyle.Fill };
    private readonly string agent;
    private readonly Func<IEnumerable<string>> modelChoices;
    public JsonElement Value { get; private set; }
    public event EventHandler? DraftChanged;
    public event EventHandler? EditorOpening;
    public event EventHandler? EditorClosed;
    public ModelPurposeControl(string agent, JsonElement value, Func<IEnumerable<string>> modelChoices)
    {
        this.agent = agent; this.modelChoices = modelChoices; Value = value.Clone();
        Dock = DockStyle.Fill; Controls.Add(edit); UpdateLabel();
        edit.Click += (_, _) => {
            EditorOpening?.Invoke(this, EventArgs.Empty);
            try {
                using var form = new ModelPurposeForm(agent, Value, this.modelChoices());
                if (form.ShowDialog(this) != DialogResult.OK || IsDisposed) return;
                if (JsonElement.DeepEquals(form.Draft, Value)) return;
                Value = form.Draft.Clone(); UpdateLabel(); DraftChanged?.Invoke(this, EventArgs.Empty);
            } finally { EditorClosed?.Invoke(this, EventArgs.Empty); }
        };
    }
    private void UpdateLabel() => edit.Text = $"Edit {Value.GetArrayLength()} model purposes…";
    public void SetDraft(JsonElement value)
    {
        // Caller has explicitly reconciled the parent Settings draft. No Save/effect here.
        _ = new ModelPurposeDraft(value);
        Value = value.Clone(); UpdateLabel();
    }
}
