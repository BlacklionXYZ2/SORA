using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Sora.DesktopShell;

public sealed record MemoryMutationIntent(string Epoch, Guid RequestId, string Id, string Owner, string? Project,
    long Version, string Action, string? Content)
{
    public string Path => MemoryPresentation.DetailPath(Id) + "/" + Action;
    public string ReceiptPath => "/api/v1/memory-mutations/" + RequestId.ToString("D");
    public void Validate()
    {
        MemoryPresentation.ValidateId(Id); MemoryPresentation.ValidateId(Owner);
        if (Project is not null) MemoryPresentation.ValidateId(Project);
        if (!Guid.TryParse(Epoch, out _) || RequestId == Guid.Empty || Version < 1 || Version == long.MaxValue
            || Action is not ("correct" or "forget") || Action == "forget" && Content is not null
            || Action == "correct" && (string.IsNullOrWhiteSpace(Content) || Content.EnumerateRunes().Count() > 16384 || Content.Contains('\0')))
            throw new ArgumentException("Use a bounded exact-ID/version/Core-bound memory edit.");
    }
    public object Body()
    {
        Validate(); var body = new Dictionary<string, object> { ["instance_id"] = Epoch,
            ["request_id"] = RequestId.ToString("D"), ["expected_version"] = Version };
        if (Content is not null) body["content"] = Content;
        return body;
    }
    public string? ContentHash => Content is null ? null : Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(Content)));
}
public sealed record MemoryEditAck(string Epoch, string CommittedEpoch, string Id, string? Successor,
    long Version, long Revision, string EventId, string At, bool Historical, string Note);

public static class MemoryEditPresentation
{
    public static bool DefiniteRejection(string? code) => code is "MEMORY_VERSION_CONFLICT" or "MEMORY_STATE_CONFLICT"
        or "CORE_INSTANCE_CHANGED" or "RUNTIME_CHANGED" or "RUNTIME_SHUTTING_DOWN" or "INVALID_MEMORY_MUTATION" or "NOT_FOUND" or "FORBIDDEN";
    public const string ForgetMeaning = "Forget only this exact record from canonical retrieval and browsing. "
        + "Other versions/successors remain. Private captures follow existing retention; conversation, audit, "
        + "backups and agent transcripts are not erased. No Undo or physical-erasure guarantee.";
    public static MemoryEditAck Ack(JsonElement data, MemoryMutationIntent intent, string currentEpoch)
    {
        intent.Validate();
        string Text(string key) => data.GetProperty(key).GetString() ?? throw new InvalidDataException("Missing memory receipt field.");
        string? Optional(string key) => data.GetProperty(key).ValueKind == JsonValueKind.Null ? null : Text(key);
        if (Text("schema_version") != "1.0" || Text("instance_id") != currentEpoch || !Guid.TryParse(currentEpoch, out _)
            || !Guid.TryParse(Text("committed_instance_id"), out _) || !Guid.TryParse(Text("request_id"), out var request) || request != intent.RequestId
            || Text("owner_id") != intent.Owner || Optional("project_id") != intent.Project || Text("memory_id") != intent.Id
            || Text("action") != intent.Action || data.GetProperty("expected_version").GetInt64() != intent.Version
            || data.GetProperty("entity_version").GetInt64() != intent.Version + 1 || Optional("content_sha256") != intent.ContentHash)
            throw new InvalidDataException("Memory acknowledgement does not match the captured edit; outcome unconfirmed.");
        var successor = Optional("successor_id"); var successorVersion = data.GetProperty("successor_version");
        if (intent.Action == "correct") {
            if (successor is null || successor == intent.Id || successorVersion.GetInt64() != 1) throw new InvalidDataException("Invalid correction successor receipt.");
            MemoryPresentation.ValidateId(successor);
        } else if (successor is not null || successorVersion.ValueKind != JsonValueKind.Null) throw new InvalidDataException("Forget must not imply a successor effect.");
        var revision = data.GetProperty("projection_revision").GetInt64(); var eventId = Text("event_id"); MemoryPresentation.ValidateId(eventId);
        var at = Text("committed_at");
        if (revision < 1 || at.Length > 80 || !(at.EndsWith('Z') || System.Text.RegularExpressions.Regex.IsMatch(at, "[+-][0-9]{2}:[0-9]{2}$"))
            || !DateTimeOffset.TryParse(at, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out _))
            throw new InvalidDataException("Invalid memory commit revision/time.");
        var note = Text("retention_note"); if (note.Length is < 1 or > 32768) throw new InvalidDataException("Invalid memory retention note.");
        return new(currentEpoch, Text("committed_instance_id"), intent.Id, successor, intent.Version + 1, revision,
            eventId, at, data.GetProperty("replayed").GetBoolean(), note);
    }
}

// Process-local user draft only. An uncertain request remains frozen until receipt/retry confirms it.
public sealed class MemoryEditDraft
{
    public MemoryDetailView Original { get; private set; }
    public string Text { get; private set; }
    public MemoryMutationIntent? Pending { get; private set; }
    public MemoryEditAck? Confirmed { get; private set; }
    public bool NeedsResolution => Pending is not null && Confirmed is null;
    public MemoryEditDraft(MemoryDetailView original) { Original = original; Text = original.Content; }
    public void Edit(string text) {
        if (Pending is not null) throw new InvalidOperationException("Resolve the frozen request before editing again.");
        Text = text;
    }
    public MemoryMutationIntent Begin(string action, string? epoch)
    {
        if (Confirmed is not null) throw new InvalidOperationException("This edit was committed; inspect canonical state before a new edit.");
        if (Original.Epoch != epoch) throw new InvalidOperationException("Draft belongs to a different Core; review its exact record or resolve the old receipt first.");
        if (Pending is { } prior) {
            if (prior.Action != action) throw new InvalidOperationException("Resolve the captured request before changing action.");
            return prior;
        }
        if (action == "correct" && Original.Item.State != "active") throw new InvalidOperationException("Only active memories may be corrected.");
        var intent = new MemoryMutationIntent(Original.Epoch, Guid.NewGuid(), Original.Item.Id, Original.Owner,
            Original.Item.Project, Original.Item.Version, action, action == "correct" ? Text : null);
        intent.Validate(); Pending = intent; return intent;
    }
    public void Reject() { if (Confirmed is null) Pending = null; }
    public void Confirm(MemoryEditAck ack) {
        if (Pending is null || ack.Id != Pending.Id) throw new InvalidOperationException("No matching captured memory edit.");
        Confirmed = ack;
    }
    public void Review(MemoryDetailView latest) {
        if (Pending is not null || latest.Item.Id != Original.Item.Id || latest.Owner != Original.Owner || latest.Item.Project != Original.Item.Project)
            throw new InvalidOperationException("Review must target the same record and cannot discard an uncertain edit.");
        Original = latest; // The GUI obtains an explicit owner review decision first; preserves authored text.
    }
}
