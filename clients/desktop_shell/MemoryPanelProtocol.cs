using System.Globalization;
using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

public sealed record MemoryPanelRequest(string Epoch, Guid Host, Guid Lease, Guid Request,
    string Id, long Version, long Generation, string Activation, DateTimeOffset Expires);
public sealed record MemoryPanelAnchor(int X, int Y, int Width, int Height);
public sealed record MemoryPanelAck(MemoryPanelRequest Request, string Status, long Generation,
    bool Visible = false, string? SelectedId = null, long? SelectedVersion = null, MemoryPanelAnchor? Anchor = null)
{
    public object Body() => new { instance_id = Request.Epoch, host_id = Request.Host,
        lease_id = Request.Lease, request_id = Request.Request, memory_id = Request.Id,
        expected_version = Request.Version, registry_generation = Generation, status = Status,
        panel_visible = Visible, selected_id = SelectedId, selected_version = SelectedVersion,
        highlighted = Anchor is not null, anchor = Anchor is null ? null : new { x = Anchor.X,
            y = Anchor.Y, width = Anchor.Width, height = Anchor.Height } };
    public void Validate()
    {
        var success = Status is "selected" or "already-visible";
        if (Status is not ("selected" or "already-visible" or "deferred" or "unavailable" or "rejected")
            || Generation < Request.Generation || success && (!Visible || SelectedId != Request.Id
                || SelectedVersion != Request.Version || Anchor is not { Width: > 0, Height: > 0 })
            || !success && Anchor is not null)
            throw new InvalidDataException("Memory presentation acknowledgement does not match actual selection.");
    }
}

// Private leases live only in this host process. No independent timer, durable UI receipt or effect replay.
public sealed class MemoryPanelClient(string profile)
{
    private readonly Guid host = Guid.NewGuid();
    private Guid? lease;
    private string? epoch;
    private readonly Dictionary<Guid, (MemoryPanelRequest Request, MemoryPanelAck? Ack)> seen = [];
    public bool Busy { get; private set; }
    public string Status { get; private set; } = "Memory presentation not yet connected.";
    public Guid Host => host;
    internal int RetainedRequests => seen.Count;
    private static string Text(JsonElement value, string name) => value.GetProperty(name).GetString()
        ?? throw new InvalidDataException("Missing UI presentation field.");
    private static Guid GuidField(JsonElement value, string name) => Guid.Parse(Text(value, name));
    private static long Number(JsonElement value, string name, long minimum = 0)
    {
        var result = value.GetProperty(name).GetInt64();
        return result >= minimum ? result : throw new InvalidDataException("Invalid UI generation/version.");
    }
    private static DateTimeOffset Expiry(JsonElement value)
    {
        var text = Text(value, "expires_at");
        if (!(text.EndsWith('Z') || text.Length >= 6 && text[^6] is '+' or '-' && text[^3] == ':')
            || !DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out var result))
            throw new InvalidDataException("UI expiry needs an explicit timezone.");
        return result;
    }
    private static void Header(JsonElement value, string expected)
    {
        if (value.ValueKind != JsonValueKind.Object || Text(value, "schema_version") != "1.0"
            || Text(value, "instance_id") != expected || !Guid.TryParse(expected, out _))
            throw new InvalidDataException("UI presentation belongs to another/unsupported Core.");
    }
    public static bool StillPending(JsonElement value, MemoryPanelRequest request)
    {
        Header(value, request.Epoch);
        if (GuidField(value, "request_id") != request.Request || Text(value, "memory_id") != request.Id
            || Number(value, "expected_version", 1) != request.Version)
            throw new InvalidDataException("Pending Memory request target changed.");
        return Text(value, "status") == "pending";
    }
    public static MemoryPanelRequest Parse(JsonElement data, string epoch, Guid host, Guid lease)
    {
        Header(data, epoch); var id = Text(data, "memory_id"); MemoryPresentation.ValidateId(id);
        var activation = Text(data, "activation");
        if (GuidField(data, "host_id") != host || GuidField(data, "lease_id") != lease
            || Text(data, "panel") != "memory" || Text(data, "operation") != "select-highlight"
            || Text(data, "origin") is not ("owner" or "companion") || activation is not ("explicit" or "passive"))
            throw new InvalidDataException("UI request is not bound to this Memory host.");
        return new(epoch, host, lease, GuidField(data, "request_id"), id, Number(data, "expected_version", 1),
            Number(data, "registry_generation"), activation, Expiry(data));
    }
    public static bool CanPresent(MemoryPanelRequest request, string? epoch, bool draft, bool busy,
        bool visible, bool minimized, DateTimeOffset dismissed, DateTimeOffset now) =>
        request.Epoch == epoch && request.Expires > now && !draft && !busy && !minimized
        && (request.Activation == "explicit" || visible) && dismissed < request.Expires.AddSeconds(-15);

    public async Task RefreshAsync(IWidgetApi api, string currentEpoch, Func<long> generation,
        Func<bool> effectBusy, Func<MemoryPanelRequest, CancellationToken, Task<MemoryPanelAck>> present,
        CancellationToken token, Action<MemoryPanelRequest, bool>? settled = null)
    {
        if (Busy) return;
        if (epoch != currentEpoch) { epoch = currentEpoch; lease = null; seen.Clear(); }
        foreach (var stale in seen.Where(item => item.Value.Request.Expires.AddMinutes(5) < DateTimeOffset.UtcNow).Select(item => item.Key).ToArray())
            seen.Remove(stale); // Expired historical keys cannot starve a continuously renewed host.
        Busy = true;
        MemoryPanelRequest? active = null;
        bool transportUncertain = false;
        try {
            var currentGeneration = generation();
            var registration = await api.PostAsync("/api/v1/ui/host", new { instance_id = epoch,
                host_id = host, profile_key = profile.ToLowerInvariant(), lease_id = lease,
                registry_generation = currentGeneration, panels = new[] { "memory" } }, token);
            Header(registration, currentEpoch);
            if (GuidField(registration, "host_id") != host || Number(registration, "registry_generation") != currentGeneration
                || Expiry(registration) <= DateTimeOffset.UtcNow)
                throw new InvalidDataException("UI lease acknowledgement does not match this host.");
            var registeredLease = GuidField(registration, "lease_id");
            if (lease.HasValue && registeredLease != lease) seen.Clear();
            lease = registeredLease;
            var command = new { instance_id = epoch, host_id = host, lease_id = lease };
            var page = await api.PostAsync("/api/v1/ui/presentations/poll", command, token);
            Header(page, currentEpoch);
            if (GuidField(page, "host_id") != host || GuidField(page, "lease_id") != lease
                || page.GetProperty("requests") is not { ValueKind: JsonValueKind.Array } requests || requests.GetArrayLength() > 16)
                throw new InvalidDataException("Invalid bounded UI presentation batch.");
            foreach (var raw in requests.EnumerateArray()) {
                var request = Parse(raw, currentEpoch, host, registeredLease);
                active = request;
                if (seen.TryGetValue(request.Request, out var previous) && previous.Request != request)
                    throw new InvalidDataException("UI request key changed target/binding.");
                MemoryPanelAck ack;
                if (previous.Ack is { } stored) {
                    ack = stored;
                    if (stored.Status is "selected" or "already-visible"
                        && (generation() != stored.Generation || request.Expires <= DateTimeOffset.UtcNow)) {
                        ack = new(request, "unavailable", Math.Max(generation(), request.Generation));
                        seen[request.Request] = (request, ack); // Changed geometry/expiry is not a fresh positive ACK.
                    }
                }
                else if (seen.ContainsKey(request.Request))
                    ack = new(request, "unavailable", Math.Max(generation(), request.Generation));
                else {
                    if (seen.Count >= 256) throw new InvalidOperationException("UI presentation history full for this host lease.");
                    seen.Add(request.Request, (request, null)); // An uncertain callback never runs again for this key.
                    ack = effectBusy() || request.Expires <= DateTimeOffset.UtcNow
                        ? new(request, "deferred", Math.Max(generation(), request.Generation))
                        : await present(request, token);
                    if (ack.Request != request) throw new InvalidDataException("UI callback acknowledged another request.");
                    ack.Validate(); seen[request.Request] = (request, ack);
                }
                ack.Validate();
                var result = await api.PostAsync("/api/v1/ui/presentations/ack", ack.Body(), token);
                Header(result, currentEpoch);
                if (GuidField(result, "request_id") != request.Request || Text(result, "memory_id") != request.Id
                    || Number(result, "expected_version", 1) != request.Version
                    || Text(result, "status") is not ("selected" or "already-visible" or "deferred" or "unavailable" or "rejected" or "expired"))
                    throw new InvalidDataException("Core presentation result target/status mismatch.");
                var confirmed = Text(result, "status") is "selected" or "already-visible";
                if (confirmed) {
                    if (Text(result, "status") != ack.Status || Number(result, "registry_generation") != ack.Generation)
                        throw new InvalidDataException("Core result does not match the actual host acknowledgement.");
                    MemoryPresentation.ValidateId(Text(result, "event_id"));
                }
                settled?.Invoke(request, confirmed); active = null;
                Status = "Memory presentation: " + Text(result, "status") + ".";
            }
        }
        catch (SoraRequestException error) when (error.Code == "UI_HOST_UNAVAILABLE") {
            lease = null; Status = "Memory host lease expired; old requests will not replay.";
        }
        catch (Exception error) when (error is not OperationCanceledException || !token.IsCancellationRequested) {
            transportUncertain = error is HttpRequestException and not SoraRequestException
                || error is OperationCanceledException;
            Status = "Memory presentation unavailable/unconfirmed; no selection replay.";
        }
        finally {
            if (active is not null && !(transportUncertain && seen.TryGetValue(active.Request, out var outstanding)
                && outstanding.Ack is { Status: "selected" or "already-visible" } actual
                && actual.Generation == generation() && active.Expires > DateTimeOffset.UtcNow))
                settled?.Invoke(active, false);
            Busy = false;
        }
    }
}
