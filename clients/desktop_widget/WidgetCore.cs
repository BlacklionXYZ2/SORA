using System.Drawing;
using System.IO.Compression;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;

namespace Sora.DesktopWidget;

public sealed record ChatLine(string Text, bool Code);

public static class ChatText
{
    // A deliberately small, inert Markdown-to-readable-text projection. Never executes HTML/links.
    public static IEnumerable<ChatLine> Lines(string text, bool markdown = true)
    {
        var fenced = false;
        foreach (var raw in text.Replace("\r\n", "\n").Split('\n'))
        {
            if (markdown && raw.TrimStart().StartsWith("```", StringComparison.Ordinal))
            { fenced = !fenced; continue; }
            if (!markdown || fenced) { yield return new(raw, fenced); continue; }
            var line = System.Text.RegularExpressions.Regex.Replace(raw, @"^\s{0,3}#{1,6}\s+", "");
            line = System.Text.RegularExpressions.Regex.Replace(line, @"^(\s*)[-*+]\s+", "$1• ");
            // Inline code is kept literal while prose emphasis is simplified.
            var pieces = line.Split('`');
            for (var i = 0; i < pieces.Length; i += 2)
            {
                pieces[i] = System.Text.RegularExpressions.Regex.Replace(pieces[i],
                    @"\*\*(.+?)\*\*", "$1");
                pieces[i] = System.Text.RegularExpressions.Regex.Replace(pieces[i],
                    @"(?<!\w)\*([^*\n]+)\*(?!\w)", "$1");
                pieces[i] = System.Text.RegularExpressions.Regex.Replace(pieces[i],
                    @"\[([^\]]+)\]\((https?://[^\s)]+)\)", "$1 ($2)");
            }
            yield return new(string.Join(pieces.Length % 2 == 1 ? "" : "`", pieces), false);
        }
    }

    public static string Plain(string text, bool markdown = true) =>
        string.Join("\n", Lines(text, markdown).Select(line => line.Text));
}

public enum WidgetAnchor { BottomRight, BottomLeft, TopRight, TopLeft }

public sealed record WidgetSettings(
    WidgetAnchor Anchor = WidgetAnchor.BottomRight,
    string Monitor = "",
    bool Expanded = false,
    bool Quiet = false,
    bool AlwaysOnTop = true,
    bool ShowTechnicalDetail = false,
    int? SavedX = null,
    int? SavedY = null);

public static class WidgetGeometry
{
    public static Point AnchorTo(Rectangle workArea, Size size, WidgetAnchor anchor, int margin = 16)
    {
        var x = anchor is WidgetAnchor.BottomRight or WidgetAnchor.TopRight
            ? workArea.Right - size.Width - margin : workArea.Left + margin;
        var y = anchor is WidgetAnchor.BottomRight or WidgetAnchor.BottomLeft
            ? workArea.Bottom - size.Height - margin : workArea.Top + margin;
        return Clamp(workArea, size, new Point(x, y));
    }

    public static Point Clamp(Rectangle workArea, Size size, Point requested)
    {
        return new Point(
            Math.Clamp(requested.X, workArea.Left, Math.Max(workArea.Left, workArea.Right - size.Width)),
            Math.Clamp(requested.Y, workArea.Top, Math.Max(workArea.Top, workArea.Bottom - size.Height)));
    }
}

public static class WidgetSettingsStore
{
    public static WidgetSettings Load(string path)
    {
        try
        {
            return JsonSerializer.Deserialize<WidgetSettings>(File.ReadAllText(path)) ?? new();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException)
        {
            return new();
        }
    }

    public static void Save(string path, WidgetSettings settings)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(settings), Encoding.UTF8);
        File.Move(temporary, path, true);
    }
}

public sealed record WidgetMessage(string Id, string Role, string Content, DateTimeOffset CreatedAt);
public sealed record WidgetTask(string Id, string Status, string Backend, string? ResultRef);
public sealed record WidgetProvider(string Id, string Name, bool Available);
public sealed record WidgetActivity(string EventId, long Sequence, string Type, string Source, string TaskId,
    string? RunId, string CorrelationId, string Timestamp)
{
    public string Label => Type switch {
        "task.planned" => "Note saved", "task.created" => "Task requested", "task.started" => "Run admitted",
        "task.retried" => "Retry admitted", "run.created" => "Run queued", "run.launching" => "Launching",
        "run.running" => "Running", "run.completed" => "Completed · provider report", "run.failed" => "Failed",
        "run.cancelled" => "Cancelled", "run.interrupted" => "Interrupted", "task.steered" => "Instruction recorded",
        _ => "Task activity"
    };
    public static WidgetActivity? Parse(JsonElement item)
    {
        static string? Text(JsonElement item, string name) => item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        if (item.ValueKind != JsonValueKind.Object) return null;
        var type = Text(item, "event_type");
        if (type is not ("task.planned" or "task.created" or "task.started" or "task.retried" or "run.created"
            or "run.launching" or "run.running" or "run.completed" or "run.failed" or "run.cancelled" or "run.interrupted" or "task.steered")) return null;
        var eventId = Text(item, "event_id"); var taskId = Text(item, "task_id"); var runId = Text(item, "run_id");
        var correlation = Text(item, "correlation_id"); var timestamp = Text(item, "timestamp"); var source = Text(item, "source");
        if (eventId is null || taskId is null || correlation is null || timestamp is null
            || !System.Text.RegularExpressions.Regex.IsMatch(eventId, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z")
            || !System.Text.RegularExpressions.Regex.IsMatch(taskId, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z")
            || runId is not null && !System.Text.RegularExpressions.Regex.IsMatch(runId, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z")
            || correlation.Length is < 1 or > 128 || correlation.Any(char.IsControl)
            || source is null || source.Length is < 1 or > 128 || source.Any(char.IsControl)
            || !DateTimeOffset.TryParse(timestamp, out _)
            || !item.TryGetProperty("sequence", out var seq) || seq.ValueKind != JsonValueKind.Number || !seq.TryGetInt64(out var sequence) || sequence < 1) return null;
        return new(eventId, sequence, type, source, taskId, runId, correlation, timestamp);
    }
}
public sealed record WidgetMemoryActivity(string EventId, long Sequence, string Type, string MemoryId,
    long Version, string Core, string? DialogueRequest, string? RetrievalId, string Status, string Timestamp)
{
    public string Key => EventId + "/" + MemoryId;
    public string Label => Type == "memory.retrieved" ? "Memory context selected"
        : Status is "selected" or "already-visible" ? "Memory selected · host report" : "Memory " + Status;
    public static IReadOnlyList<WidgetMemoryActivity> Parse(JsonElement item)
    {
        static string? Text(JsonElement data, string name) => data.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
        static bool Id(string? value) => value is not null && System.Text.RegularExpressions.Regex.IsMatch(value,
            "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z");
        if (item.ValueKind != JsonValueKind.Object || !Id(Text(item, "event_id"))
            || !item.TryGetProperty("event_type", out var kind) || kind.ValueKind != JsonValueKind.String
            || kind.GetString() is not ("memory.retrieved" or "ui.memory.presented")
            || !item.TryGetProperty("sequence", out var sequence) || sequence.ValueKind != JsonValueKind.Number || !sequence.TryGetInt64(out var seq) || seq < 1
            || !DateTimeOffset.TryParse(Text(item, "timestamp"), out _)
            || Text(item, "timestamp") is not { } stamp || !System.Text.RegularExpressions.Regex.IsMatch(stamp, "(?:Z|[+-][0-9]{2}:[0-9]{2})\\z")
            || !item.TryGetProperty("payload", out var data) || data.ValueKind != JsonValueKind.Object
            || !Guid.TryParse(Text(data, "instance_id"), out _)) return [];
        var eventId = Text(item, "event_id")!; var type = kind.GetString()!;
        var core = Text(data, "instance_id")!; var dialogue = Text(data, "dialogue_request_id");
        if (dialogue is not null && !Id(dialogue)) return [];
        var timestamp = Text(item, "timestamp")!;
        var retrieval = type == "memory.retrieved" ? Text(data, "retrieval_id") : null;
        if (type == "memory.retrieved" && (!Id(retrieval) || dialogue is null
            || Text(data, "source") != "canonical" || Text(data, "stage") is not ("chooser" or "reply"))) return [];
        var status = type == "memory.retrieved" ? "context-selected" : Text(data, "status");
        if (type == "ui.memory.presented" && status is not ("selected" or "already-visible" or "deferred" or "unavailable" or "rejected")) return [];
        if (type == "ui.memory.presented" && (!Guid.TryParse(Text(data, "request_id"), out _)
            || !Guid.TryParse(Text(data, "host_id"), out _)
            || !data.TryGetProperty("registry_generation", out var gen) || gen.ValueKind != JsonValueKind.Number
            || !gen.TryGetInt64(out var generation) || generation < 0)) return [];
        var rows = type == "memory.retrieved" && data.TryGetProperty("memories", out var memories)
            && memories.ValueKind == JsonValueKind.Array ? memories.EnumerateArray().ToArray()
            : type == "ui.memory.presented" ? new[] { data } : [];
        if (rows.Length is < 1 or > 64) return [];
        var result = new List<WidgetMemoryActivity>();
        foreach (var row in rows) {
            if (row.ValueKind != JsonValueKind.Object || !Id(Text(row, "memory_id"))
                || !row.TryGetProperty("entity_version", out var version) || version.ValueKind != JsonValueKind.Number || !version.TryGetInt64(out var v) || v < 1) return [];
            result.Add(new(eventId, seq, type, Text(row, "memory_id")!, v, core, dialogue, retrieval, status!, timestamp));
        }
        return result;
    }
}
public sealed record WidgetSnapshot(
    bool Connected,
    string Error,
    long Sequence,
    IReadOnlyList<WidgetMessage> Messages,
    IReadOnlyList<WidgetTask> Tasks,
    IReadOnlyList<WidgetProvider> Providers,
    int ActiveWorkers,
    bool DialogueReady)
{
    public static WidgetSnapshot Empty { get; } = new(false, "Connecting…", 0, [], [], [], 0, false);
    public string ModelState { get; init; } = "ready";
    public string DialogueState { get; init; } = "idle";
    public string DialogueModel { get; init; } = "Configured dialogue model";
    public IReadOnlyList<WidgetActivity> PublicActivity { get; init; } = [];
    public IReadOnlyList<WidgetMemoryActivity> MemoryActivity { get; init; } = [];
    public string StatusLabel => !Connected ? "Reconnecting…" : DialogueState == "thinking"
        ? "Thinking…" : !DialogueReady ? ModelState == "reloading"
            ? "Model reloading…" : "Model unavailable · Settings"
            : DialogueState == "talking" ? "Speaking…" : "Ready to talk";
}

public interface IWidgetApi
{
    Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken);
    Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken);
}

public sealed class WidgetApiClient : IWidgetApi, IDisposable
{
    // Optional profile-host binding. Existing clients keep their compatible unbound protocol.
    public string? ExpectedCoreInstanceId { get; set; }
    private readonly HttpClient client;
    private readonly string tokenFile;
    private readonly string deviceId;

    public WidgetApiClient(Uri baseAddress, string tokenFile, string deviceId)
    {
        if (baseAddress.Scheme != Uri.UriSchemeHttp ||
            baseAddress.Host is not ("127.0.0.1" or "::1"))
            throw new ArgumentException("Widget Core address must be loopback HTTP.", nameof(baseAddress));
        this.tokenFile = Path.GetFullPath(tokenFile);
        this.deviceId = deviceId;
        client = new HttpClient { BaseAddress = baseAddress, Timeout = Timeout.InfiniteTimeSpan };
    }

    public Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken) =>
        SendAsync(HttpMethod.Get, path, null, cancellationToken);

    public Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken) =>
        SendAsync(HttpMethod.Post, path, body, cancellationToken);

    public Task<JsonElement> PostWithGrantAsync(
        string path, object body, string grantId, CancellationToken cancellationToken) =>
        SendAsync(HttpMethod.Post, path, body, cancellationToken, grantId);

    private async Task<JsonElement> SendAsync(
        HttpMethod method, string path, object? body, CancellationToken cancellationToken,
        string? grantId = null)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(
            path is "/api/v1/dialogue" or "/api/v1/dialogue/desktop" ? 315 :
            path is "/api/v1/agents/catalogue/refresh" ? 35 : 12));
        cancellationToken = deadline.Token;
        // Core may replace the token on restart. It is read only into process memory, never settings.
        var token = (await File.ReadAllTextAsync(tokenFile, cancellationToken)).Trim();
        if (token.Length < 16) throw new IOException("Core token file is not ready.");
        using var request = new HttpRequestMessage(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Headers.ConnectionClose = true;
        request.Headers.Add("X-SORA-Device-ID", deviceId);
        if (ExpectedCoreInstanceId is string instance && path != "/api/v1/runtime/identity")
            request.Headers.Add("X-SORA-Core-Instance", instance);
        if (grantId is not null)
            request.Headers.Add("X-SORA-Grant-ID", grantId);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (body is not null)
            request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await client.SendAsync(request, cancellationToken);
        var content = await response.Content.ReadAsStringAsync(cancellationToken);
        using var json = JsonDocument.Parse(content);
        if (!response.IsSuccessStatusCode)
        {
            var message = json.RootElement.TryGetProperty("error", out var error) &&
                error.TryGetProperty("message", out var detail)
                ? detail.GetString() : $"Core returned {(int)response.StatusCode}.";
            var code = error.ValueKind == JsonValueKind.Object && error.TryGetProperty("code", out var value)
                ? value.GetString() : null;
            throw new SoraRequestException(message, code);
        }
        return json.RootElement.Clone();
    }

    public void Dispose() => client.Dispose();
}

public sealed class SoraRequestException(string? message, string? code) : HttpRequestException(message)
{
    public string? Code { get; } = code;
}

// Dialogs consume the existing workflow, not a second synchronizer or HTTP client.
public interface IAgentWorkflow
{
    Task<JsonElement> AgentCatalogueAsync(bool refresh = false, CancellationToken cancellationToken = default);
    Task<JsonElement> SettingsAsync(CancellationToken cancellationToken = default);
    Task<JsonElement> SaveModelPurposesAsync(int version, int revision, string agent, JsonElement rows,
        CancellationToken cancellationToken = default);
    Task<JsonElement> ProjectPathsAsync(bool reconcile = false, CancellationToken cancellationToken = default);
    Task<JsonElement> DelegateAsync(string intent, string? referenceId, CancellationToken cancellationToken = default,
        AgentSelection? selection = null, string? idempotencyKey = null);
    Task<JsonElement> StartPlannedAsync(string taskId, string intent, AgentSelection selection,
        CancellationToken cancellationToken = default);
}

public sealed class TaskSubmissionDraft
{
    public string Key { get; } = Guid.NewGuid().ToString("N");
    private JsonElement? request;
    public bool Attempted => request.HasValue;
    public bool Confirmed { get; private set; }
    public string Begin(string intent, string? reference, AgentSelection selection)
    {
        var candidate = JsonSerializer.SerializeToElement(AgentSelection.TaskBody(intent, reference, selection, Key));
        if (Confirmed) throw new InvalidOperationException("This task was acknowledged. Choose New task for a separate request.");
        if (request.HasValue && !JsonElement.DeepEquals(candidate, request.Value))
            throw new InvalidOperationException("An unconfirmed request is retained. Retry its exact text, model and project; inspect Activity before creating another task.");
        request = candidate; return Key;
    }
    public void Acknowledge() => Confirmed = true;
}

public sealed class WidgetSync(IWidgetApi api) : IAgentWorkflow
{
    public WidgetSnapshot Current { get; private set; } = WidgetSnapshot.Empty;

    public void ResetForNewCore() => Current = Current with { Connected = false, Sequence = 0,
        DialogueReady = false, PublicActivity = [], MemoryActivity = [], Error = "Core instance changed. Last-known data is stale until resync." };

    public async Task<WidgetSnapshot> RefreshAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var sequence = Current.Sequence;
            var activity = Current.PublicActivity.ToDictionary(item => item.EventId);
            var memoryActivity = Current.MemoryActivity.ToDictionary(item => item.Key);
            var changed = !Current.Connected;
            for (var pageNumber = 0; pageNumber < 10; pageNumber++)
            {
                var page = await api.GetAsync(
                    $"/api/v1/events?since_sequence={sequence}&limit=100", cancellationToken);
                var events = page.GetProperty("events");
                if (page.GetProperty("resync_required").GetBoolean()) { activity.Clear(); memoryActivity.Clear(); }
                foreach (var item in events.EnumerateArray()) {
                    var publicEvent = WidgetActivity.Parse(item);
                    foreach (var memoryEvent in WidgetMemoryActivity.Parse(item)) memoryActivity[memoryEvent.Key] = memoryEvent;
                    if (publicEvent is not null) activity[publicEvent.EventId] = publicEvent;
                }
                changed |= events.GetArrayLength() > 0 || page.GetProperty("resync_required").GetBoolean();
                sequence = page.GetProperty("next_sequence").GetInt64();
                if (!page.GetProperty("more_available").GetBoolean()) break;
                if (pageNumber == 9) changed = true;
            }
            if (!changed)
            {
                // Model lifecycle is volatile, not a durable chat/task event.
                var currentCompanion = await api.GetAsync("/api/v1/projections/companion", cancellationToken);
                var model = currentCompanion.GetProperty("companion");
                Current = Current with { Connected = true, Error = "", Sequence = sequence,
                    DialogueReady = model.GetProperty("dialogue_ready").GetBoolean(),
                    ModelState = Text(model, "model_state", "ready"),
                    DialogueState = Text(model, "state", "idle"),
                    DialogueModel = Text(model, "dialogue_model", "Configured dialogue model"),
                    PublicActivity = activity.Values.OrderBy(item => item.Sequence).TakeLast(64).ToArray(),
                    MemoryActivity = memoryActivity.Values.OrderBy(item => item.Sequence).TakeLast(64).ToArray() };
                return Current;
            }
            var messages = api.GetAsync("/api/v1/messages?limit=100", cancellationToken);
            var tasks = api.GetAsync("/api/v1/tasks?limit=100&offset=0", cancellationToken);
            var companion = api.GetAsync("/api/v1/projections/companion", cancellationToken);
            var status = api.GetAsync("/api/v1/status", cancellationToken);
            await Task.WhenAll(messages, tasks, companion, status);
            Current = ParseSnapshot(
                await messages, await tasks, await companion, await status, sequence) with {
                    PublicActivity = activity.Values.OrderBy(item => item.Sequence).TakeLast(64).ToArray(),
                    MemoryActivity = memoryActivity.Values.OrderBy(item => item.Sequence).TakeLast(64).ToArray()
                };
        }
        catch (Exception error) when (error is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            Current = Current with { Connected = false, Error = error.Message };
        }
        return Current;
    }

    public Task<JsonElement> DialogueAsync(string content, CancellationToken cancellationToken = default,
        string? requestId = null) =>
        api.PostAsync("/api/v1/dialogue", new { content, request_id = requestId }, cancellationToken);

    public Task<JsonElement> DialogueWithFilesAsync(
        string content, IReadOnlyList<string> filePaths, CancellationToken cancellationToken = default,
        string? requestId = null) =>
        api.PostAsync("/api/v1/dialogue", new { content, file_paths = filePaths, request_id = requestId }, cancellationToken);

    public Task<JsonElement> DesktopDialogueAsync(
        string content, CancellationToken cancellationToken = default, string? requestId = null) =>
        api.PostAsync("/api/v1/dialogue/desktop", new { content, request_id = requestId }, cancellationToken);

    public Task<JsonElement> CancelDialogueAsync(string requestId, CancellationToken cancellationToken = default) =>
        api.PostAsync("/api/v1/dialogue/cancel", new { request_id = requestId }, cancellationToken);

    public Task<JsonElement> VoiceStatusAsync(CancellationToken cancellationToken = default) =>
        api.GetAsync("/api/v1/voice/local", cancellationToken);

    public Task<JsonElement> VoiceActionAsync(string action, CancellationToken cancellationToken = default) =>
        api.PostAsync("/api/v1/voice/local", new { action }, cancellationToken);

    public Task<JsonElement> DelegateAsync(
        string intent, string? referenceId, CancellationToken cancellationToken = default,
        AgentSelection? selection = null, string? idempotencyKey = null) =>
        api.PostAsync("/api/v1/tasks", AgentSelection.TaskBody(intent, referenceId, selection, idempotencyKey), cancellationToken);

    public Task<JsonElement> AgentCatalogueAsync(bool refresh = false,
        CancellationToken cancellationToken = default) => refresh
        ? api.PostAsync("/api/v1/agents/catalogue/refresh", new { }, cancellationToken)
        : api.GetAsync("/api/v1/agents/catalogue", cancellationToken);

    public Task<JsonElement> SettingsAsync(CancellationToken cancellationToken = default) =>
        api.GetAsync("/api/v1/projections/settings", cancellationToken);

    public Task<JsonElement> SaveModelPurposesAsync(int version, int revision, string agent,
        JsonElement rows, CancellationToken cancellationToken = default)
    {
        if (agent is not ("codex" or "hermes" or "antigravity"))
            throw new ArgumentException("Select a supported agent.");
        return api.PostAsync("/api/v1/settings", new { version, expected_revision = revision,
            changes = new Dictionary<string, object> { [$"agents.{agent}.model_choices"] = rows } }, cancellationToken);
    }

    public Task<JsonElement> ProjectPathsAsync(bool reconcile = false,
        CancellationToken cancellationToken = default) => reconcile
        ? api.PostAsync("/api/v1/paths/reconcile", new { }, cancellationToken)
        : api.GetAsync("/api/v1/paths", cancellationToken);

    public Task<JsonElement> StartPlannedAsync(string taskId, string intent,
        AgentSelection selection, CancellationToken cancellationToken = default) =>
        api.PostAsync("/api/v1/board/cards/" + Uri.EscapeDataString(taskId) + "/start",
            AgentSelection.TaskBody(intent, null, selection), cancellationToken);

    public Task<JsonElement> TaskEvidenceAsync(string taskId, CancellationToken cancellationToken = default) =>
        api.GetAsync("/api/v1/tasks/" + Uri.EscapeDataString(taskId) + "/evidence", cancellationToken);

    public static WidgetSnapshot ParseSnapshot(
        JsonElement messages, JsonElement tasks, JsonElement companion, JsonElement status, long sequence)
    {
        var parsedMessages = messages.EnumerateArray().Select(item => new WidgetMessage(
            Text(item, "message_id"), Text(item, "role"), Text(item, "content"),
            DateTimeOffset.TryParse(Text(item, "created_at"), out var date) ? date : DateTimeOffset.MinValue
        )).ToArray();
        var parsedTasks = tasks.GetProperty("tasks").EnumerateArray().Select(item => new WidgetTask(
            Text(item, "task_id"), Text(item, "status"),
            Text(item, "effective_backend", "unassigned"),
            item.TryGetProperty("result_ref", out var result) && result.ValueKind == JsonValueKind.String
                ? result.GetString() : null
        )).ToArray();
        var providers = status.GetProperty("providers").EnumerateObject().Select(item =>
            new WidgetProvider(item.Name, Text(item.Value, "display_name", item.Name),
                item.Value.TryGetProperty("available", out var available) && available.GetBoolean())).ToArray();
        var identity = companion.GetProperty("companion");
        return new WidgetSnapshot(true, "", sequence, parsedMessages, parsedTasks, providers,
            companion.GetProperty("background_workers_active").GetInt32(),
            identity.GetProperty("dialogue_ready").GetBoolean()) {
                ModelState = Text(identity, "model_state", "ready"),
                DialogueState = Text(identity, "state", "idle"),
                DialogueModel = Text(identity, "dialogue_model", "Configured dialogue model") };
    }

    private static string Text(JsonElement item, string property, string fallback = "") =>
        item.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback : fallback;
}

public sealed record AgentSelection(string? Provider = null, string? Model = null, string? Effort = null,
    string? WorkingDirectory = null, string? WorkspaceMode = null)
{
    public static Dictionary<string, object> TaskBody(string intent, string? referenceId,
        AgentSelection? selection, string? key = null)
    {
        selection ??= new();
        if ((selection.Model is not null || selection.Effort is not null) &&
            (selection.Provider is null or "auto"))
            throw new ArgumentException("Model and effort overrides require an explicit provider.");
        var body = new Dictionary<string, object> {
            ["intent"] = intent, ["idempotency_key"] = key ?? Guid.NewGuid().ToString("N")
        };
        if (selection.Provider is not null) body["explicit_provider"] = selection.Provider;
        if (selection.Model is not null) body["explicit_model"] = selection.Model;
        if (selection.Effort is not null) body["explicit_effort"] = selection.Effort;
        if (selection.WorkingDirectory is not null) body["working_directory"] = selection.WorkingDirectory;
        if (selection.WorkspaceMode is not null) body["workspace_mode"] = selection.WorkspaceMode;
        if (referenceId is not null)
        { body["reference_id"] = referenceId; body["reference_utterance"] = intent; }
        return body;
    }
}

public sealed record WidgetAttachment(string Path, string Label, string Kind, string Preview, bool Embedded);

public static class WidgetAttachments
{
    private static readonly HashSet<string> TextExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".xml", ".yaml", ".yml",
        ".py", ".cs", ".js", ".ts", ".html", ".css", ".log", ".ps1", ".sql", ".rtf",
    };
    private static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    { ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp" };

    public static WidgetAttachment Inspect(string path)
    {
        var full = Path.GetFullPath(path);
        var info = new FileInfo(full);
        if (!info.Exists) throw new FileNotFoundException("Selected file is missing.", full);
        var extension = info.Extension;
        if (ImageExtensions.Contains(extension))
            return new(full, info.Name, "image", "Image is sent to the local vision model for this turn.", false);
        if (extension.Equals(".docx", StringComparison.OrdinalIgnoreCase))
        {
            var doc = ReadDocx(full, info.Length);
            return new(full, info.Name, "document", doc, false);
        }
        if (TextExtensions.Contains(extension))
        {
            if (info.Length > 64 * 1024)
                return new(full, info.Name, "text", "File is over 64 KiB; its path is referenced without inline content.", false);
            var content = File.ReadAllText(full, Encoding.UTF8);
            var embedded = content.Length <= 8_000;
            return new(full, info.Name, "text", embedded ? content : content[..8_000] + "\n[Preview truncated]", embedded);
        }
        return new(full, info.Name, "file", "Preview unavailable here. Local Core will read a bounded view for this turn.", false);
    }

    private static string ReadDocx(string path, long size)
    {
        if (size > 8 * 1024 * 1024) return "Document is over 8 MiB; open it in its configured app.";
        using var archive = ZipFile.OpenRead(path);
        var entry = archive.GetEntry("word/document.xml");
        if (entry is null || entry.Length > 512 * 1024) return "Document preview unavailable.";
        using var reader = new StreamReader(entry.Open(), Encoding.UTF8);
        var xml = XDocument.Parse(reader.ReadToEnd());
        var text = string.Join(" ", xml.Descendants().Where(x => x.Name.LocalName == "t")
            .Select(x => x.Value));
        return text.Length > 8_000 ? text[..8_000] + "\n[Preview truncated]" : text;
    }

    public static string Compose(string prompt, IReadOnlyList<WidgetAttachment> attachments, string? referenceId)
    {
        var builder = new StringBuilder(prompt.Trim());
        if (!string.IsNullOrWhiteSpace(referenceId))
            builder.Append("\n\nCanonical reference ID: ").Append(referenceId.Trim());
        foreach (var attachment in attachments)
        {
            builder.Append("\n\nSelected ").Append(attachment.Kind).Append(" reference: ")
                .Append(attachment.Path);
            if (attachment.Embedded)
                builder.Append("\n```\n").Append(attachment.Preview).Append("\n```");
            else
                builder.Append("\nThe file contents are not included in this dialogue turn.");
        }
        if (builder.Length > 24_000) throw new ArgumentException("Message with attachments is too long.");
        return builder.ToString();
    }
}
