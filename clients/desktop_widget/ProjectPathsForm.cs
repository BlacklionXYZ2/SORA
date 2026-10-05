using System.Drawing;
using System.Text.Json;

namespace Sora.DesktopWidget;

/// <summary>Owner-local evidence; never a force-unlock or full filesystem audit.</summary>
public sealed class ProjectPathsForm : Form
{
    private readonly IAgentWorkflow sync;
    private readonly bool hosted;
    private readonly Func<bool> canUseCore;
    private bool shuttingDown, resourcesDisposed;
    public bool HasPendingWork => busy;
    private readonly DataGridView leases = Grid();
    private readonly DataGridView events = Grid();
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = true };
    private readonly Button refresh = new() { Text = "Refresh", AutoSize = true };
    private readonly Button reconcile = new() { Text = "Recheck stopped writers", AutoSize = true };
    private readonly CancellationTokenSource lifetime = new();
    private bool busy;
    private bool evidenceRead, wasAvailable;
    private string? currentEpoch;

    public ProjectPathsForm(IAgentWorkflow sync, bool hosted = false, Func<bool>? canUseCore = null)
    {
        this.sync = sync;
        this.hosted = hosted; this.canUseCore = canUseCore ?? (() => true);
        Text = "SORA · Project paths and writers";
        Size = new Size(1000, 670); MinimumSize = new Size(680, 480);
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10);
        StartPosition = FormStartPosition.CenterParent;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), RowCount = 6, ColumnCount = 1 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 35));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 65));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
        layout.Controls.Add(new Label { Text = "Reserved projects — uncertainty retains the reservation", AutoSize = true }, 0, 0);
        leases.AccessibleName = "Project writer reservations";
        foreach (var title in new[] { "Project directory", "State", "Task", "Run", "Reserved at" }) leases.Columns.Add(title, title);
        layout.Controls.Add(leases, 0, 1);
        layout.Controls.Add(new Label { Text = "Recent path evidence — source labels describe coverage, not verified success", AutoSize = true }, 0, 2);
        events.AccessibleName = "Project path evidence";
        foreach (var title in new[] { "Time", "Path", "Operation", "State", "Source", "Run" }) events.Columns.Add(title, title);
        layout.Controls.Add(events, 0, 3); layout.Controls.Add(status, 0, 4);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill };
        buttons.Controls.Add(refresh); buttons.Controls.Add(reconcile);
        layout.Controls.Add(buttons, 0, 5); Controls.Add(layout);
        layout.SizeChanged += (_, _) => {
            foreach (var label in layout.Controls.OfType<Label>())
                label.MaximumSize = new Size(Math.Max(100, layout.ClientSize.Width - 28), 0);
        };
        refresh.Click += async (_, _) => await LoadAsync(false);
        reconcile.Click += async (_, _) => {
            if (!this.canUseCore() || MessageBox.Show(this,
                "Recheck stopped writers using Core's existing evidence? Uncertainty keeps reservations; this is not force unlock or task cancellation.",
                "SORA · recheck writer evidence", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
                MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
            await LoadAsync(true);
        };
        Shown += async (_, _) => {
            if (!hosted) {
            TopMost = Owner?.TopMost == true;
            var area = Screen.FromControl(Owner ?? this).WorkingArea;
            Size = new Size(Math.Min(Width, area.Width), Math.Min(Height, area.Height));
            Location = WidgetGeometry.Clamp(area, Size, Location);
            }
            await LoadAsync(false);
        };
        FormClosing += (_, args) => {
            if (hosted && !shuttingDown && args.CloseReason == CloseReason.UserClosing) { args.Cancel = true; Hide(); }
        };
    }

    private static DataGridView Grid() => new() { Dock = DockStyle.Fill, ReadOnly = true,
        AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect, MultiSelect = false };

    private async Task LoadAsync(bool recheck)
    {
        if (busy) return;
        if (!canUseCore()) { UpdateHostAvailability(); return; }
        busy = true; refresh.Enabled = reconcile.Enabled = false; status.Text = "Reading local evidence…";
        try
        {
            var value = await sync.ProjectPathsAsync(recheck, lifetime.Token);
            if (IsDisposed) return;
            evidenceRead = true; wasAvailable = canUseCore();
            leases.Rows.Clear(); events.Rows.Clear();
            foreach (var item in value.GetProperty("leases").EnumerateArray())
                leases.Rows.Add(TextOf(item, "display_root"), TextOf(item, "status"), TextOf(item, "task_id"), TextOf(item, "run_id"), TextOf(item, "acquired_at"));
            foreach (var item in value.GetProperty("events").EnumerateArray())
                events.Rows.Add(TextOf(item, "occurred_at"), TextOf(item, "path"), TextOf(item, "operation"), TextOf(item, "status"), TextOf(item, "source"), TextOf(item, "run_id"));
            status.Text = TextOf(value, "notice");
        }
        catch (Exception error) { if (!IsDisposed) status.Text = "Path evidence unavailable: " + error.Message; }
        finally { busy = false; if (!IsDisposed) UpdateHostAvailability(); }
    }

    public void UpdateHostAvailability(string? epoch = null)
    {
        if (IsDisposed) return;
        var available = canUseCore();
        refresh.Enabled = reconcile.Enabled = !busy && available;
        if (!available) status.Text = "Core unavailable or host effects blocked. Retained path evidence is stale; no recheck will be sent.";
        else if (currentEpoch is not null && epoch is not null && currentEpoch != epoch)
            status.Text = "Core instance changed. Retained path evidence is stale; explicitly Refresh before interpreting it.";
        else if (!wasAvailable) status.Text = evidenceRead ? "Core reconnected. Retained path evidence is stale; explicitly Refresh." : "Core connected. Choose Refresh to read path evidence.";
        wasAvailable = available;
        if (epoch is not null) currentEpoch = epoch;
    }
    public void CloseForHostShutdown() { shuttingDown = true; Close(); }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed) { resourcesDisposed = true; lifetime.Cancel(); lifetime.Dispose(); }
        base.Dispose(disposing);
    }

    private static string TextOf(JsonElement item, string key) =>
        item.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
}
