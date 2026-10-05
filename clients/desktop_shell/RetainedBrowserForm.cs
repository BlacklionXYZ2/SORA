using Sora.DesktopWidget;
using System.Text.Json;

namespace Sora.DesktopShell;

// Shared canonical projection; no independent polling, filesystem launcher or credential editor.
internal sealed class RetainedBrowserForm : Form
{
    private readonly ShellSession session;
    private readonly bool integrations;
    private readonly Func<Task> refresh;
    private readonly CancellationTokenSource lifetime = new();
    private readonly ListBox records = new() { Dock = DockStyle.Fill, IntegralHeight = false };
    private readonly TextBox detail = new() { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true,
        ScrollBars = ScrollBars.Both, WordWrap = false, AccessibleName = "Selected canonical record details" };
    private readonly Label state = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly Label outcome = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly List<Button> actions = [];
    private string signature = "";
    private bool busy, updating, shutdown, disposed;
    public bool HasPendingWork => busy;
    private sealed record Row(string Id, string Label) { public override string ToString() => Label; }

    public RetainedBrowserForm(ShellSession session, bool integrations, Func<Task> refresh)
    {
        this.session = session; this.integrations = integrations; this.refresh = refresh;
        Text = integrations ? "SORA · Integrations" : "SORA · Content";
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10.5f); ClientSize = new Size(840, 680);
        StartPosition = FormStartPosition.CenterScreen;
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4, ColumnCount = 1, Padding = new Padding(16) };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var body = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 38)); body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 62));
        body.Controls.Add(records, 0, 0); body.Controls.Add(detail, 1, 0);
        records.AccessibleName = integrations ? "Registered integrations" : "Registered content references";
        var toolbar = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
        var read = ShellTheme.Button("Refresh", "Refresh shared canonical projections");
        read.Click += async (_, _) => await WorkAsync(refresh);
        toolbar.Controls.Add(read);
        if (!integrations) foreach (var verb in new[] { "open", "show", "where" }) {
            var action = ShellTheme.Button(char.ToUpperInvariant(verb[0]) + verb[1..], verb + " selected registered content");
            action.Click += async (_, _) => await NavigateAsync(verb); actions.Add(action); toolbar.Controls.Add(action);
        }
        root.Controls.Add(state, 0, 0); root.Controls.Add(body, 0, 1);
        root.Controls.Add(toolbar, 0, 2); root.Controls.Add(outcome, 0, 3); Controls.Add(root);
        records.SelectedIndexChanged += (_, _) => { if (!updating) ShowSelection(); };
        FormClosing += (_, args) => { if (!shutdown && args.CloseReason == CloseReason.UserClosing) { args.Cancel = true; Hide(); } };
        ShellTheme.Apply(this); Render();
    }

    public void Render()
    {
        if (disposed) return;
        var projection = session.Retained;
        state.Text = session.RetainedCurrent ? integrations
            ? "Canonical extension metadata · read-only; enabled is not proof of a working integration"
            : "Registered content only · navigation uses Core's configured handlers and static access policy"
            : "Stale/offline · cached records only; navigation unavailable. " + projection.Error;
        var next = integrations ? JsonSerializer.Serialize(projection.Extensions) : JsonSerializer.Serialize(projection.Content);
        if (next != signature) {
            var selected = (records.SelectedItem as Row)?.Id; signature = next; updating = true;
            try {
                records.Items.Clear();
                var rows = integrations ? projection.Extensions.Select(item => new Row(item.Id, item.Id + (item.Enabled ? " · enabled" : " · disabled")))
                    : projection.Content.Select(item => new Row(item.Id, item.Label + " · " + item.Kind));
                foreach (var row in rows) { records.Items.Add(row); if (row.Id == selected) records.SelectedItem = row; }
            }
            finally { updating = false; }
        }
        ShowSelection();
    }
    private void ShowSelection()
    {
        var id = (records.SelectedItem as Row)?.Id; var projection = session.Retained;
        var text = "No record selected. " + (records.Items.Count == 0 ? "Core has no registered records in this projection." : "Choose an exact record.");
        if (integrations) {
            var item = projection.Extensions.SingleOrDefault(row => row.Id == id);
            if (item is not null) text = $"ID: {item.Id}\r\nDepth: {item.Depth}\r\nVersion: {item.Version}\r\nEnabled: {item.Enabled}\r\nActive projection: {projection.ActiveExtensions.Contains(item.Id)}"
                + "\r\n\r\nCapabilities:\r\n" + string.Join("\r\n", item.Capabilities)
                + "\r\n\r\nDeclared remote/historical grant metadata (not a local approval request):\r\n" + string.Join("\r\n", item.RequiredGrants)
                + "\r\n\r\nProvider status (availability is not entitlement/execution proof):\r\n"
                + string.Join("\r\n", session.Snapshot.Providers.Select(provider => provider.Name + " · " + (provider.Available ? "reported available" : "unavailable")));
        }
        else {
            var item = projection.Content.SingleOrDefault(row => row.Id == id);
            if (item is not null) text = $"ID: {item.Id}\r\nLabel: {item.Label}\r\nKind: {item.Kind}\r\nRegistered path: {item.Path}\r\nHandler: {item.Handler ?? "configured default"}\r\n\r\nPath text is inert. Open/Show/Where sends the exact reference ID to Core, not a client-side executable or URL.";
        }
        if (detail.Text != text) detail.Text = text;
        foreach (var action in actions) action.Enabled = !busy && session.RetainedCurrent && !session.MutationBusy && id is not null;
    }
    private async Task NavigateAsync(string verb)
    {
        var id = (records.SelectedItem as Row)?.Id;
        if (id is null || !session.RetainedCurrent || session.MutationBusy) return;
        await WorkAsync(async () => {
            var response = await session.MutateRetainedAsync("/api/v1/content/navigate", FullAppProjection.NavigationRequest(id, verb), lifetime.Token);
            if (disposed) return;
            outcome.Text = RetainedRequests.NavigationOutcome(response, id);
            await refresh();
        });
    }
    private async Task WorkAsync(Func<Task> work)
    {
        if (busy || disposed) return;
        busy = true; ShowSelection();
        try { await work(); }
        catch (Exception error) { if (!disposed) outcome.Text = "Operation not confirmed; no automatic replay. " + error.Message; }
        finally { busy = false; if (!disposed) Render(); }
    }
    public void CloseForHostShutdown() { shutdown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !disposed) { disposed = true; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }
}
