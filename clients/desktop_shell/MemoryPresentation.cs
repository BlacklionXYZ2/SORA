using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Sora.DesktopShell;

public sealed record MemoryQuery(string Query = "", string State = "active", string Project = "all", string Scope = "")
{
    public void Validate()
    {
        if (Query.Length > 256 || Scope.Length > 128 || Query.Concat(Scope).Any(char.IsControl)
            || State is not ("active" or "expired" or "superseded" or "all") || Project is not ("all" or "project" or "global"))
            throw new ArgumentException("Use a bounded literal search, exact scope and supported state/project filters.");
    }
    public string Path(string? cursor = null)
    {
        Validate(); MemoryPresentation.ValidateCursor(cursor);
        return "/api/v1/memories?limit=50&state=" + State + "&project=" + Project
            + "&q=" + Uri.EscapeDataString(Query) + "&scope=" + Uri.EscapeDataString(Scope)
            + (cursor is null ? "" : "&cursor=" + cursor);
    }
}

public sealed record MemoryItem(string Id, string Owner, string? Project, long Version, string State,
    string Scope, string Sensitivity, string Retention, string Provenance, bool MetadataTruncated,
    string Preview, bool ContentTruncated, string? ValidUntil);
public sealed record MemoryLink(string Id, string Label, string Kind);
public sealed record MemoryPageView(string Epoch, string Owner, string? Project, long Revision, string Observed,
    string Note, MemoryQuery Query, IReadOnlyList<MemoryItem> Items, long Total, string? NextCursor);
public sealed record MemoryDetailView(string Epoch, string Owner, string? Project, long Revision, string Observed,
    string Note, MemoryItem Item, string Content, string? Successor, IReadOnlyList<MemoryLink> Evidence, bool Withheld);

// Closed public-field copy. Raw payloads, capture IDs, file paths and unknown fields are never rendered.
public static class MemoryPresentation
{
    public static string DetailPath(string id) { ValidateId(id); return "/api/v1/memories/" + id; }
    public static void ValidateId(string id)
    {
        if (!Regex.IsMatch(id, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z", RegexOptions.CultureInvariant))
            throw new ArgumentException("Select an exact canonical memory/reference ID.");
    }
    public static void ValidateCursor(string? cursor)
    {
        if (cursor is not null && (cursor.Length is < 1 or > 1024 || !Regex.IsMatch(cursor, "\\A[A-Za-z0-9_-]+\\z")))
            throw new ArgumentException("Use the unchanged Core-issued Memory cursor.");
    }
    private static string Text(JsonElement data, string name, int maximum, bool nonempty = true)
    {
        if (!data.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String
            || value.GetString() is not { } text || text.Length > maximum || nonempty && text.Length == 0)
            throw new InvalidDataException("Invalid bounded Memory field: " + name);
        return text;
    }
    private static string Id(JsonElement data, string name) { var id = Text(data, name, 128); ValidateId(id); return id; }
    private static string? OptionalId(JsonElement data, string name)
    {
        if (!data.TryGetProperty(name, out var value) || value.ValueKind == JsonValueKind.Null) return null;
        return Id(data, name);
    }
    private static long Number(JsonElement data, string name, long minimum = 0)
    {
        if (!data.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out var result) || result < minimum)
            throw new InvalidDataException("Invalid Memory revision/count.");
        return result;
    }
    private static bool Flag(JsonElement data, string name)
    {
        if (!data.TryGetProperty(name, out var value) || value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("Invalid Memory flag.");
        return value.GetBoolean();
    }
    private static string Time(JsonElement data, string name)
    {
        var value = Text(data, name, 80);
        if (!Regex.IsMatch(value, "(?:Z|[+-][0-9]{2}:[0-9]{2})\\z") ||
            !DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
            throw new InvalidDataException("Memory timestamp must have an explicit offset.");
        return value;
    }
    private static (string Epoch, string Owner, string? Project, long Revision, string Observed, string Note) Header(JsonElement data, string? epoch)
    {
        if (data.ValueKind != JsonValueKind.Object || Text(data, "schema_version", 8) != "1.0")
            throw new InvalidDataException("Unsupported Memory projection.");
        var instance = Text(data, "instance_id", 36);
        if (!Guid.TryParse(instance, out _) || epoch is not null && instance != epoch)
            throw new InvalidDataException("Memory belongs to a different Core instance.");
        return (instance, Id(data, "owner_id"), OptionalId(data, "project_id"), Number(data, "projection_revision"),
            Time(data, "observed_at"), Text(data, "evidence_note", 32768));
    }
    private static MemoryItem Item(JsonElement row, string owner, string? project)
    {
        if (row.ValueKind != JsonValueKind.Object || Id(row, "owner_id") != owner)
            throw new InvalidDataException("Memory owner mismatch.");
        var itemProject = OptionalId(row, "project_id");
        if (itemProject is not null && itemProject != project) throw new InvalidDataException("Memory project mismatch.");
        var state = Text(row, "state", 16);
        if (state is not ("active" or "expired" or "superseded")) throw new InvalidDataException("Deleted/unknown Memory cannot be displayed.");
        var expiry = row.TryGetProperty("valid_until", out var valid) && valid.ValueKind != JsonValueKind.Null ? Time(row, "valid_until") : null;
        return new(Id(row, "memory_id"), owner, itemProject, Number(row, "entity_version", 1), state,
            Text(row, "scope", 256, false), Text(row, "sensitivity", 256, false), Text(row, "retention", 256, false),
            Text(row, "provenance", 1024, false), Flag(row, "metadata_truncated"),
            Text(row, "content_preview", 1024), Flag(row, "content_truncated"), expiry);
    }
    public static MemoryPageView Page(JsonElement data, MemoryQuery query, string? epoch)
    {
        query.Validate(); var h = Header(data, epoch);
        var echoed = new MemoryQuery(Text(data, "query", 512, false), Text(data, "state_filter", 16),
            Text(data, "project_filter", 16), Text(data, "scope_filter", 256, false));
        if (query != echoed || Number(data, "limit", 1) != 50) throw new InvalidDataException("Memory page filter mismatch.");
        var rows = data.GetProperty("memories");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 50) throw new InvalidDataException("Memory page exceeds its requested bound.");
        var ids = new HashSet<string>(); var items = new List<MemoryItem>();
        foreach (var row in rows.EnumerateArray()) {
            var item = Item(row, h.Owner, h.Project);
            if (!ids.Add(item.Id) || query.State != "all" && item.State != query.State
                || query.Project == "global" && item.Project is not null
                || query.Project == "project" && (h.Project is null || item.Project != h.Project)
                || query.Scope.Length > 0 && item.Scope != query.Scope)
                throw new InvalidDataException("Memory page identities/filters are inconsistent.");
            items.Add(item);
        }
        var total = Number(data, "total"); if (total < items.Count) throw new InvalidDataException("Memory count inconsistent.");
        var next = data.TryGetProperty("next_cursor", out var nextValue) && nextValue.ValueKind != JsonValueKind.Null
            ? Text(data, "next_cursor", 1024) : null;
        ValidateCursor(next);
        if (next is not null && items.Count == 0) throw new InvalidDataException("Empty Memory page cannot advance.");
        return new(h.Epoch, h.Owner, h.Project, h.Revision, h.Observed, h.Note, query, items, total, next);
    }
    public static MemoryDetailView Detail(JsonElement data, string id, string? epoch)
    {
        ValidateId(id); var h = Header(data, epoch); var row = data.GetProperty("memory"); var item = Item(row, h.Owner, h.Project);
        if (item.Id != id) throw new InvalidDataException("Exact Memory ID mismatch; another record is not substituted.");
        var links = row.GetProperty("evidence"); if (links.ValueKind != JsonValueKind.Array || links.GetArrayLength() > 64)
            throw new InvalidDataException("Memory evidence exceeds its bound.");
        var evidence = new List<MemoryLink>(); var ids = new HashSet<string>();
        foreach (var link in links.EnumerateArray()) {
            var reference = Id(link, "reference_id"); var kind = Text(link, "kind", 16);
            if (!ids.Add(reference) || reference.StartsWith("capture-", StringComparison.Ordinal)
                || kind is not ("repository" or "file" or "document" or "image" or "telemetry" or "artifact"))
                throw new InvalidDataException("Invalid/private Memory evidence.");
            evidence.Add(new(reference, Text(link, "label", 1024), kind));
        }
        return new(h.Epoch, h.Owner, h.Project, h.Revision, h.Observed, h.Note, item, Text(row, "content", 32768),
            OptionalId(row, "superseded_by"), evidence, Flag(row, "evidence_withheld"));
    }
    public static string Inspection(MemoryDetailView detail)
    {
        var m = detail.Item;
        var result = new StringBuilder($"{m.Id} · version {m.Version} · {m.State}\r\n\r\n{detail.Content}\r\n\r\n");
        result.AppendLine($"Scope: {m.Scope}\r\nProject: {m.Project ?? "Owner-global"}\r\nSensitivity: {m.Sensitivity}\r\nRetention: {m.Retention}\r\nProvenance: {m.Provenance}");
        result.AppendLine("Valid until: " + (m.ValidUntil ?? "No expiry recorded"));
        result.AppendLine("Created / importance / relevance / graph: not recorded or not yet supported.");
        if (m.MetadataTruncated) result.AppendLine("Long metadata truncated in this bounded projection.");
        if (detail.Successor is not null) result.AppendLine("Superseded by: " + detail.Successor + " (inspect explicitly; selection does not follow it)");
        if (detail.Withheld) result.AppendLine("Private, unregistered, out-of-scope or excess evidence withheld.");
        result.AppendLine($"\r\nRead at: {detail.Observed}\r\nProjection revision: {detail.Revision}\r\n\r\n{detail.Note}");
        return result.ToString();
    }
}

public sealed record MemoryRead(long Request, string? Epoch, MemoryQuery Query, string? Id = null);

// Process-local read/selection cache only. Disconnect never makes an old detail fresh on reconnect.
public sealed class MemoryBrowserState
{
    private long request;
    private string? epoch;
    private bool connected;
    public MemoryPageView? Page { get; private set; }
    public MemoryDetailView? Detail { get; private set; }
    public string? SelectedId { get; private set; }
    public bool PageCurrent { get; private set; }
    public bool DetailCurrent { get; private set; }
    public MemoryQuery Query { get; private set; } = new();
    public void Observe(string? currentEpoch, bool available)
    {
        if (epoch != currentEpoch) { ++request; Page = null; Detail = null; SelectedId = null; PageCurrent = false; DetailCurrent = false; }
        else if (!available && connected) { ++request; PageCurrent = false; DetailCurrent = false; }
        epoch = currentEpoch; connected = available;
    }
    public MemoryRead BeginPage(MemoryQuery query)
    {
        query.Validate(); if (!connected) throw new InvalidOperationException("Connect the matching Core before Refresh.");
        Query = query; PageCurrent = false; Detail = null; DetailCurrent = false;
        return new(++request, epoch, query);
    }
    public void Select(string? id)
    {
        if (id is not null) MemoryPresentation.ValidateId(id);
        if (id == SelectedId) return;
        ++request; SelectedId = id; Detail = null; DetailCurrent = false;
    }
    public MemoryRead BeginDetail(string id)
    {
        Select(id); if (!connected) throw new InvalidOperationException("Connect the matching Core before Inspect.");
        Detail = null; DetailCurrent = false; return new(++request, epoch, Query, id);
    }
    public bool IsCurrent(MemoryRead read) => connected && read.Request == request && read.Epoch == epoch && read.Query == Query;
    public bool AcceptPage(MemoryRead read, MemoryPageView value)
    {
        if (!IsCurrent(read)) return false;
        if (read.Id is not null || value.Query != read.Query || read.Epoch is not null && value.Epoch != read.Epoch)
            throw new InvalidDataException("Page target changed.");
        Page = value; PageCurrent = true;
        if (!value.Items.Any(item => item.Id == SelectedId)) SelectedId = null;
        return true;
    }
    public bool AcceptDetail(MemoryRead read, MemoryDetailView value)
    {
        if (!IsCurrent(read) || read.Id != SelectedId) return false;
        if (value.Item.Id != read.Id || read.Epoch is not null && value.Epoch != read.Epoch
            || PageCurrent && Page is { } page && (page.Owner != value.Owner || page.Project != value.Project))
            throw new InvalidDataException("Detail target/scope changed.");
        Detail = value; DetailCurrent = true; return true;
    }
    public void Invalidate() { ++request; PageCurrent = false; DetailCurrent = false; }
}
