using System.Drawing;
using System.Text;
using System.Text.Json;

namespace Sora.DesktopWidget;

public sealed class TaskEvidenceForm : Form
{
    private readonly WidgetSync sync;
    private readonly string taskId;
    private readonly RichTextBox detail = new() { Dock = DockStyle.Fill, ReadOnly = true, DetectUrls = false };
    private readonly Button refresh = new() { Text = "Refresh task result", Dock = DockStyle.Bottom, Height = 36 };
    private readonly CancellationTokenSource lifetime = new();
    public TaskEvidenceForm(WidgetSync sync, string taskId)
    {
        this.sync = sync; this.taskId = taskId;
        Text = "SORA · Task result and evidence"; Size = new Size(800, 560);
        MinimumSize = new Size(580, 420); StartPosition = FormStartPosition.CenterParent;
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10);
        detail.AccessibleName = "Readable task result and evidence";
        Controls.Add(detail); Controls.Add(refresh);
        refresh.Click += async (_, _) => await LoadAsync();
        Shown += async (_, _) => {
            var area = Screen.FromControl(Owner ?? this).WorkingArea;
            Location = WidgetGeometry.Clamp(area, Size, Location);
            await LoadAsync();
        };
        FormClosed += (_, _) => { lifetime.Cancel(); lifetime.Dispose(); };
    }

    private async Task LoadAsync()
    {
        refresh.Enabled = false;
        try {
            var data = await sync.TaskEvidenceAsync(taskId, lifetime.Token);
            if (IsDisposed) return;
            var task = data.GetProperty("task");
            var text = new StringBuilder();
            text.AppendLine($"Task: {taskId}\nStatus: {Get(task, "status")}\nAgent: {Get(task, "effective_backend")}\nRequested model: {Get(task, "requested_model", "Harness default")}\nProject: {Get(task, "working_directory", "None")}\nMode: {Get(task, "workspace_mode", "None")}\n");
            var result = data.GetProperty("result");
            text.AppendLine("ORIGINAL OWNER REQUEST\n" + Get(data, "owner_request", "Not available") + "\n");
            var brief = Get(task, "companion_brief");
            if (brief.Length > 0) text.AppendLine("SORA SUGGESTED BRIEF (not the owner's instruction)\n" + brief + "\n");
            if (result.ValueKind == JsonValueKind.Object) {
                text.AppendLine("RESULT\n" + Get(result, "summary"));
                text.AppendLine(Get(result, "conclusion"));
                if (result.TryGetProperty("error", out var error) && error.ValueKind == JsonValueKind.Object)
                    text.AppendLine("FAILURE\n" + Get(error, "code") + ": " + Get(error, "message"));
                foreach (var key in new[] { "warnings", "uncertainties", "actions_taken", "files_read", "files_changed", "commands_run", "task_updates" }) {
                    if (!result.TryGetProperty(key, out var values) || values.ValueKind != JsonValueKind.Array || values.GetArrayLength() == 0) continue;
                    text.AppendLine("\n" + key.Replace('_', ' ').ToUpperInvariant());
                    foreach (var value in values.EnumerateArray()) text.AppendLine("• " + value.ToString());
                }
                text.AppendLine("\nChangelog path (provider report): " + Get(result, "changelog_path", "Not reported"));
            } else text.AppendLine("No final result stored yet. Use Refresh to check progress.");
            text.AppendLine("\nCOVERAGE\n" + Get(data, "evidence_note"));
            detail.Text = text.ToString();
        } catch (Exception error) { if (!IsDisposed) detail.Text = "Task evidence unavailable: " + error.Message; }
        finally { if (!IsDisposed) refresh.Enabled = true; }
    }
    private static string Get(JsonElement item, string key, string fallback = "") =>
        item.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? fallback : fallback;
}
