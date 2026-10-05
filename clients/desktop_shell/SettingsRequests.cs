using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

public static class SettingsRequests
{
    public static (int Version, int Revision) Projection(JsonElement projection)
    {
        if (projection.ValueKind != JsonValueKind.Object
            || !projection.TryGetProperty("settings_version", out var version) || !version.TryGetInt32(out int v) || v != 9
            || !projection.TryGetProperty("settings_revision", out var revision) || !revision.TryGetInt32(out int r) || r < 0
            || !projection.TryGetProperty("fields", out var fields) || fields.ValueKind != JsonValueKind.Array || fields.GetArrayLength() > 256)
            throw new InvalidDataException("Canonical v9 settings projection unavailable; edits are not supported by this Core.");
        var keys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var field in fields.EnumerateArray()) {
            if (field.ValueKind != JsonValueKind.Object || !field.TryGetProperty("key", out var key)
                || key.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(key.GetString())
                || !keys.Add(key.GetString()!) || !field.TryGetProperty("value", out _))
                throw new InvalidDataException("Settings field identity/value is invalid.");
        }
        return (v, r);
    }
    public static void Validate(string path, JsonElement body, JsonElement current)
    {
        var (version, revision) = Projection(current);
        if (body.ValueKind != JsonValueKind.Object) throw new ArgumentException("Use a typed settings request.");
        string[] allowed = path switch {
            "/api/v1/settings" => ["version", "expected_revision", "changes"],
            "/api/v1/model/reload" => ["expected_revision"],
            "/api/v1/settings/refresh" => [],
            _ => throw new NotSupportedException("Unsupported settings effect route.")
        };
        if (body.EnumerateObject().Count() != allowed.Length || body.EnumerateObject().Any(p => !allowed.Contains(p.Name)))
            throw new ArgumentException("Unsupported/missing settings request field.");
        if (path == "/api/v1/settings/refresh") return;
        if (!body.GetProperty("expected_revision").TryGetInt32(out int expected) || expected != revision
            || current.TryGetProperty("disk_changed", out var changed) && changed.ValueKind == JsonValueKind.True)
            throw new InvalidOperationException("Settings changed; inspect and reconcile the retained draft before submitting. Nothing sent.");
        if (path == "/api/v1/model/reload") {
            if (!current.TryGetProperty("can_reload", out var can) || can.ValueKind != JsonValueKind.True)
                throw new InvalidOperationException("Current model state cannot reload; nothing sent.");
            return;
        }
        if (!body.GetProperty("version").TryGetInt32(out int requested) || requested != version)
            throw new ArgumentException("Use the canonical settings version.");
        var changes = body.GetProperty("changes");
        if (changes.ValueKind != JsonValueKind.Object || changes.GetRawText().Length > 262144)
            throw new ArgumentException("Use bounded canonical settings changes.");
        var editable = current.GetProperty("fields").EnumerateArray()
            .Where(f => f.TryGetProperty("editable", out var e) && e.ValueKind == JsonValueKind.True)
            .Select(f => f.GetProperty("key").GetString()).ToHashSet();
        var names = new HashSet<string>(StringComparer.Ordinal);
        if (changes.EnumerateObject().Any(p => !editable.Contains(p.Name) || !names.Add(p.Name)))
            throw new ArgumentException("Only currently editable canonical fields may be changed.");
    }
}

// Same shared session/transport/effect slot; this is not another inference client.
public sealed class SettingsApi(ShellSession session) : IWidgetApi
{
    public Task<JsonElement> GetAsync(string path, CancellationToken token) => path == "/api/v1/projections/settings"
        ? session.SettingsAsync(token) : throw new NotSupportedException("Unsupported settings read route.");
    public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) =>
        session.SettingsOperationAsync(path, body, token);
}
