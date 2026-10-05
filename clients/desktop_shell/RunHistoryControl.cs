using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

// Explicit owner-local reads through the profile session; no independent transport/history store.
internal sealed class RunHistoryControl : UserControl
{
    private readonly ShellSession session;
    private readonly CancellationTokenSource lifetime = new();
    private readonly DataGridView runs = Grid("Canonical task attempts");
    private readonly DataGridView artifacts = Grid("Reported files and registered content references");
    private readonly RichTextBox detail = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false,
        AccessibleName = "Exact attempt provider report", Text = "Choose a task and refresh its attempts." };
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly Button reload = ShellTheme.Button("Refresh attempts", "Read newest page of selected task attempts");
    private readonly Button previous = ShellTheme.Button("Previous page", "Read previous attempt page");
    private readonly Button next = ShellTheme.Button("Next page", "Read older attempts for the same task");
    private readonly Button inspect = ShellTheme.Button("Inspect attempt", "Read exact selected attempt, not latest task result");
    private readonly Button open = ShellTheme.Button("Open registered file", "Open selected Core-registered content reference");
    private readonly List<string?> pages = [null];
    private string? taskId, nextCursor, evidenceRun, epoch;
    private int pageIndex, revision, readRevision;
    private bool reading, rendering, disposed;

    public RunHistoryControl(ShellSession session)
    {
        this.session = session; epoch = session.CoreInstanceId; Dock = DockStyle.Fill;
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 30));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 50)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 20));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true };
        actions.Controls.AddRange([reload, previous, next, inspect, open]);
        foreach (var column in new[] { "Attempt", "Run ID", "Provider", "State", "Result ID" }) runs.Columns.Add(column, column);
        foreach (var column in new[] { "Reported artifact", "Path (inert)", "Registered reference" }) artifacts.Columns.Add(column, column);
        runs.SelectionChanged += (_, _) => { if (rendering) return; readRevision++; ClearDetail(); UpdateAvailability(); };
        artifacts.SelectionChanged += (_, _) => UpdateAvailability();
        reload.Click += async (_, _) => await ReadPageAsync(null, 0);
        previous.Click += async (_, _) => { if (pageIndex > 0) await ReadPageAsync(pages[pageIndex - 1], pageIndex - 1); };
        next.Click += async (_, _) => { if (nextCursor is not null) await ReadPageAsync(nextCursor, pageIndex + 1); };
        inspect.Click += async (_, _) => await InspectAsync();
        open.Click += async (_, _) => await OpenAsync();
        root.Controls.Add(actions, 0, 0); root.Controls.Add(runs, 0, 1); root.Controls.Add(detail, 0, 2);
        root.Controls.Add(artifacts, 0, 3); root.Controls.Add(status, 0, 4); Controls.Add(root);
        session.Changed += Changed; UpdateAvailability();
    }
    private static DataGridView Grid(string name) => new() { Dock = DockStyle.Fill, ReadOnly = true,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, MultiSelect = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect, AccessibleName = name };
    private string? SelectedRun => runs.SelectedRows.Count == 1 ? runs.SelectedRows[0].Tag as string : null;
    private string? SelectedReference => artifacts.SelectedRows.Count == 1 ? artifacts.SelectedRows[0].Tag as string : null;
    public void SetTask(string? id)
    {
        if (taskId == id) return;
        taskId = id; Reset("Refresh attempts to read this exact task's history.");
    }
    private void ClearDetail()
    {
        evidenceRun = null; artifacts.Rows.Clear(); detail.Text = "Select and inspect an attempt. No other attempt's report is substituted.";
    }
    private void Reset(string message)
    {
        revision++; readRevision++; reading = false; pageIndex = 0; pages.Clear(); pages.Add(null); nextCursor = null;
        rendering = true;
        try { runs.Rows.Clear(); ClearDetail(); } finally { rendering = false; }
        detail.Text = message; status.Text = message; UpdateAvailability();
    }
    private void Changed(object? sender, EventArgs args)
    {
        if (disposed) return;
        if (!session.CanUseCore) evidenceRun = null; // Reconnect alone cannot make an old report current.
        if (epoch != session.CoreInstanceId) { epoch = session.CoreInstanceId; Reset("Core instance changed; refresh attempts again."); }
        UpdateAvailability();
    }
    private void UpdateAvailability()
    {
        var ready = session.CanUseCore && !reading;
        reload.Enabled = ready && taskId is not null; previous.Enabled = ready && pageIndex > 0;
        next.Enabled = ready && nextCursor is not null; inspect.Enabled = ready && SelectedRun is not null;
        open.Enabled = ready && !session.MutationBusy && evidenceRun == SelectedRun && evidenceRun is not null && SelectedReference is not null;
        if (!session.CanUseCore) status.Text = "Core unavailable/host blocked · any displayed history is stale; Open disabled.";
    }
    private bool Current(string id, int version, int request) => !disposed && taskId == id && revision == version && readRevision == request;
    private async Task ReadPageAsync(string? cursor, int index)
    {
        var id = taskId; if (id is null || reading) return;
        var version = revision; var request = ++readRevision; reading = true; UpdateAvailability();
        try {
            var page = await session.TaskRunsAsync(id, cursor, lifetime.Token);
            if (!Current(id, version, request)) return;
            rendering = true;
            try {
                runs.Rows.Clear(); ClearDetail();
                foreach (var row in page.GetProperty("runs").EnumerateArray()) {
                    var run = row.GetProperty("run"); var runId = TaskPresentation.Text(run, "run_id");
                    var position = runs.Rows.Add(run.GetProperty("attempt").ToString(), runId, TaskPresentation.Text(run, "provider"),
                        TaskPresentation.Text(run, "status"), TaskPresentation.Text(row, "result_id", "Not recorded"));
                    runs.Rows[position].Tag = runId;
                }
                runs.ClearSelection();
            } finally { rendering = false; }
            if (index == 0) { pages.Clear(); pages.Add(null); }
            else if (index >= pages.Count) pages.Add(cursor);
            pageIndex = index; nextCursor = TaskPresentation.Text(page, "next_cursor"); if (nextCursor.Length == 0) nextCursor = null;
            status.Text = $"Task {id} · page {index + 1} · {runs.Rows.Count} of {page.GetProperty("total")} attempts\n" + TaskPresentation.Text(page, "evidence_note");
        }
        catch (Exception error) { if (Current(id, version, request)) { nextCursor = null; status.Text = "History read failed; retained page is stale. " + error.Message; ClearDetail(); } }
        finally { if (!disposed && revision == version) { reading = false; UpdateAvailability(); } }
    }
    private async Task InspectAsync()
    {
        var id = taskId; var runId = SelectedRun; if (id is null || runId is null || reading) return;
        var version = revision; var request = ++readRevision; reading = true; ClearDetail(); UpdateAvailability();
        try {
            var data = await session.TaskRunEvidenceAsync(id, runId, lifetime.Token);
            if (!Current(id, version, request) || SelectedRun != runId) return;
            detail.Text = TaskPresentation.RunEvidence(id, runId, data); evidenceRun = runId;
            foreach (var artifact in data.GetProperty("artifacts").EnumerateArray()) {
                var refs = artifact.GetProperty("reference_ids");
                var kind = TaskPresentation.Text(artifact, "kind"); var path = TaskPresentation.Text(artifact, "path");
                if (refs.GetArrayLength() == 0) artifacts.Rows.Add(kind, path, "Not registered · cannot Open");
                foreach (var value in refs.EnumerateArray()) {
                    var reference = value.GetString()!; _ = FullAppProjection.NavigationRequest(reference, "open");
                    var position = artifacts.Rows.Add(kind, path, reference); artifacts.Rows[position].Tag = reference;
                }
            }
            artifacts.ClearSelection(); status.Text = "Exact attempt inspected. Reported paths are inert; Open revalidates registered reference IDs.";
        }
        catch (Exception error) { if (Current(id, version, request)) { ClearDetail(); status.Text = "Attempt evidence unavailable: " + error.Message; } }
        finally { if (!disposed && revision == version) { reading = false; UpdateAvailability(); } }
    }
    private async Task OpenAsync()
    {
        var reference = SelectedReference; if (reference is null || !open.Enabled) return;
        var version = revision; var request = ++readRevision; var id = taskId!;
        try {
            var result = await session.MutateRetainedAsync("/api/v1/content/navigate", FullAppProjection.NavigationRequest(reference, "open"), lifetime.Token);
            if (Current(id, version, request)) status.Text = RetainedRequests.NavigationOutcome(result, reference);
        }
        catch (Exception error) { if (Current(id, version, request)) status.Text = "Open not confirmed; no automatic retry. " + error.Message; }
        finally { if (!disposed) UpdateAvailability(); }
    }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !disposed) { disposed = true; session.Changed -= Changed; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }
}
