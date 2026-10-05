using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Sora.DesktopShell;

public static class TaskPresentation
{
    public static string Path(string id, string? action = null)
    {
        if (!Regex.IsMatch(id, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z", RegexOptions.CultureInvariant)
            || action is not (null or "evidence" or "cancel" or "steer"))
            throw new ArgumentException("Select an exact supported task target.");
        return "/api/v1/tasks/" + id + (action is null ? "" : "/" + action);
    }

    public static bool CanControl(string status, string action) => action is "cancel" or "steer" &&
        status is "queued" or "routing" or "reasoning" or "working" or "waiting_for_permission" or "waiting_for_input";

    public static string RunsPath(string taskId, string? runId = null, string? cursor = null)
    {
        var path = Path(taskId) + "/runs";
        if (runId is not null) { _ = Path(runId); if (cursor is not null) throw new ArgumentException("Choose a run or page cursor."); return path + "/" + runId; }
        if (cursor is not null && (cursor.Length is < 1 or > 1024 || !Regex.IsMatch(cursor, "\\A[A-Za-z0-9_-]+\\z")))
            throw new ArgumentException("Use the task-bound history cursor.");
        return path + "?limit=50" + (cursor is null ? "" : "&cursor=" + cursor);
    }
    public static void ValidateRuns(string taskId, JsonElement data, string? runId = null)
    {
        if (data.ValueKind != JsonValueKind.Object || Text(data, "task_id") != taskId)
            throw new InvalidDataException("Run evidence task identity mismatch.");
        void Validate(JsonElement run) {
            if (Text(run, "task_id") != taskId || runId is not null && Text(run, "run_id") != runId)
                throw new InvalidDataException("Run evidence identity mismatch.");
            _ = Path(Text(run, "run_id"));
        }
        if (runId is not null) { Validate(data.GetProperty("run")); return; }
        var rows = data.GetProperty("runs"); if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 100) throw new InvalidDataException("Run page exceeds its bound.");
        var ids = new HashSet<string>();
        foreach (var row in rows.EnumerateArray()) { var run = row.GetProperty("run"); Validate(run); if (!ids.Add(Text(run, "run_id"))) throw new InvalidDataException("Run page has duplicate IDs."); }
        var next = Text(data, "next_cursor"); if (next.Length > 0) _ = RunsPath(taskId, cursor: next);
    }
    public static string RunEvidence(string taskId, string runId, JsonElement data)
    {
        ValidateRuns(taskId, data, runId); var run = data.GetProperty("run");
        var output = new StringBuilder($"Task: {taskId}\nRun: {runId}\nAttempt: {run.GetProperty("attempt")}\nProvider: {Text(run, "provider")}\nStatus: {Text(run, "status")}\nOutcome: {Text(run, "outcome", "Not reported")}\nStarted: {Text(run, "started_at", "Not recorded")}\nFinished: {Text(run, "finished_at", "Not recorded")}\n\n");
        var report = data.GetProperty("result");
        if (report.ValueKind == JsonValueKind.Object) {
            if (Text(report, "task_id") != taskId || Text(report, "run_id") != runId) throw new InvalidDataException("Result identity mismatch.");
            output.AppendLine("PROVIDER-REPORTED RESULT · " + Text(report, "result_id") + "\n" + Text(report, "summary") + "\n" + Text(report, "conclusion"));
            foreach (var key in new[] { "warnings", "uncertainties", "actions_taken", "files_read", "files_changed", "commands_run", "task_updates" }) {
                if (report.TryGetProperty(key, out var values) && values.ValueKind == JsonValueKind.Array && values.GetArrayLength() > 0) {
                    output.AppendLine("\n" + key.Replace('_', ' ').ToUpperInvariant() + " (provider report)");
                    foreach (var value in values.EnumerateArray()) output.AppendLine("• " + value.GetString());
                }
            }
            if (report.TryGetProperty("error", out var error)) output.AppendLine("\nFAILURE\n" + Text(error, "code") + ": " + Text(error, "message"));
            output.AppendLine("\nChangelog (provider report): " + Text(report, "changelog_path", "Not reported"));
        }
        else output.AppendLine("No normalized result recorded for this attempt; its task's latest result is not substituted.");
        if (data.TryGetProperty("omitted_items", out var omitted)) foreach (var item in omitted.EnumerateObject()) output.AppendLine($"Omitted {item.Name}: {item.Value} (bounded projection)");
        if (data.TryGetProperty("text_truncated", out var truncated) && truncated.ValueKind == JsonValueKind.True) output.AppendLine("Provider text truncated by the bounded projection.");
        output.AppendLine("\nCOVERAGE\n" + Text(data, "evidence_note")); return output.ToString();
    }

    public static string Evidence(string id, JsonElement data)
    {
        var task = data.GetProperty("task");
        if (Text(task, "task_id") != id) throw new InvalidDataException("Task evidence identity changed; nothing selected.");
        var output = new StringBuilder();
        output.AppendLine($"Task: {id}\nStatus: {Text(task, "status")}\nAgent: {Text(task, "effective_backend", "Unassigned")}");
        output.AppendLine($"Requested model: {Text(task, "requested_model", "Configured default")}\nRequested effort: {Text(task, "requested_effort", "Configured default")}");
        output.AppendLine($"Project: {Text(task, "working_directory", "None")}\nMode: {Text(task, "workspace_mode", "None")}\nBase ref: {Text(task, "workspace_base_ref", "Not reported")}\n");
        output.AppendLine("ORIGINAL OWNER REQUEST\n" + Text(data, "owner_request", "Not available") + "\n");
        var brief = Text(task, "companion_brief");
        if (brief.Length > 0) output.AppendLine("SORA SUGGESTED BRIEF (not the owner's instruction)\n" + brief + "\n");
        var result = data.GetProperty("result");
        if (result.ValueKind == JsonValueKind.Object)
        {
            output.AppendLine("PROVIDER-REPORTED RESULT\n" + Text(result, "summary"));
            output.AppendLine(Text(result, "conclusion"));
            if (result.TryGetProperty("error", out var error) && error.ValueKind == JsonValueKind.Object)
                output.AppendLine("FAILURE\n" + Text(error, "code") + ": " + Text(error, "message"));
            foreach (var key in new[] { "warnings", "uncertainties", "actions_taken", "files_read", "files_changed",
                "commands_run", "task_updates", "artifacts" })
            {
                if (!result.TryGetProperty(key, out var values) || values.ValueKind != JsonValueKind.Array ||
                    values.GetArrayLength() == 0) continue;
                output.AppendLine("\n" + key.Replace('_', ' ').ToUpperInvariant() + " (provider report)");
                foreach (var value in values.EnumerateArray()) output.AppendLine("• " + value.ToString());
            }
            output.AppendLine("\nChangelog path (provider report): " + Text(result, "changelog_path", "Not reported"));
        }
        else output.AppendLine("No final result stored yet. Refresh to check progress.");
        output.AppendLine("\nCOVERAGE\n" + Text(data, "evidence_note", "Independent action verification not available."));
        return output.ToString();
    }

    public static string Text(JsonElement value, string property, string fallback = "") =>
        value.TryGetProperty(property, out var item) && item.ValueKind == JsonValueKind.String
            ? item.GetString() ?? fallback : fallback;
}
