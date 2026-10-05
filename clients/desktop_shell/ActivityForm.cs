using Sora.DesktopWidget;

namespace Sora.DesktopShell;

// No panel timer/state transport. The profile session owns the canonical
// task list; evidence is read only on explicit selection/refresh.
internal sealed class ActivityForm : Form
{
    private readonly ShellSession session;
    private readonly RunHistoryControl history;
    private WidgetTask? pinned;
    private readonly Func<Task> refresh;
    private readonly CancellationTokenSource lifetime = new();
    private readonly DataGridView tasks = new() { Dock = DockStyle.Fill, ReadOnly = true,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, MultiSelect = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect, AccessibleName = "Canonical specialist tasks" };
    private readonly RichTextBox evidence = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false,
        AccessibleName = "Selected task result and coverage", Text = "Select a task and open its evidence." };
    private readonly TextBox steerText = new() { Dock = DockStyle.Fill, Multiline = true, MaxLength = 8000,
        AccessibleName = "Steering instruction for selected task", PlaceholderText = "Instruction for the selected task (not Chat)" };
    private readonly Label status = new() { AutoSize = true, Dock = DockStyle.Fill };
    private readonly Button read = ShellTheme.Button("Open / refresh evidence", "Read selected task evidence");
    private readonly Button cancel = ShellTheme.Button("Cancel task", "Cancel selected specialist task, not Chat response");
    private readonly Button steer = ShellTheme.Button("Send instruction", "Steer selected specialist task");
    private IReadOnlyList<WidgetTask> rendered = [];
    private string? evidenceId;
    private int selectionRevision, draftRevision, readRevision;
    private bool rendering, shuttingDown, resourcesDisposed;
    private string operation = "", lastEpoch = "";

    public ActivityForm(ShellSession session, Func<Task> refresh)
    {
        this.session = session; this.refresh = refresh; history = new RunHistoryControl(session);
        Text = "SORA · Activity and task evidence"; Font = new Font("Segoe UI", 10.5f);
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(920, 700); MinimumSize = new Size(600, 480);
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(16), RowCount = 6, ColumnCount = 1 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 40));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 60));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 70)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.Controls.Add(new Label { AutoSize = true, Text = "Specialist work is independent of Chat. Closing this panel does not cancel a task." }, 0, 0);
        foreach (var name in new[] { "Task", "State", "Agent", "Result reference" }) tasks.Columns.Add(name, name);
        tasks.SelectionChanged += (_, _) => {
            if (rendering) return;
            selectionRevision++; evidenceId = null;
            evidence.Text = "Evidence has not been read for this selection."; history.SetTask(SelectedId); Render();
        };
        var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill };
        var exactId = new TextBox { Width = 230, MaxLength = 128, AccessibleName = "Exact task ID outside the latest task list",
            PlaceholderText = "Exact task ID" };
        var find = ShellTheme.Button("Inspect task ID", "Read exact task even outside latest 100 tasks");
        find.Click += async (_, _) => {
            try { await SelectTaskAsync(exactId.Text.Trim()); }
            catch (ArgumentException error) { operation = "Task target invalid: " + error.Message; Render(); }
        };
        var reload = ShellTheme.Button("Refresh task list", "Refresh shared Core state");
        reload.Click += async (_, _) => await refresh();
        read.Click += async (_, _) => await ReadAsync();
        cancel.Click += async (_, _) => await ControlAsync("cancel");
        steer.Click += async (_, _) => await ControlAsync("steer");
        steerText.TextChanged += (_, _) => { draftRevision++; Render(); };
        actions.Controls.AddRange([reload, read, cancel, steer, exactId, find]);
        var views = new TabControl { Dock = DockStyle.Fill, AccessibleName = "Task evidence and complete attempt history" };
        var latest = new TabPage("Latest task evidence"); latest.Controls.Add(evidence);
        var attempts = new TabPage("All attempts / files"); attempts.Controls.Add(history); views.TabPages.AddRange([latest, attempts]);
        root.Controls.Add(tasks, 0, 1); root.Controls.Add(actions, 0, 2); root.Controls.Add(views, 0, 3);
        root.Controls.Add(steerText, 0, 4); root.Controls.Add(status, 0, 5); Controls.Add(root);
        session.Changed += SessionChanged; ShellTheme.Apply(this); Render();
        FormClosing += (_, args) => { if (!shuttingDown) { args.Cancel = true; Hide(); } };
        Resize += (_, _) => status.MaximumSize = new Size(Math.Max(100, ClientSize.Width - 40), 0);
    }
    private string? SelectedId => tasks.SelectedRows.Count == 1 ? tasks.SelectedRows[0].Tag as string : null;
    private void SessionChanged(object? sender, EventArgs args) { if (!IsDisposed) Render(); }
    private void Render()
    {
        if (lastEpoch != (session.CoreInstanceId ?? ""))
        {
            lastEpoch = session.CoreInstanceId ?? ""; selectionRevision++; evidenceId = null; pinned = null;
            evidence.Text = "Core instance changed; select and read current task evidence.";
        }
        var list = session.Snapshot.Tasks.ToList();
        if (pinned is not null && list.All(task => task.Id != pinned.Id)) list.Add(pinned);
        var selected = SelectedId;
        if (!rendered.SequenceEqual(list))
        {
            rendering = true;
            try
            {
                tasks.Rows.Clear();
                foreach (var task in list) { var row = tasks.Rows.Add(task.Id, task.Status, task.Backend, task.ResultRef ?? "Not stored"); tasks.Rows[row].Tag = task.Id; }
                tasks.ClearSelection();
                foreach (DataGridViewRow row in tasks.Rows) if ((string?)row.Tag == selected) row.Selected = true;
                if (selected is not null && SelectedId is null) { selectionRevision++; evidenceId = null; evidence.Text = "Previously selected task is not in the current bounded list."; }
                rendered = list.ToArray();
            }
            finally { rendering = false; }
        }
        history.SetTask(SelectedId);
        var choice = list.FirstOrDefault(task => task.Id == SelectedId);
        var ready = session.CanUseCore && !session.MutationBusy;
        read.Enabled = session.CanUseCore && choice is not null;
        cancel.Enabled = ready && choice is not null && TaskPresentation.CanControl(choice.Status, "cancel");
        steer.Enabled = ready && choice is not null && TaskPresentation.CanControl(choice.Status, "steer") && !string.IsNullOrWhiteSpace(steerText.Text);
        status.Text = (!session.Snapshot.Connected ? "Core unavailable · list/evidence are last-known and stale; controls disabled."
            : !session.CanUseCore ? "Host lifecycle blocks task actions."
            : session.MutationBusy ? "Waiting for task/settings acknowledgement; no automatic replay."
            : "Latest 100 tasks plus exact-ID inspection · model readiness is not required for task control. " + (evidenceId is null ? "" : "Evidence shown for " + evidenceId))
            + (operation.Length > 0 ? "\n" + operation : "");
    }
    public async Task SelectTaskAsync(string id)
    {
        _ = TaskPresentation.Path(id); var version = ++selectionRevision;
        rendering = true;
        try { tasks.ClearSelection(); } finally { rendering = false; }
        history.SetTask(null); evidenceId = null; evidence.Text = "Resolving exact task " + id + "; no substitute task selected."; Render();
        try {
            var data = await session.TaskEvidenceAsync(id, lifetime.Token);
            if (IsDisposed || selectionRevision != version) return;
            var task = data.GetProperty("task");
            pinned = new WidgetTask(id, TaskPresentation.Text(task, "status"), TaskPresentation.Text(task, "effective_backend"),
                TaskPresentation.Text(task, "result_ref", ""));
            Render(); rendering = true;
            try { tasks.ClearSelection(); foreach (DataGridViewRow row in tasks.Rows) if ((string?)row.Tag == id) row.Selected = true; }
            finally { rendering = false; }
            history.SetTask(id); evidence.Text = TaskPresentation.Evidence(id, data); evidenceId = id; Render();
        }
        catch (Exception error) { if (!IsDisposed && selectionRevision == version) {
            tasks.ClearSelection(); history.SetTask(null); evidenceId = null; evidence.Text = "Requested task was not resolved; no substitute task selected.";
            operation = "Exact requested task unavailable: " + error.Message; Render();
        } }
    }
    private async Task ReadAsync()
    {
        var id = SelectedId; var revision = selectionRevision; var readRequest = ++readRevision; if (id is null) return;
        try
        {
            var result = await session.TaskEvidenceAsync(id, lifetime.Token);
            if (IsDisposed || SelectedId != id || selectionRevision != revision || readRevision != readRequest) return;
            evidence.Text = TaskPresentation.Evidence(id, result); evidenceId = id; Render();
        }
        catch (Exception error) { if (!IsDisposed && SelectedId == id && selectionRevision == revision && readRevision == readRequest) evidence.Text = "Evidence unavailable: " + error.Message; }
    }
    private async Task ControlAsync(string action)
    {
        var id = SelectedId; if (id is null || session.MutationBusy) return;
        var instruction = steerText.Text; var revision = draftRevision;
        if (MessageBox.Show(this, action == "cancel" ? $"Request cancellation of task {id}? This is not Stop response or Undo."
            : $"Send the entered instruction to task {id}?", "SORA · task control", MessageBoxButtons.YesNo,
            MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
        try
        {
            var result = await session.ControlTaskAsync(id, action, instruction, lifetime.Token);
            if (IsDisposed) return;
            var accepted = result.TryGetProperty(action == "cancel" ? "cancelled" : "steered", out var value) && value.ValueKind == System.Text.Json.JsonValueKind.True;
            if (accepted && action == "steer" && revision == draftRevision) steerText.Clear();
            operation = accepted ? "Core acknowledged task " + id + " " + action + "; check its subsequent state." : "Core did not acknowledge a task change; no automatic retry.";
            Render();
            await refresh();
        }
        catch (Exception error) { if (!IsDisposed) { operation = "Task control not confirmed. Instruction retained; no automatic retry. " + error.Message; Render(); } }
    }
    public void CloseForHostShutdown() { shuttingDown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed) { resourcesDisposed = true; session.Changed -= SessionChanged; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }
}
