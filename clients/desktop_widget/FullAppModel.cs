using System.Text.Json;
using System.Text.RegularExpressions;

namespace Sora.DesktopWidget;

public sealed record FullTask(string Id, string Status, string Backend, string Description,
    string? ResultReference, DateTimeOffset UpdatedAt)
{
    public string? RequestedModel { get; init; }
    public string? RequestedEffort { get; init; }
    public string? WorkingDirectory { get; init; }
    public string? WorkspaceMode { get; init; }
    public string ProjectLabel => WorkingDirectory is null ? "No selected project" :
        WorkingDirectory + " · " + WorkspaceMode;
    public string SelectionLabel => RequestedModel is null ? "Configured default" :
        RequestedModel + (RequestedEffort is null ? "" : $" · {RequestedEffort}");
}
public sealed record FullBoardCard(string Id, string Column, string Status, string Description,
    string? Specialist, bool NeedsAttention, int RunCount, DateTimeOffset UpdatedAt)
{
    public string? AssignedAgent { get; init; }
    public bool ManuallyPlaced { get; init; }
    public int BoardVersion { get; init; }
}
public sealed record FullExtension(string Id, string Depth, string Version, bool Enabled,
    IReadOnlyList<string> Capabilities, IReadOnlyList<string> RequiredGrants);
public sealed record FullContent(string Id, string Kind, string Label, string Path, string? Handler);
public sealed record FullPermission(string Device, string? Project, string Operation,
    string Resource, string Status, DateTimeOffset ExpiresAt, int UsedCount, int? MaxUses);
public sealed record FullSettings(string Owner, string Project, string DialogueBackend,
    string? DialogueModel, string? DialogueBaseUrl, bool DialogueKeyConfigured,
    int WorkerCount, int ContextMaxChars, IReadOnlyList<string> ContentRoots,
    IReadOnlyList<string> EditorRoots, IReadOnlyList<string> ContentHandlers,
    bool CodingWorkspaceConfigured, int SecretCount)
{
    public bool DialogueManaged { get; init; }
    [System.Text.Json.Serialization.JsonIgnore(Condition =
        System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement UnifiedSettings { get; init; }
    public string? DialogueModelFolder { get; init; }
    public double DialogueTimeoutSeconds { get; init; } = 30;
    public int SettingsRevision { get; init; }
    public int ActiveSettingsRevision { get; init; }
    public bool RestartRequired { get; init; }
    public FullEditableRuntimeSettings? Pending { get; init; }
}
public sealed record FullEditableRuntimeSettings(string DialogueBackend, string? DialogueModel,
    string? DialogueBaseUrl, double DialogueTimeoutSeconds, int WorkerCount, int ContextMaxChars)
{
    public string? DialogueModelFolder { get; init; }
}
public sealed record FullAppSnapshot(WidgetSnapshot Companion, IReadOnlyList<FullTask> Tasks,
    IReadOnlyList<FullExtension> Extensions, IReadOnlyList<FullContent> Content,
    IReadOnlyList<FullPermission> Permissions,
    IReadOnlyList<string> ActiveExtensions, FullSettings? Settings, int PermissionTotal,
    bool PermissionsTruncated, string Error)
{
    public IReadOnlyList<FullBoardCard> BoardCards { get; init; } = [];
    public static FullAppSnapshot Empty { get; } = new(WidgetSnapshot.Empty, [], [], [], [], [],
        null, 0, false, "Connecting…");
}

public static class FullAppProjection
{
    public static FullAppSnapshot Parse(WidgetSnapshot companion, JsonElement tasks,
        JsonElement extensions, JsonElement content, JsonElement permissions, JsonElement capabilities,
        JsonElement settings, JsonElement board = default)
    {
        var messages = companion.Messages.ToDictionary(item => item.Id, item => item.Content);
        var parsedTasks = tasks.GetProperty("tasks").EnumerateArray().Select(item =>
            new FullTask(Get(item, "task_id"), Get(item, "status"),
                Get(item, "effective_backend", "unassigned"),
                TaskDescription(item, messages),
                GetOptional(item, "result_ref"), ParseDate(Get(item, "updated_at"))) {
                    RequestedModel = GetOptional(item, "requested_model"),
                    RequestedEffort = GetOptional(item, "requested_effort"),
                    WorkingDirectory = GetOptional(item, "working_directory"),
                    WorkspaceMode = GetOptional(item, "workspace_mode")
                }).ToArray();
        var parsedExtensions = extensions.EnumerateArray().Select(item =>
            new FullExtension(Get(item, "extension_id"), Get(item, "depth"),
                Get(item, "version"), item.GetProperty("enabled").GetBoolean(),
                Strings(item, "capability_ids"), Strings(item, "required_grants"))).ToArray();
        var parsedContent = content.GetProperty("references").EnumerateArray().Select(item =>
            new FullContent(Get(item, "reference_id"), Get(item, "kind"), Get(item, "label"),
                Get(item, "path"), GetOptional(item, "handler_id"))).ToArray();
        var parsedPermissions = permissions.GetProperty("grants").EnumerateArray().Select(item =>
            new FullPermission(Get(item, "device_id"), GetOptional(item, "project_id"),
                Get(item, "operation"), Get(item, "resource"), Get(item, "status"),
                ParseDate(Get(item, "expires_at")), item.GetProperty("used_count").GetInt32(),
                item.TryGetProperty("max_uses", out var uses) && uses.ValueKind == JsonValueKind.Number
                    ? uses.GetInt32() : null)).ToArray();
        var handlers = settings.GetProperty("content_handlers").EnumerateArray()
            .Select(item => Get(item, "handler_id") + " (" +
                string.Join(", ", Strings(item, "kinds")) + ")").ToArray();
        var pending = settings.TryGetProperty("pending_settings", out var staged) &&
            staged.ValueKind == JsonValueKind.Object ? new FullEditableRuntimeSettings(
                Get(staged, "dialogue_backend"), GetOptional(staged, "dialogue_model"),
                GetOptional(staged, "dialogue_base_url"),
                staged.GetProperty("dialogue_timeout_seconds").GetDouble(),
                staged.GetProperty("worker_count").GetInt32(),
                staged.GetProperty("context_max_chars").GetInt32()) {
                    DialogueModelFolder = GetOptional(staged, "dialogue_model_folder"),
                } : null;
        var parsedSettings = new FullSettings(Get(settings, "owner_id"), Get(settings, "project_id"),
            Get(settings, "dialogue_backend"), GetOptional(settings, "dialogue_model"),
            GetOptional(settings, "dialogue_base_url"),
            settings.GetProperty("dialogue_api_key_configured").GetBoolean(),
            settings.GetProperty("worker_count").GetInt32(),
            settings.GetProperty("context_max_chars").GetInt32(),
            Strings(settings, "content_roots"), Strings(settings, "editor_roots"), handlers,
            settings.GetProperty("coding_workspace_configured").GetBoolean(),
            settings.GetProperty("secrets").GetArrayLength()) {
                DialogueTimeoutSeconds = settings.TryGetProperty("dialogue_timeout_seconds", out var timeout)
                    ? timeout.GetDouble() : 30,
                SettingsRevision = settings.TryGetProperty("settings_revision", out var revision)
                    ? revision.GetInt32() : 0,
                ActiveSettingsRevision = settings.TryGetProperty("active_settings_revision", out var activeRevision)
                    ? activeRevision.GetInt32() : 0,
                RestartRequired = settings.TryGetProperty("restart_required", out var restart) && restart.GetBoolean(),
                Pending = pending,
                DialogueModelFolder = GetOptional(settings, "dialogue_model_folder"),
                DialogueManaged = settings.TryGetProperty("dialogue_managed", out var managed) && managed.GetBoolean(),
                UnifiedSettings = settings.TryGetProperty("settings_version", out var settingsVersion) &&
                    settingsVersion.GetInt32() is 2 or 3 or 4 or 5 or 6 or 7 or 8 or 9 ? settings.Clone() : default,
            };
        var cards = ParseBoard(board);
        return new(companion, parsedTasks, parsedExtensions, parsedContent, parsedPermissions,
            Strings(capabilities, "active_extensions"), parsedSettings,
            permissions.GetProperty("total").GetInt32(),
            permissions.GetProperty("truncated").GetBoolean(), "") { BoardCards = cards };
    }

    public static FullBoardCard[] ParseBoard(JsonElement board) => board.ValueKind == JsonValueKind.Object &&
            board.TryGetProperty("cards", out var boardCards) && boardCards.ValueKind == JsonValueKind.Array
            ? boardCards.EnumerateArray().Select(item => new FullBoardCard(
                Get(item, "task_id"), Get(item, "column"), Get(item, "status"),
                Get(item, "intent"), GetOptional(item, "specialist"),
                item.TryGetProperty("needs_attention", out var attention) && attention.GetBoolean(),
                item.TryGetProperty("run_count", out var runs) ? runs.GetInt32() : 0,
                ParseDate(Get(item, "updated_at"))) {
                    AssignedAgent = GetOptional(item, "assigned_agent"),
                    ManuallyPlaced = Get(item, "column_source") == "manual",
                    BoardVersion = item.TryGetProperty("board_version", out var version)
                        ? version.GetInt32() : 0,
                }).ToArray() : [];

    public static FullContent[] ParseContent(JsonElement content) => content.GetProperty("references").EnumerateArray()
        .Select(item => new FullContent(Get(item, "reference_id"), Get(item, "kind"), Get(item, "label"),
            Get(item, "path"), GetOptional(item, "handler_id"))).ToArray();
    public static FullExtension[] ParseExtensions(JsonElement extensions) => extensions.EnumerateArray()
        .Select(item => new FullExtension(Get(item, "extension_id"), Get(item, "depth"), Get(item, "version"),
            item.GetProperty("enabled").GetBoolean(), Strings(item, "capability_ids"), Strings(item, "required_grants"))).ToArray();
    public static string[] ActiveExtensions(JsonElement capabilities) => Strings(capabilities, "active_extensions");

    public static bool IsSafeIdentifier(string value) =>
        Regex.IsMatch(value, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z", RegexOptions.CultureInvariant);

    public static string TaskPath(string taskId, string action)
    {
        if (!IsSafeIdentifier(taskId) || action is not ("steer" or "cancel"))
            throw new ArgumentException("Invalid task control target.");
        return $"/api/v1/tasks/{taskId}/{action}";
    }

    public static string BoardPath(string taskId, string action)
    {
        if (!IsSafeIdentifier(taskId) || action is not ("start" or "retry" or "move" or "assign" or "remove"))
            throw new ArgumentException("Invalid board card action target.");
        return $"/api/v1/board/cards/{taskId}/{action}";
    }

    public static object SettingsUpdate(int expectedRevision, string backend, string? model,
        string? baseUrl, double timeoutSeconds, int workers, int contextMaxChars,
        string? modelFolder = null)
    {
        if (expectedRevision < 0 || backend is not ("deterministic" or "openai-compatible") ||
            timeoutSeconds is < 1 or > 300 || workers is < 1 or > 16 ||
            contextMaxChars is < 256 or > 65536)
            throw new ArgumentException("Invalid runtime settings.");
        model = string.IsNullOrWhiteSpace(model) ? null : model.Trim();
        baseUrl = string.IsNullOrWhiteSpace(baseUrl) ? null : baseUrl.Trim();
        modelFolder = string.IsNullOrWhiteSpace(modelFolder) ? null : modelFolder.Trim();
        if (modelFolder is { Length: > 4096 })
            throw new ArgumentException("Model folder path is too long.");
        if (backend == "deterministic") { model = null; baseUrl = null; }
        else
        {
            if (model is null or { Length: > 200 } || baseUrl is null or { Length: > 2048 } ||
                !Uri.TryCreate(baseUrl, UriKind.Absolute, out var uri) ||
                uri.UserInfo.Length > 0 || uri.Query.Length > 0 || uri.Fragment.Length > 0 ||
                uri.AbsolutePath.TrimEnd('/') != "/v1" ||
                (uri.Scheme != Uri.UriSchemeHttps &&
                 !(uri.Scheme == Uri.UriSchemeHttp && uri.Host is "localhost" or "127.0.0.1" or "::1")))
                throw new ArgumentException("Use a model and a HTTPS or loopback HTTP /v1 endpoint.");
        }
        return new { version = 1, expected_revision = expectedRevision, dialogue_backend = backend,
            dialogue_model = model, dialogue_base_url = baseUrl,
            dialogue_model_folder = modelFolder,
            dialogue_timeout_seconds = timeoutSeconds, worker_count = workers,
            context_max_chars = contextMaxChars };
    }

    public static object NavigationRequest(string referenceId, string verb)
    {
        if (!IsSafeIdentifier(referenceId) || verb is not ("open" or "show" or "where"))
            throw new ArgumentException("Invalid content reference or action.");
        return new { utterance = $"{verb} this referenced content", verb,
            explicit_reference_id = referenceId };
    }

    private static string Get(JsonElement item, string property, string fallback = "") =>
        GetOptional(item, property) ?? fallback;
    private static string TaskDescription(JsonElement item, Dictionary<string, string> messages)
    {
        var text = messages.GetValueOrDefault(Get(item, "creator_message_id"), "Delegated task");
        const string prefix = "Fix this later: ";
        return text.StartsWith(prefix, StringComparison.Ordinal) ? text[prefix.Length..] : text;
    }
    private static string? GetOptional(JsonElement item, string property) =>
        item.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() : null;
    private static string[] Strings(JsonElement item, string property) =>
        item.TryGetProperty(property, out var values) && values.ValueKind == JsonValueKind.Array
            ? values.EnumerateArray().Where(value => value.ValueKind == JsonValueKind.String)
                .Select(value => value.GetString() ?? "").ToArray() : [];
    private static DateTimeOffset ParseDate(string value) =>
        DateTimeOffset.TryParse(value, out var parsed) ? parsed : DateTimeOffset.MinValue;
}

public sealed class FullAppSync(IWidgetApi api, WidgetSync widget)
{
    public WidgetSync Workflow => widget;
    public FullAppSnapshot Current { get; private set; } = FullAppSnapshot.Empty;

    public async Task<FullAppSnapshot> RefreshAsync(CancellationToken cancellationToken = default)
    {
        var companion = await widget.RefreshAsync(cancellationToken);
        if (!companion.Connected)
            return Current = Current with { Companion = companion, Error = companion.Error };
        try
        {
            var tasks = api.GetAsync("/api/v1/tasks?limit=100&offset=0", cancellationToken);
            var extensions = api.GetAsync("/api/v1/extensions", cancellationToken);
            var content = api.GetAsync("/api/v1/content/references", cancellationToken);
            var permissions = api.GetAsync("/api/v1/projections/permissions", cancellationToken);
            var capabilities = api.GetAsync("/api/v1/projections/capabilities", cancellationToken);
            var settings = api.GetAsync("/api/v1/projections/settings", cancellationToken);
            var board = api.GetAsync("/api/v1/projections/objects", cancellationToken);
            await Task.WhenAll(tasks, extensions, content, permissions, capabilities, settings, board);
            Current = FullAppProjection.Parse(companion, await tasks, await extensions, await content,
                await permissions, await capabilities, await settings, await board);
        }
        catch (Exception error) when (error is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            Current = Current with { Companion = companion, Error = error.Message };
        }
        return Current;
    }
}
