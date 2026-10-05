using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

// This adapter has a fixed route/effect vocabulary, not arbitrary client-side authority.
public static class RetainedRequests
{
    public static string NavigationOutcome(JsonElement reply, string target)
    {
        if (reply.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Navigation acknowledgement is not an object; outcome unknown.");
        var status = Text(reply, "status"); var reason = Text(reply, "reason");
        var reference = Text(reply, "reference_id");
        if (status is not ("opened" or "opened_with_limitations" or "clarification_required" or "not_found" or "unsupported" or "failed")
            || string.IsNullOrWhiteSpace(reason) || reference.Length > 0 && reference != target
            || (status is "opened" or "opened_with_limitations") && reference != target)
            throw new InvalidDataException("Navigation acknowledgement incomplete/mismatched; outcome unknown.");
        var limitations = reply.TryGetProperty("limitations", out var values) && values.ValueKind == JsonValueKind.Array
            ? string.Join(" · ", values.EnumerateArray().Select(value => value.GetString())) : "";
        return $"{target} · {status.Replace('_', ' ')}: {reason}" + (limitations.Length > 0 ? " · " + limitations : "");
    }
    public static void ValidateProjectionShapes(JsonElement board, JsonElement content, JsonElement extensions, JsonElement capabilities)
    {
        static JsonElement Array(JsonElement root, string field)
        {
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty(field, out var value) || value.ValueKind != JsonValueKind.Array)
                throw new InvalidDataException("Canonical retained projection shape is unavailable.");
            return value;
        }
        static void Ids(JsonElement rows, string key)
        {
            var ids = new HashSet<string>(StringComparer.Ordinal);
            foreach (var row in rows.EnumerateArray()) {
                if (row.ValueKind != JsonValueKind.Object || !row.TryGetProperty(key, out var value)
                    || value.ValueKind != JsonValueKind.String || !FullAppProjection.IsSafeIdentifier(value.GetString()!)
                    || !ids.Add(value.GetString()!)) throw new InvalidDataException("Canonical retained IDs are invalid/duplicated.");
            }
        }
        var cards = Array(board, "cards"); Ids(cards, "task_id");
        foreach (var card in cards.EnumerateArray()) {
            if (Text(card, "column") is not ("TODO" or "DOING" or "DONE")) throw new InvalidDataException("Unknown canonical board column.");
        }
        Ids(Array(content, "references"), "reference_id");
        if (extensions.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Canonical integrations are unavailable.");
        Ids(extensions, "extension_id"); _ = Array(capabilities, "active_extensions");
    }
    public static (string? Id, string Action) Validate(string path, JsonElement body)
    {
        if (body.ValueKind != JsonValueKind.Object) throw new ArgumentException("Use a typed retained-surface request.");
        if (path == "/api/v1/board/cards") {
            Fields(body, "intent", "idempotency_key");
            var intent = Text(body, "intent"); var key = Text(body, "idempotency_key");
            if (string.IsNullOrWhiteSpace(intent) || intent.Length > 4000 || key.Length is < 1 or > 128 || key.Any(char.IsControl))
                throw new ArgumentException("A bounded note and stable plan key are required.");
            return (null, "plan");
        }
        if (path == "/api/v1/content/navigate") {
            Fields(body, "utterance", "verb", "explicit_reference_id");
            var id = Text(body, "explicit_reference_id"); var verb = Text(body, "verb");
            _ = FullAppProjection.NavigationRequest(id, verb);
            if (Text(body, "utterance") != $"{verb} this referenced content") throw new ArgumentException("Use the selected registered content action.");
            return (id, verb);
        }
        const string prefix = "/api/v1/board/cards/";
        if (!path.StartsWith(prefix, StringComparison.Ordinal)) throw new ArgumentException("Unsupported retained-surface route.");
        var parts = path[prefix.Length..].Split('/');
        if (parts.Length != 2) throw new ArgumentException("Choose an exact board card action.");
        _ = FullAppProjection.BoardPath(parts[0], parts[1]);
        if (parts[1] == "start") throw new ArgumentException("Use the shared agent selector for planned work.");
        if (parts[1] == "retry") Fields(body);
        else {
            Fields(body, parts[1] == "assign" ? new[] { "assigned_agent", "expected_version" }
                : parts[1] == "move" ? new[] { "column", "expected_version" } : new[] { "expected_version" });
            if (!body.TryGetProperty("expected_version", out var version) || version.ValueKind != JsonValueKind.Number || !version.TryGetInt32(out var number) || number < 0)
                throw new ArgumentException("Use the captured board version.");
            if (parts[1] == "move" && Text(body, "column") is not ("TODO" or "DOING" or "DONE"))
                throw new ArgumentException("Choose a board column.");
            if (parts[1] == "assign" && Text(body, "assigned_agent") is not ("codex" or "claude" or "hermes" or "antigravity" or "sora" or "unassigned"))
                throw new ArgumentException("Choose a registered board assignee label.");
        }
        return (parts[0], parts[1]);
    }
    private static string Text(JsonElement body, string key) =>
        body.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
    private static void Fields(JsonElement body, params string[] allowed)
    {
        if (body.EnumerateObject().Any(item => !allowed.Contains(item.Name)))
            throw new ArgumentException("Unsupported retained-surface field.");
    }
}

public sealed class RetainedApi(ShellSession session) : IWidgetApi
{
    public Task<JsonElement> GetAsync(string path, CancellationToken token) =>
        throw new NotSupportedException("Views use the one shared host projection, not another full-state refresh.");
    public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) => session.MutateRetainedAsync(path, body, token);
}
