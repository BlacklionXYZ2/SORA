using System.Drawing;
using Sora.DesktopWidget;

namespace Sora.DesktopApp;

/// <summary>Sticky-note projection of Core tasks; placement never changes run status.</summary>
public sealed class KanbanBoardForm : Form
{
    private readonly IWidgetApi api;
    private readonly Func<FullAppSnapshot> current;
    private readonly Func<CancellationToken, Task<FullAppSnapshot>> refresh;
    private readonly IAgentWorkflow workflow;
    private readonly Func<bool> canUseCore;
    private readonly Func<string?> coreEpoch;
    private readonly bool hosted;
    private readonly CancellationTokenSource lifetime = new();
    private readonly List<Button> effectButtons = [];
    private BoardNoteDraft noteDraft = new();
    private bool hostShutdown, resourcesDisposed, selectorOpen, boardExpanded;
    public bool HasPendingWork => actionInProgress || selectorOpen;
    public bool IsExpanded => boardExpanded;
    public event Action<bool>? ExpandedChanged;
    private readonly FlowLayoutPanel[] lanes = [MakeLane(), MakeLane(), MakeLane()];
    private readonly TableLayoutPanel miniNotes = new() { Dock = DockStyle.Fill,
        ColumnCount = 3, BackColor = Color.FromArgb(180, 142, 99), Padding = new Padding(4) };
    private readonly Label status = new() { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
    private readonly TextBox planText = new() { Dock = DockStyle.Fill,
        PlaceholderText = "Write a task note; saving does not start an agent" };
    private readonly ComboBox assignee = new() { Width = 138, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox targetColumn = new() { Width = 132, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly Panel compact = new() { Dock = DockStyle.Fill };
    private readonly Panel expanded = new() { Dock = DockStyle.Fill, Visible = false };
    private string? selectedId;
    private string signature = "";

    public KanbanBoardForm(WidgetApiClient api, FullAppSync sync)
        : this(api, () => sync.Current, token => sync.RefreshAsync(token), sync.Workflow) { }

    public KanbanBoardForm(IWidgetApi api, Func<FullAppSnapshot> current,
        Func<CancellationToken, Task<FullAppSnapshot>> refresh, IAgentWorkflow workflow,
        bool hosted = false, Func<bool>? canUseCore = null, Func<string?>? coreEpoch = null)
    {
        this.api = api;
        this.current = current; this.refresh = refresh; this.workflow = workflow; this.hosted = hosted;
        this.canUseCore = canUseCore ?? (() => current().Companion.Connected);
        this.coreEpoch = coreEpoch ?? (() => null);
        Text = "SORA · Note board";
        StartPosition = FormStartPosition.CenterParent;
        AutoScaleMode = AutoScaleMode.Dpi;
        Size = new Size(360, 300);
        MinimumSize = new Size(320, 260);
        Font = new Font("Segoe UI", 10);
        BackColor = Color.FromArgb(55, 43, 35);
        ForeColor = Color.FromArgb(250, 244, 231);
        Controls.Add(expanded);
        Controls.Add(compact);
        BuildCompact();
        BuildExpanded();
        for (var i = 0; i < 3; i++)
            miniNotes.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f / 3));
        assignee.Items.AddRange(["Unassigned", "Sora", "Codex", "Claude", "Hermes", "Antigravity"]);
        assignee.SelectedIndex = 0;
        targetColumn.Items.AddRange(["TODO", "IN PROGRESS", "COMPLETED"]);
        targetColumn.SelectedIndex = 0;
        KeyPreview = true;
        KeyDown += (_, e) => { if (e.KeyCode == Keys.Escape && IsExpanded) { Collapse(); e.Handled = true; } };
        foreach (var lane in lanes) lane.SizeChanged += (_, _) => ResizeNotes();
        FormClosing += (_, args) => {
            if (hosted && !hostShutdown && args.CloseReason == CloseReason.UserClosing) { args.Cancel = true; Hide(); }
            else if (HasPendingWork && !hostShutdown) { args.Cancel = true; status.Text = "Wait for the pending board operation; hiding does not cancel work."; }
        };
    }

    private void BuildCompact()
    {
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2,
            Padding = new Padding(11), BackColor = Color.FromArgb(91, 65, 45) };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 39));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        compact.Controls.Add(layout);
        var title = new Button { Text = "SORA NOTES · OPEN ↗", AccessibleName = "Expand SORA note board",
            Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
            FlatStyle = FlatStyle.Flat, Font = new Font("Segoe UI Semibold", 11),
            BackColor = Color.FromArgb(91, 65, 45), ForeColor = Color.FromArgb(255, 246, 223) };
        title.Click += (_, _) => Expand();
        layout.Controls.Add(title, 0, 0);
        miniNotes.Click += (_, _) => Expand();
        layout.Controls.Add(miniNotes, 0, 1);
    }

    private void BuildExpanded()
    {
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 6,
            Padding = new Padding(12), BackColor = Color.FromArgb(91, 65, 45) };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 43));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        expanded.Controls.Add(layout);
        var heading = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        heading.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        heading.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        heading.Controls.Add(new Label { Text = "SORA'S NOTE BOARD", Dock = DockStyle.Fill,
            Font = new Font("Segoe UI Semibold", 16), ForeColor = ForeColor }, 0, 0);
        var shrink = MakeButton("Minimise ↙");
        shrink.Click += (_, _) => Collapse();
        heading.Controls.Add(shrink, 1, 0);
        layout.Controls.Add(heading, 0, 0);
        var viewport = new Panel { Dock = DockStyle.Fill, AutoScroll = true };
        var board = new TableLayoutPanel { ColumnCount = 3,
            BackColor = Color.FromArgb(180, 142, 99), Padding = new Padding(7) };
        viewport.Controls.Add(board);
        viewport.SizeChanged += (_, _) => {
            var scale = DeviceDpi / 96d;
            board.Size = new Size(Math.Max(viewport.ClientSize.Width, (int)(750 * scale)),
                Math.Max(100, viewport.ClientSize.Height - SystemInformation.HorizontalScrollBarHeight));
        };
        for (var i = 0; i < 3; i++)
        {
            board.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f / 3));
            var lane = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2,
                Padding = new Padding(5), BackColor = Color.FromArgb(199, 166, 124) };
            lane.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
            lane.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            lane.Controls.Add(new Label { Text = new[] { "TODO", "IN PROGRESS", "COMPLETED" }[i],
                Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = Color.FromArgb(57, 42, 31),
                Font = new Font("Segoe UI Semibold", 12) }, 0, 0);
            lane.Controls.Add(lanes[i], 0, 1);
            board.Controls.Add(lane, i, 0);
        }
        layout.Controls.Add(viewport, 0, 1);
        layout.Controls.Add(planText, 0, 2);
        var controls = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true,
            BackColor = Color.FromArgb(91, 65, 45) };
        var placement = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true,
            BackColor = Color.FromArgb(91, 65, 45) };
        var add = MakeButton("Add note");
        var assign = MakeButton("Assign selected");
        var move = MakeButton("Move selected");
        var remove = MakeButton("Remove selected");
        var start = MakeButton("Start planned");
        var retry = MakeButton("Retry failed");
        add.Click += async (_, _) => await PlanAsync();
        assign.Click += async (_, _) => await AssignAsync();
        move.Click += async (_, _) => await MoveAsync();
        remove.Click += async (_, _) => await RemoveAsync();
        start.Click += async (_, _) => await StartAsync();
        retry.Click += async (_, _) => await RetryAsync();
        effectButtons.AddRange([add, assign, move, remove, start, retry]);
        var restore = MakeButton("Restore submitted draft");
        restore.Click += (_, _) => {
            if (noteDraft.Intent is null) return;
            planText.Text = noteDraft.Intent;
            assignee.SelectedItem = noteDraft.Assignee == "sora" ? "Sora" :
                char.ToUpperInvariant(noteDraft.Assignee![0]) + noteDraft.Assignee[1..];
        };
        controls.Controls.AddRange([assignee, add, assign, start, retry]);
        placement.Controls.AddRange([targetColumn, move, remove, restore]);
        layout.Controls.Add(controls, 0, 3);
        layout.Controls.Add(placement, 0, 4);
        status.ForeColor = Color.FromArgb(255, 238, 211);
        status.AutoSize = true;
        layout.Controls.Add(status, 0, 5);
    }

    private void Expand()
    {
        SetExpanded(true);
    }

    private void Collapse()
    {
        SetExpanded(false);
    }

    public void SetExpanded(bool value, bool notify = true)
    {
        boardExpanded = value;
        expanded.Visible = value; compact.Visible = !value;
        var scale = DeviceDpi / 96d; var area = Screen.FromControl(this).WorkingArea;
        MinimumSize = new Size(Math.Min((int)(320 * scale), area.Width), Math.Min((int)(260 * scale), area.Height));
        Size = new Size(Math.Min((int)((value ? 1120 : 360) * scale), area.Width),
            Math.Min((int)((value ? 700 : 300) * scale), area.Height));
        Location = new Point(Math.Clamp(Left, area.Left, Math.Max(area.Left, area.Right - Width)),
            Math.Clamp(Top, area.Top, Math.Max(area.Top, area.Bottom - Height)));
        Render(current(), force: true);
        if (notify) ExpandedChanged?.Invoke(value);
    }

    private void ResizeNotes()
    {
        foreach (var lane in lanes) foreach (Control note in lane.Controls)
            note.Width = Math.Max(60, lane.ClientSize.Width - SystemInformation.VerticalScrollBarWidth - 10);
    }

    public void Render(FullAppSnapshot snapshot, bool force = false)
    {
        if (resourcesDisposed) return;
        var available = snapshot.Companion.Connected && canUseCore() && !actionInProgress && !selectorOpen;
        foreach (var button in effectButtons) button.Enabled = available;
        if (!snapshot.Companion.Connected || !canUseCore()) status.Text = "Stale/offline · cached notes only; no changes available.";
        var next = string.Join('|', snapshot.BoardCards.Select(card =>
            card.Id + card.Column + card.Status + card.Description + card.AssignedAgent +
            card.BoardVersion + card.RunCount + card.NeedsAttention))
            + boardExpanded + SystemInformation.HighContrast;
        if (!force && next == signature) return;
        signature = next;
        var focusedNote = lanes.SelectMany(lane => lane.Controls.Cast<Control>()).FirstOrDefault(note => note.Focused)?.Tag as string;
        foreach (var lane in lanes) ClearControls(lane);
        ClearControls(miniNotes);
        foreach (var card in snapshot.BoardCards)
        {
            var index = LaneIndex(card.Column);
            var badge = card.AssignedAgent ?? "Unassigned";
            var run = card.Status.Replace('_', ' ');
            var summary = card.Description.Length > 80 ? card.Description[..80] + "…" : card.Description;
            var text = $"{summary}\n\n{badge} · run: {run}";
            if (card.ManuallyPlaced) text += " · moved note";
            if (card.NeedsAttention) text += " · needs attention";
            var note = new Button { Text = text, Tag = card.Id, Width = 300, Height = (int)(168 * DeviceDpi / 96d),
                TextAlign = ContentAlignment.TopLeft, Padding = new Padding(8),
                BackColor = NoteColor(card.AssignedAgent), ForeColor = SystemInformation.HighContrast ? SystemColors.WindowText : Color.FromArgb(39, 37, 40),
                FlatStyle = FlatStyle.Flat, AccessibleName = $"{card.Description}; assigned {badge}; run {run}" };
            note.FlatAppearance.BorderColor = card.Id == selectedId
                ? SystemInformation.HighContrast ? SystemColors.Highlight : Color.FromArgb(31, 45, 70)
                : SystemInformation.HighContrast ? SystemColors.WindowText : Color.FromArgb(143, 121, 91);
            note.FlatAppearance.BorderSize = card.Id == selectedId ? 3 : 1;
            note.Click += (_, _) => { selectedId = card.Id; Render(current(), force: true); };
            lanes[index].Controls.Add(note);
            if (card.Id == focusedNote) note.Focus();
        }
        for (var i = 0; i < 3; i++)
        {
            var column = new[] { "TODO", "DOING", "DONE" }[i];
            var count = snapshot.BoardCards.Count(card => card.Column == column);
            var first = snapshot.BoardCards.FirstOrDefault(card => card.Column == column);
            var mini = new Label { Dock = DockStyle.Fill, Margin = new Padding(2),
                Padding = new Padding(5), BackColor = first is null
                    ? SystemInformation.HighContrast ? SystemColors.Window : Color.FromArgb(243, 230, 193) : NoteColor(first.AssignedAgent),
                ForeColor = SystemInformation.HighContrast ? SystemColors.WindowText : Color.FromArgb(44, 39, 34),
                Text = $"{new[] { "TODO", "DOING", "DONE" }[i]} ({count})\n\n" +
                    (first is null ? "" : first.Description[..Math.Min(35, first.Description.Length)]),
                TextAlign = ContentAlignment.TopLeft };
            mini.Click += (_, _) => Expand();
            miniNotes.Controls.Add(mini, i, 0);
        }
        ResizeNotes();
        if (!actionInProgress) status.Text = available
            ? $"{snapshot.BoardCards.Count} notes · placement is separate from run status"
            : "Offline · showing last canonical snapshot";
    }

    private FullBoardCard? SelectedCard() =>
        current().BoardCards.FirstOrDefault(card => card.Id == selectedId);

    private async Task PlanAsync()
    {
        var intent = planText.Text.Trim();
        if (intent.Length is < 1 or > 4000)
        { status.Text = "Enter a description of 1–4,000 characters."; return; }
        await RunAsync(async () => {
            var agent = SelectedAgent(); noteDraft.Begin(intent, agent, coreEpoch());
            if (noteDraft.TaskId is null) {
                var response = await api.PostAsync("/api/v1/board/cards", new {
                    intent, idempotency_key = noteDraft.Key
                }, lifetime.Token);
                noteDraft.Acknowledge(response.GetProperty("task_id").GetString() ?? "");
            }
            var taskId = noteDraft.TaskId!;
            selectedId = taskId;
            if (agent != "unassigned") {
                var latest = await refresh(lifetime.Token);
                noteDraft.Begin(intent, agent, coreEpoch());
                if (!latest.Companion.Connected) throw new InvalidOperationException("Note admitted but the canonical board is stale; assignment draft retained.");
                var card = latest.BoardCards.SingleOrDefault(item => item.Id == taskId)
                    ?? throw new InvalidOperationException("Note admitted but refresh cannot confirm its assignment; draft retained.");
                if (card.AssignedAgent != agent) {
                    if (card.BoardVersion != 0) throw new InvalidOperationException("Note admitted, but assignment changed elsewhere. Inspect it before assigning manually; draft retained.");
                    await api.PostAsync(FullAppProjection.BoardPath(taskId, "assign"),
                        new { assigned_agent = agent, expected_version = 0 }, lifetime.Token);
                }
            }
            noteDraft.Begin(intent, agent, coreEpoch()); noteDraft.Confirm(); noteDraft = new();
            if (planText.Text.Trim() == intent && SelectedAgent() == agent) planText.Clear();
            Render(await refresh(lifetime.Token), force: true);
        }, "Note saved; no agent run was started.");
    }

    private async Task AssignAsync()
    {
        var card = SelectedCard();
        if (card is null) { status.Text = "Select a note first."; return; }
        await EditAsync(card, "assign", new { assigned_agent = SelectedAgent(),
            expected_version = card.BoardVersion },
            "Assignment changed; no agent run was started.");
    }

    private async Task MoveAsync()
    {
        var card = SelectedCard();
        if (card is null) { status.Text = "Select a note first."; return; }
        var next = targetColumn.SelectedIndex switch { 1 => "DOING", 2 => "DONE", _ => "TODO" };
        var name = next switch { "DOING" => "IN PROGRESS", "DONE" => "COMPLETED", _ => "TODO" };
        if (MessageBox.Show(this, $"Move this note to {name}? The agent run status will not change.",
            "Move note", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        await EditAsync(card, "move", new { column = next,
            expected_version = card.BoardVersion }, $"Moved to {name}; run status unchanged.");
    }

    private async Task RemoveAsync()
    {
        var card = SelectedCard();
        if (card is null) { status.Text = "Select a note first."; return; }
        if (MessageBox.Show(this, "Remove this note from the board? The task and run history will be kept.",
            "Remove note", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        await EditAsync(card, "remove", new { expected_version = card.BoardVersion },
            "Note hidden; task and run history retained.");
    }

    private async Task EditAsync(FullBoardCard card, string action, object body, string success)
    {
        await RunAsync(async () => {
            await api.PostAsync(FullAppProjection.BoardPath(card.Id, action), body, lifetime.Token);
            if (action == "remove" && selectedId == card.Id) selectedId = null;
            Render(await refresh(lifetime.Token), force: true);
        }, success);
    }

    private async Task StartAsync()
    {
        var card = SelectedCard();
        if (card is null || card.Status != "planned")
        { status.Text = "Select a planned note."; return; }
        if (card.AssignedAgent == "claude")
        { status.Text = "Claude is a board assignment, but no Claude provider is registered here."; return; }
        if (HasPendingWork || !canUseCore()) { status.Text = "Connect the matching Core and wait for pending work."; return; }
        using var selector = new AgentCatalogueForm(workflow, card.Description,
            plannedTaskId: card.Id, canUseCore: canUseCore);
        selectorOpen = true; Render(current());
        try { if (selector.ShowDialog(this) != DialogResult.OK) return; }
        finally { selectorOpen = false; Render(current()); }
        await RunAsync(async () => {
            Render(await refresh(lifetime.Token), force: true);
        }, "Run admitted under this note; inspect Activity for execution/results.");
    }

    private async Task RetryAsync()
    {
        var card = SelectedCard();
        if (card is null || card.Status is not ("failed" or "cancelled" or "interrupted"))
        { status.Text = "Select a failed, cancelled or interrupted note."; return; }
        if (MessageBox.Show(this, "Retry this task? Earlier runs remain in history.",
            "Retry work", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        await EditAsync(card, "retry", new { }, "Retry admitted; earlier runs retained. Inspect Activity for execution/results.");
    }

    private bool actionInProgress;

    private async Task RunAsync(Func<Task> action, string success)
    {
        if (HasPendingWork || !canUseCore()) { status.Text = "Connect the matching Core and wait for the current board change."; return; }
        actionInProgress = true;
        Render(current());
        status.Text = "Saving…";
        try { await action(); if (!resourcesDisposed) status.Text = success; }
        catch (Exception error) { if (!resourcesDisposed) status.Text = "Change not fully confirmed; inspect the board before retry. " + error.Message; }
        finally { actionInProgress = false; if (!resourcesDisposed) foreach (var button in effectButtons) button.Enabled = canUseCore() && current().Companion.Connected; }
    }

    public void CloseForHostShutdown() { hostShutdown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed) { resourcesDisposed = true; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }

    private string SelectedAgent() => (assignee.SelectedItem?.ToString() ?? "Unassigned").ToLowerInvariant();
    private static int LaneIndex(string column) => column switch { "TODO" => 0, "DOING" => 1, _ => 2 };
    public void RefreshBoardAppearance()
    {
        if (SystemInformation.HighContrast) {
            void Apply(Control control) {
                control.BackColor = SystemColors.Window; control.ForeColor = SystemColors.WindowText;
                foreach (Control child in control.Controls) Apply(child);
            }
            Apply(this);
        }
        else {
            void Apply(Control control) {
                if (control is not TextBox and not ComboBox) {
                    control.BackColor = control is Button ? Color.FromArgb(75, 66, 75) : Color.FromArgb(91, 65, 45);
                    control.ForeColor = Color.FromArgb(250, 244, 231);
                }
                foreach (Control child in control.Controls) Apply(child);
            }
            Apply(this);
            foreach (var lane in lanes) lane.BackColor = Color.FromArgb(199, 166, 124);
        }
        Render(current(), force: true);
    }
    private static Color NoteColor(string? agent) => SystemInformation.HighContrast ? SystemColors.Window : agent?.ToLowerInvariant() switch {
        "codex" => Color.FromArgb(174, 211, 245),
        "claude" => Color.FromArgb(247, 190, 145),
        "hermes" => Color.FromArgb(206, 183, 237),
        "antigravity" => Color.FromArgb(174, 226, 183),
        "sora" => Color.FromArgb(249, 184, 206),
        _ => Color.FromArgb(250, 236, 175),
    };
    private static FlowLayoutPanel MakeLane() => new() { Dock = DockStyle.Fill,
        FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true,
        BackColor = Color.FromArgb(199, 166, 124) };
    private static void ClearControls(Control parent)
    {
        while (parent.Controls.Count > 0) parent.Controls[0].Dispose();
    }
    private static Button MakeButton(string text) => new() { Text = text, AutoSize = true,
        Height = 34, BackColor = Color.FromArgb(75, 66, 75), ForeColor = Color.White };
}
