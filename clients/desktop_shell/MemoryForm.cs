using Sora.DesktopWidget;

namespace Sora.DesktopShell;

// One host session; bounded explicit reads and process-local selection/cache, never a memory store.
internal sealed class MemoryForm : Form
{
    private readonly ShellSession session;
    private readonly MemoryBrowserState model = new();
    private readonly CancellationTokenSource lifetime = new();
    private readonly List<string?> cursors = [null];
    private readonly TextBox query = new() { Width = 240, MaxLength = 256, PlaceholderText = "Search remembered words",
        AccessibleName = "Literal canonical memory content search" };
    private readonly TextBox scope = new() { Width = 125, MaxLength = 128, PlaceholderText = "Any scope",
        AccessibleName = "Exact memory scope filter, blank for all scopes" };
    private readonly ComboBox state = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 125, AccessibleName = "Memory state filter" };
    private readonly ComboBox project = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 165, AccessibleName = "Current project or owner-global memories" };
    private readonly TextBox exact = new() { Width = 220, MaxLength = 128, PlaceholderText = "Exact memory ID", AccessibleName = "Exact canonical memory ID" };
    private readonly DataGridView records = new() { Dock = DockStyle.Fill, ReadOnly = true, RowHeadersVisible = false,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
        MultiSelect = false, SelectionMode = DataGridViewSelectionMode.FullRowSelect, AccessibleName = "Canonical memories, newest storage admissions first" };
    private readonly RichTextBox detail = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false,
        AccessibleName = "Exact selected memory content, metadata and provenance" };
    private readonly ListBox evidence = new() { Dock = DockStyle.Fill, IntegralHeight = false, AccessibleName = "Current registered memory evidence references" };
    private readonly Label status = new() { AutoSize = false, Dock = DockStyle.Fill, AutoEllipsis = true,
        MinimumSize = new Size(100, 72), AccessibleName = "Memory page freshness and operation outcome" };
    private readonly ToolTip statusTip = new();
    private readonly Label heading = new() { AutoSize = true, Dock = DockStyle.Fill, Text = "MEMORY · Overview" };
    private readonly Button refresh = ShellTheme.Button("Refresh / search", "Read first canonical Memory page with these filters");
    private readonly Button previous = ShellTheme.Button("Previous", "Read the previous Memory page");
    private readonly Button next = ShellTheme.Button("Next", "Read the next older Memory page");
    private readonly Button inspect = ShellTheme.Button("Inspect selection", "Read the exact selected canonical Memory record");
    private readonly Button inspectId = ShellTheme.Button("Inspect ID", "Read the exact entered ID without substituting another memory");
    private readonly Button open = ShellTheme.Button("Open registered evidence", "Revalidate exact memory and open its current registered evidence through Core");
    private readonly Button correct = ShellTheme.Button("Correct…", "Draft a correction of this exact active record");
    private readonly Button forget = ShellTheme.Button("Forget…", "Forget only this exact canonical record, not captures or backups");
    private readonly Button saveEdit = ShellTheme.Button("Save correction", "Commit the retained exact-version correction");
    private readonly Button discardEdit = ShellTheme.Button("Discard draft", "Explicitly discard this process-local memory draft");
    private readonly Button reviewEdit = ShellTheme.Button("Review latest", "Read and explicitly review the same record's latest version");
    private readonly Button resolveEdit = ShellTheme.Button("Check receipt", "Read historical confirmation without repeating a mutation");
    private readonly Button retryEdit = ShellTheme.Button("Retry same request", "Explicitly retry the frozen idempotent request");
    private readonly TextBox editText = new() { Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill,
        MaxLength = 32768, AccessibleName = "Retained exact-version memory correction draft" };
    private readonly Label editTarget = new() { AutoSize = true, AccessibleName = "Pinned memory draft identity and version" };
    private readonly TableLayoutPanel editPanel = new() { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3,
        Visible = false, Height = 190, MinimumSize = new Size(0, 160) };
    private MemoryEditDraft? editDraft;
    private bool editingText, mutating, modal;
    private readonly TableLayoutPanel body = new() { Dock = DockStyle.Fill };
    private readonly TableLayoutPanel inspector = new() { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, Padding = new Padding(8) };
    private bool rendering, reading, navigating, disposed, shutdown, stacked;
    private int pageIndex;
    private string message = "Refresh to browse SORA's canonical memories. No model call is needed.";
    private MemoryDetailView? evidenceFor;
    private bool presenting, showWithoutActivation;
    private DateTimeOffset lastDismissal = DateTimeOffset.MinValue;
    private (string Id, long Version, string Epoch)? highlighted;
    private Guid? highlightedRequest;
    private DateTimeOffset highlightDeadline;
    public event EventHandler? PresentationChanged;
    protected override bool ShowWithoutActivation => showWithoutActivation;
    public bool HasPendingWork => navigating || mutating || modal || presenting;
    public bool HasUnsavedChanges => editDraft is { Confirmed: null };
    private sealed record EvidenceRow(MemoryLink Link)
    { public override string ToString() => Link.Label + " · " + Link.Kind + " · " + Link.Id; }

    public MemoryForm(ShellSession session)
    {
        this.session = session; session.EnableRetained();
        Text = "SORA · Memory"; AccessibleName = "SORA canonical Memory browser";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f); ClientSize = new Size(1060, 740); MinimumSize = new Size(620, 520);
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5, Padding = new Padding(16), AutoScroll = true };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var modes = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        var overview = ShellTheme.Button("Overview", "Browse active canonical memories");
        var search = ShellTheme.Button("Search", "Focus literal Memory search");
        var graph = ShellTheme.Button("Graph · not yet available", "Canonical relationship graph is not yet implemented");
        graph.Enabled = false;
        overview.Click += async (_, _) => {
            if (reading || HasPendingWork || editDraft is not null) return;
            query.Clear(); scope.Clear(); state.SelectedIndex = 0; project.SelectedIndex = 0;
            heading.Text = "MEMORY · Overview"; await ReadPageAsync(null, 0);
        };
        search.Click += (_, _) => { heading.Text = "MEMORY · Search"; query.Focus(); };
        modes.Controls.AddRange([heading, overview, search, graph]);
        state.Items.AddRange(["active", "expired", "superseded", "all"]); state.SelectedIndex = 0;
        project.Items.AddRange(["Project + owner-global", "Current project only", "Owner-global only"]); project.SelectedIndex = 0;
        var filters = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        filters.Controls.AddRange([new Label { AutoSize = true, Text = "Words" }, query,
            new Label { AutoSize = true, Text = "State" }, state, project, scope, refresh]);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        actions.Controls.AddRange([previous, next, inspect, exact, inspectId, correct, forget]);
        foreach (var column in new[] { "Remembered words", "State", "Version", "Scope" }) records.Columns.Add(column, column);
        records.Columns[0].FillWeight = 65; records.Columns[1].FillWeight = 15;
        records.Columns[2].FillWeight = 8; records.Columns[3].FillWeight = 12;
        records.DefaultCellStyle.WrapMode = DataGridViewTriState.True;
        inspector.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        inspector.RowStyles.Add(new RowStyle(SizeType.Percent, 78)); inspector.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        inspector.RowStyles.Add(new RowStyle(SizeType.Percent, 22)); inspector.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        inspector.Controls.Add(detail, 0, 0); inspector.Controls.Add(new Label { AutoSize = true, Text = "Registered evidence · no capture scratchpads" }, 0, 1);
        inspector.Controls.Add(evidence, 0, 2); inspector.Controls.Add(open, 0, 3);
        inspector.RowCount = 5; inspector.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        editPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        editPanel.RowStyles.Add(new RowStyle(SizeType.AutoSize)); editPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        editPanel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var editActions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        editActions.Controls.AddRange([saveEdit, discardEdit, reviewEdit, resolveEdit, retryEdit]);
        editPanel.Controls.Add(editTarget, 0, 0); editPanel.Controls.Add(editText, 0, 1); editPanel.Controls.Add(editActions, 0, 2);
        inspector.Controls.Add(editPanel, 0, 4);
        root.Controls.Add(modes, 0, 0); root.Controls.Add(filters, 0, 1); root.Controls.Add(actions, 0, 2);
        root.Controls.Add(body, 0, 3); root.Controls.Add(status, 0, 4); Controls.Add(root);
        refresh.Click += async (_, _) => await ReadPageAsync(null, 0);
        previous.Click += async (_, _) => { if (pageIndex > 0) await ReadPageAsync(cursors[pageIndex - 1], pageIndex - 1); };
        next.Click += async (_, _) => { if (model.PageCurrent && model.Page?.NextCursor is { } cursor) await ReadPageAsync(cursor, pageIndex + 1); };
        inspect.Click += async (_, _) => { if (model.SelectedId is { } id) await InspectAsync(id); };
        inspectId.Click += async (_, _) => await InspectAsync(exact.Text.Trim());
        query.KeyDown += async (_, e) => { if (e.KeyCode == Keys.Enter) { e.Handled = true; e.SuppressKeyPress = true; await ReadPageAsync(null, 0); } };
        query.TextChanged += (_, _) => FiltersChanged(); scope.TextChanged += (_, _) => FiltersChanged();
        exact.TextChanged += (_, _) => UpdateAvailability();
        state.SelectedIndexChanged += (_, _) => FiltersChanged(); project.SelectedIndexChanged += (_, _) => FiltersChanged();
        records.SelectionChanged += async (_, _) => {
            if (rendering) return;
            var id = records.SelectedRows.Count == 1 ? records.SelectedRows[0].Tag as string : null;
            model.Select(id); RenderInspection(); UpdateAvailability();
            if (id is not null && !reading && !navigating) await InspectAsync(id);
        };
        evidence.SelectedIndexChanged += (_, _) => UpdateAvailability();
        open.Click += async (_, _) => await OpenEvidenceAsync();
        correct.Click += (_, _) => StartCorrection();
        forget.Click += async (_, _) => await ForgetAsync();
        saveEdit.Click += async (_, _) => await SubmitEditAsync("correct");
        retryEdit.Click += async (_, _) => { if (editDraft?.Pending is { } request) await SubmitEditAsync(request.Action); };
        resolveEdit.Click += async (_, _) => await ResolveEditAsync();
        reviewEdit.Click += async (_, _) => await ReviewEditAsync();
        discardEdit.Click += (_, _) => DiscardDraft();
        editText.TextChanged += (_, _) => { if (!editingText && editDraft is not null && editDraft.Pending is null) editDraft.Edit(editText.Text); UpdateAvailability(); };
        session.Changed += HostChanged;
        FormClosing += (_, e) => { if (!shutdown && e.CloseReason == CloseReason.UserClosing) {
            e.Cancel = true; lastDismissal = DateTimeOffset.UtcNow; ClearHighlight(); Hide(); } };
        Resize += (_, _) => { ClearHighlight(); Responsive(); status.MaximumSize = new Size(Math.Max(220, ClientSize.Width - 40), 0); };
        LocationChanged += (_, _) => ClearHighlight();
        DpiChanged += (_, _) => ClearHighlight();
        detail.VScroll += (_, _) => ClearHighlight(); detail.HScroll += (_, _) => ClearHighlight();
        VisibleChanged += (_, _) => ClearHighlight();
        Responsive(force: true); ShellTheme.Apply(this); HostChanged(null, EventArgs.Empty);
    }
    private MemoryQuery CurrentQuery => new(query.Text, state.SelectedItem?.ToString() ?? "active",
        project.SelectedIndex == 1 ? "project" : project.SelectedIndex == 2 ? "global" : "all", scope.Text);
    private void Responsive(bool force = false)
    {
        var narrow = ClientSize.Width < 860 * DeviceDpi / 96;
        if (!force && narrow == stacked) return;
        stacked = narrow; body.SuspendLayout(); body.Controls.Clear(); body.ColumnStyles.Clear(); body.RowStyles.Clear();
        body.ColumnCount = narrow ? 1 : 2; body.RowCount = narrow ? 2 : 1;
        body.MinimumSize = new Size(0, narrow ? 280 : 180);
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, narrow ? 100 : 44));
        if (!narrow) body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 56));
        body.RowStyles.Add(new RowStyle(SizeType.Percent, narrow ? 42 : 100));
        if (narrow) body.RowStyles.Add(new RowStyle(SizeType.Percent, 58));
        body.Controls.Add(records, 0, 0); body.Controls.Add(inspector, narrow ? 0 : 1, narrow ? 1 : 0); body.ResumeLayout();
    }
    private void FiltersChanged()
    {
        ClearHighlight();
        model.Invalidate(); message = "Filters changed · Refresh/search to read matching records; any displayed page is stale.";
        RenderInspection(); UpdateAvailability();
    }
    public void OnUserOpen()
    {
        HostChanged(null, EventArgs.Empty);
        if (model.Page is null && !reading && session.CanUseCore) _ = ReadPageAsync(null, 0);
    }
    private void HostChanged(object? sender, EventArgs args)
    {
        if (disposed) return;
        if (highlighted is not null && DateTimeOffset.UtcNow >= highlightDeadline) ClearHighlight();
        var old = model.Page; model.Observe(session.CoreInstanceId, session.CanUseCore);
        if (old is not null && model.Page is null) {
            rendering = true; try { records.Rows.Clear(); } finally { rendering = false; }
            cursors.Clear(); cursors.Add(null); pageIndex = 0;
            message = "Core instance changed · Refresh before browsing this Core's memories.";
        }
        RenderInspection(); UpdateAvailability();
    }
    private void RenderInspection()
    {
        if (highlighted is { } target && (!model.DetailCurrent || model.Detail is not { } current
            || current.Item.Id != target.Id || current.Item.Version != target.Version || current.Epoch != target.Epoch)) ClearHighlight();
        var text = model.Detail is { } value ? (model.DetailCurrent ? "" : "STALE / UNCONFIRMED CACHE\r\n\r\n") + MemoryPresentation.Inspection(value)
            : model.SelectedId is { } id ? id + "\r\nInspect this exact record. No other memory is substituted."
            : "Select a memory to inspect its content and provenance.\r\n\r\nCorrections create a successor. Forgetting affects only the exact record, not captures/backups. Semantic selection requires a current host acknowledgement; model/Chat integration is still in development.";
        if (detail.Text != text) detail.Text = text;
        if (!model.DetailCurrent || model.Detail is null) { evidence.Items.Clear(); evidenceFor = null; }
        else if (!ReferenceEquals(evidenceFor, model.Detail)) {
            var selected = (evidence.SelectedItem as EvidenceRow)?.Link.Id;
            evidence.Items.Clear();
            foreach (var link in model.Detail.Evidence) {
                var index = evidence.Items.Add(new EvidenceRow(link));
                if (link.Id == selected) evidence.SelectedIndex = index;
            }
            evidenceFor = model.Detail;
        }
    }
    private void UpdateAvailability()
    {
        var ready = session.CanUseCore && !reading && !HasPendingWork;
        var browsing = ready && editDraft is null;
        refresh.Enabled = browsing; inspectId.Enabled = browsing && exact.Text.Trim().Length > 0;
        inspect.Enabled = browsing && model.SelectedId is not null;
        previous.Enabled = browsing && model.PageCurrent && pageIndex > 0;
        next.Enabled = browsing && model.PageCurrent && model.Page?.NextCursor is not null && pageIndex < 255;
        records.Enabled = editDraft is null && !HasPendingWork;
        query.Enabled = scope.Enabled = state.Enabled = project.Enabled = exact.Enabled = editDraft is null && !HasPendingWork;
        open.Enabled = browsing && model.DetailCurrent && session.RetainedCurrent && !session.MutationBusy && evidence.SelectedItem is EvidenceRow;
        correct.Enabled = browsing && !session.MutationBusy && model.DetailCurrent && model.Detail?.Item.State == "active";
        forget.Enabled = browsing && !session.MutationBusy && model.DetailCurrent && model.Detail is not null;
        editPanel.Visible = editDraft is not null;
        editText.ReadOnly = HasPendingWork || editDraft?.Pending is not null;
        saveEdit.Enabled = ready && !session.MutationBusy && editDraft is { Pending: null, Original.Item.State: "active" }
            && editDraft.Original.Epoch == session.CoreInstanceId && !string.IsNullOrWhiteSpace(editDraft.Text);
        discardEdit.Enabled = editDraft is not null && !HasPendingWork;
        reviewEdit.Enabled = ready && editDraft is { Pending: null };
        resolveEdit.Enabled = ready && editDraft?.NeedsResolution == true;
        retryEdit.Enabled = ready && !session.MutationBusy && editDraft?.NeedsResolution == true && editDraft.Original.Epoch == session.CoreInstanceId;
        if (editDraft is { } draft) editTarget.Text = $"Draft pinned to {draft.Original.Item.Id} · v{draft.Original.Item.Version} · "
            + (draft.Original.Epoch == session.CoreInstanceId ? "same Core" : "DIFFERENT CORE; review required")
            + (draft.NeedsResolution ? " · frozen request " + draft.Pending!.RequestId : "");
        var cache = model.Page is { } page ? $"Page {pageIndex + 1} · {page.Items.Count} shown / {page.Total} matching · revision {page.Revision} · observed {page.Observed}"
            + (model.PageCurrent ? " · explicit read, not continuously polled" : " · STALE / UNCONFIRMED") : "No page read.";
        var fullStatus = (session.CanUseCore ? "" : "Core unavailable/host blocked · reads and navigation disabled. ")
            + (reading ? "Reading… " : navigating ? "Navigation pending… " : "") + cache + "\r\n" + message;
        status.Text = fullStatus; status.AccessibleDescription = fullStatus; statusTip.SetToolTip(status, fullStatus);
    }
    private async Task ReadPageAsync(string? cursor, int index)
    {
        if (reading || HasPendingWork || editDraft is not null || disposed) return;
        MemoryRead read;
        try { read = model.BeginPage(CurrentQuery); } catch (Exception error) { message = error.Message; UpdateAvailability(); return; }
        reading = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(15));
        try {
            var page = await session.MemoryPageAsync(read.Query, cursor, bounded.Token);
            if (disposed || !model.AcceptPage(read, page)) return;
            if (index == 0) { cursors.Clear(); cursors.Add(null); } else if (index == cursors.Count) cursors.Add(cursor);
            pageIndex = index; rendering = true;
            try {
                records.Rows.Clear();
                foreach (var item in page.Items) {
                    var row = records.Rows.Add(item.Preview + (item.ContentTruncated ? "…" : ""), item.State, item.Version, item.Scope);
                    records.Rows[row].Tag = item.Id;
                }
                records.ClearSelection();
                foreach (DataGridViewRow row in records.Rows) if ((string?)row.Tag == model.SelectedId) row.Selected = true;
            } finally { rendering = false; }
            message = page.Items.Count == 0 ? "No matching canonical memories. Deleted records are absent; search is literal, not semantic." : page.Note;
            if (pageIndex == 255 && page.NextCursor is not null) message += " Page-history bound reached; Refresh to start again.";
            RenderInspection();
        }
        catch (Exception error) { if (!disposed && model.IsCurrent(read)) { model.Invalidate(); message = "Memory page unavailable; retained rows are stale. " + error.Message; } }
        finally { reading = false; if (!disposed) UpdateAvailability(); }
    }
    private async Task InspectAsync(string id)
    {
        if (reading || HasPendingWork || editDraft is not null || disposed) return;
        ClearHighlight();
        MemoryRead read;
        try { read = model.BeginDetail(id); } catch (Exception error) { message = error.Message; UpdateAvailability(); return; }
        rendering = true;
        try { records.ClearSelection(); foreach (DataGridViewRow row in records.Rows) if ((string?)row.Tag == id) row.Selected = true; }
        finally { rendering = false; }
        reading = true; RenderInspection(); UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(15));
        try {
            var value = await session.MemoryDetailAsync(id, bounded.Token);
            if (disposed || !model.AcceptDetail(read, value)) return;
            RenderInspection();
            message = "Exact memory inspected at " + value.Observed + ". Supersession never changes selection automatically.";
        }
        catch (Exception error) { if (!disposed && model.IsCurrent(read)) { message = "Exact memory unavailable; nothing else selected. " + error.Message; RenderInspection(); } }
        finally { reading = false; if (!disposed) UpdateAvailability(); }
    }
    private void ClearHighlight()
    {
        highlighted = null; highlightedRequest = null; detail.BackColor = SystemColors.Window;
        detail.AccessibleName = "Exact selected memory content, metadata and provenance";
        PresentationChanged?.Invoke(this, EventArgs.Empty);
    }
    public async Task<MemoryPanelAck> PresentAsync(MemoryPanelRequest request, Func<long> generation, CancellationToken token)
    {
        MemoryPanelAck Outcome(string state) => new(request, state, Math.Max(generation(), request.Generation),
            Visible && WindowState != FormWindowState.Minimized);
        bool Allowed() => !disposed && session.CanUseCore && MemoryPanelClient.CanPresent(request,
            session.CoreInstanceId, editDraft is not null, reading || navigating || mutating || modal
                || session.TaskControlBusy || session.SecondaryMutationBusy || session.VoiceBusy,
            Visible, WindowState == FormWindowState.Minimized, lastDismissal, DateTimeOffset.UtcNow);
        if (presenting || !Allowed()) return Outcome("deferred");
        HostChanged(null, EventArgs.Empty);
        var beforeGeneration = generation();
        var already = Visible && model.DetailCurrent && model.Detail is { } prior
            && prior.Item.Id == request.Id && prior.Item.Version == request.Version;
        presenting = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, token);
        bounded.CancelAfter(request.Expires - DateTimeOffset.UtcNow > TimeSpan.Zero
            ? request.Expires - DateTimeOffset.UtcNow : TimeSpan.FromMilliseconds(1));
        try {
            var value = await session.MemoryDetailAsync(request.Id, bounded.Token);
            if (!await session.MemoryPresentationPendingAsync(request, bounded.Token)) return Outcome("unavailable");
            bounded.Token.ThrowIfCancellationRequested();
            if (!Allowed() || beforeGeneration != generation()) return Outcome("deferred");
            if (value.Epoch != request.Epoch || value.Item.Id != request.Id || value.Item.Version != request.Version)
                return Outcome("unavailable");
            model.Observe(session.CoreInstanceId, session.CanUseCore);
            var read = model.BeginDetail(request.Id);
            if (!model.AcceptDetail(read, value)) return Outcome("unavailable");
            rendering = true;
            try { records.ClearSelection(); foreach (DataGridViewRow row in records.Rows)
                if ((string?)row.Tag == request.Id) row.Selected = true; }
            finally { rendering = false; }
            RenderInspection();
            if (!Visible) {
                showWithoutActivation = true;
                try { Show(); } finally { showWithoutActivation = false; }
            }
            PerformLayout();
            if (!Allowed() || !detail.Visible || !Visible || WindowState == FormWindowState.Minimized)
                return Outcome("unavailable");
            detail.BackColor = SystemColors.Info;
            detail.AccessibleName = "Highlighted canonical memory " + request.Id + " version " + request.Version;
            highlighted = (request.Id, request.Version, request.Epoch);
            highlightedRequest = request.Request;
            highlightDeadline = request.Expires;
            PresentationChanged?.Invoke(this, EventArgs.Empty);
            var anchor = Rectangle.Intersect(detail.RectangleToScreen(detail.ClientRectangle), Screen.FromControl(detail).Bounds);
            if (anchor.Width <= 0 || anchor.Height <= 0) { ClearHighlight(); return Outcome("unavailable"); }
            message = "Semantic selection highlighted exact memory " + request.Id + " · v" + request.Version
                + ". Host acknowledgement pending; no focus activation.";
            return new(request, already ? "already-visible" : "selected", Math.Max(generation(), request.Generation),
                true, request.Id, request.Version, new(anchor.X, anchor.Y, anchor.Width, anchor.Height));
        }
        catch (Exception error) when (error is not OperationCanceledException || !token.IsCancellationRequested) {
            ClearHighlight(); message = "Semantic memory target unavailable or changed; no replacement selected.";
            return Outcome("unavailable");
        }
        finally { presenting = false; if (!disposed) UpdateAvailability(); }
    }
    public void SetPresentationOutcome(MemoryPanelRequest request, bool confirmed)
    {
        if (disposed || highlightedRequest != request.Request) return;
        if (!confirmed) { ClearHighlight(); model.Invalidate(); RenderInspection(); }
        message = confirmed ? "Core acknowledged exact Memory selection/highlight: " + request.Id + " · v" + request.Version
            : "Memory presentation unconfirmed, deferred or target changed; highlight cleared. No automatic selection replay.";
        UpdateAvailability();
    }
    private async Task OpenEvidenceAsync()
    {
        if (!open.Enabled || evidence.SelectedItem is not EvidenceRow selected || model.SelectedId is not { } id) return;
        var read = model.BeginDetail(id); navigating = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(30));
        try {
            var value = await session.MemoryDetailAsync(id, bounded.Token);
            if (disposed || !model.AcceptDetail(read, value)) return;
            if (!value.Evidence.Any(link => link.Id == selected.Link.Id)) throw new InvalidOperationException("Evidence is no longer registered for this exact memory; nothing opened.");
            var result = await session.MutateRetainedAsync("/api/v1/content/navigate", FullAppProjection.NavigationRequest(selected.Link.Id, "open"), bounded.Token);
            if (!disposed) message = "Captured evidence " + selected.Link.Id + ": " + RetainedRequests.NavigationOutcome(result, selected.Link.Id);
        }
        catch (Exception error) { if (!disposed) message = "Navigation for captured evidence " + selected.Link.Id + " not confirmed; no automatic replay. " + error.Message; }
        finally { navigating = false; if (!disposed) { RenderInspection(); UpdateAvailability(); } }
    }
    private void StartCorrection()
    {
        if (!correct.Enabled || model.Detail is not { } value) return;
        editDraft = new(value); editingText = true; try { editText.Text = value.Content; } finally { editingText = false; }
        message = "Correction draft retained on Hide; exact record/version remains pinned. Existing capture evidence is not copied to corrected text.";
        UpdateAvailability(); editText.Focus();
    }
    private async Task ForgetAsync()
    {
        if (!forget.Enabled || model.Detail is not { } value) return;
        modal = true; UpdateAvailability(); DialogResult decision;
        try { decision = MessageBox.Show(this, value.Item.Id + " · version " + value.Item.Version + "\r\n\r\n" + MemoryEditPresentation.ForgetMeaning,
            "Forget exact memory?", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2); }
        finally { modal = false; UpdateAvailability(); }
        if (decision != DialogResult.OK) return;
        if (!model.DetailCurrent || !ReferenceEquals(model.Detail, value) || value.Epoch != session.CoreInstanceId) {
            message = "Memory/Core changed during confirmation; nothing sent. Inspect again."; UpdateAvailability(); return;
        }
        editDraft = new(value); editingText = true; try { editText.Text = value.Content; } finally { editingText = false; }
        await SubmitEditAsync("forget");
    }
    private async Task SubmitEditAsync(string action)
    {
        if (editDraft is not { } draft || !session.CanUseCore || HasPendingWork || session.MutationBusy) return;
        MemoryMutationIntent request;
        try { request = draft.Begin(action, session.CoreInstanceId); } catch (Exception error) { message = error.Message; UpdateAvailability(); return; }
        mutating = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(30));
        try {
            var ack = await session.EditMemoryAsync(request, bounded.Token);
            if (!disposed) FinishEdit(draft, ack);
        } catch (SoraRequestException error) when (MemoryEditPresentation.DefiniteRejection(error.Code)) {
            draft.Reject(); message = "Edit rejected; draft retained. Review the same record before another submission. " + error.Message;
        } catch (Exception error) { message = "Outcome UNCONFIRMED; request frozen. Check receipt or explicitly retry the same request; do not create a new edit. " + error.Message; }
        finally { mutating = false; if (!disposed) { RenderInspection(); UpdateAvailability(); } }
    }
    private void FinishEdit(MemoryEditDraft draft, MemoryEditAck ack)
    {
        draft.Confirm(ack); editDraft = null; model.Invalidate();
        message = $"{(ack.Historical ? "Historical receipt confirms" : "Core committed")} {draft.Pending!.Action} of {ack.Id} · v{ack.Version} · revision {ack.Revision} · {ack.At}. "
            + (ack.Successor is not null ? "Successor " + ack.Successor + "; inspect this ID explicitly. " : "Exact record excluded; other versions are unchanged. ")
            + "Refresh before relying on current state. " + ack.Note;
    }
    private async Task ResolveEditAsync()
    {
        if (!resolveEdit.Enabled || editDraft is not { Pending: { } request } draft) return;
        mutating = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(15));
        try { var ack = await session.MemoryReceiptAsync(request, bounded.Token); if (!disposed) FinishEdit(draft, ack); }
        catch (Exception error) { message = "No matching receipt confirmed. Request stays frozen: absence is not proof a write never occurred. " + error.Message; }
        finally { mutating = false; if (!disposed) { RenderInspection(); UpdateAvailability(); } }
    }
    private async Task ReviewEditAsync()
    {
        if (!reviewEdit.Enabled || editDraft is not { Pending: null } draft) return;
        mutating = true; UpdateAvailability();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token); bounded.CancelAfter(TimeSpan.FromSeconds(15));
        try {
            var latest = await session.MemoryDetailAsync(draft.Original.Item.Id, bounded.Token);
            if (disposed) return;
            modal = true;
            try {
                if (MessageBox.Show(this, MemoryPresentation.Inspection(latest) + "\r\n\r\nUse this exact record/version as the draft baseline? Your authored correction text is retained.",
                    "Review latest memory", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) == DialogResult.Yes) {
                    if (!session.CanUseCore || latest.Epoch != session.CoreInstanceId) throw new InvalidOperationException("Core changed during review; baseline unchanged.");
                    draft.Review(latest); message = "Exact baseline reviewed; authored text retained. Superseded/expired records cannot be corrected.";
                }
            } finally { modal = false; }
        } catch (Exception error) { message = "Review unavailable; draft and exact target retained. " + error.Message; }
        finally { mutating = false; if (!disposed) UpdateAvailability(); }
    }
    private bool DiscardDraft()
    {
        if (editDraft is null) return true;
        if (HasPendingWork) return false;
        modal = true; UpdateAvailability(); DialogResult answer;
        try { answer = MessageBox.Show(this, "Discard this local draft? This does not undo a submitted mutation. "
            + (editDraft.NeedsResolution ? "The captured request outcome remains unknown; receipt ID: " + editDraft.Pending!.RequestId : ""),
            "Discard memory draft", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2); }
        finally { modal = false; }
        if (answer == DialogResult.Yes) editDraft = null;
        UpdateAvailability(); return editDraft is null;
    }
    public bool CanCloseForHostShutdown() => !HasPendingWork && DiscardDraft();
    public void CloseForHostShutdown() { shutdown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !disposed) { disposed = true; session.Changed -= HostChanged; lifetime.Cancel(); lifetime.Dispose(); statusTip.Dispose(); }
        base.Dispose(disposing);
    }
}
