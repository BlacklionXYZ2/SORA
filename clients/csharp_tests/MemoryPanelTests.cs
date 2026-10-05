using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

namespace Sora.CSharpTests;

public sealed class MemoryPanelTests
{
    private static readonly string Epoch = Guid.NewGuid().ToString("D");
    private static readonly Guid Host = Guid.NewGuid(), Lease = Guid.NewGuid();
    private static MemoryPanelRequest Request(string activation = "explicit") =>
        new(Epoch, Host, Lease, Guid.NewGuid(), "memory-a", 1, 0, activation, DateTimeOffset.UtcNow.AddSeconds(15));
    private static Dictionary<string, object?> Raw(MemoryPanelRequest value) => new() {
        ["schema_version"] = "1.0", ["instance_id"] = value.Epoch, ["host_id"] = value.Host,
        ["lease_id"] = value.Lease, ["request_id"] = value.Request, ["memory_id"] = value.Id,
        ["expected_version"] = value.Version, ["registry_generation"] = value.Generation,
        ["panel"] = "memory", ["operation"] = "select-highlight", ["origin"] = "companion",
        ["activation"] = value.Activation, ["expires_at"] = value.Expires,
        ["reasoning"] = "PRIVATE-CAPTURE", ["content"] = "PRIVATE-CONTENT"
    };
    private static MemoryPanelAck Selected(MemoryPanelRequest value) =>
        new(value, "selected", 0, true, value.Id, value.Version, new(-100, 50, 600, 300));
    [Fact]
    public void PublicRequestCopiesOnlyBindingsAndNeverPrivateContent()
    {
        var value = Request();
        var parsed = MemoryPanelClient.Parse(JsonSerializer.SerializeToElement(Raw(value)), Epoch, Host, Lease);
        Assert.Equal(value, parsed); Assert.DoesNotContain("PRIVATE", parsed.ToString());
        var ack = Selected(parsed); ack.Validate();
        var body = JsonSerializer.Serialize(ack.Body());
        Assert.DoesNotContain("PRIVATE", body); Assert.DoesNotContain("authorized_by", body);
    }
    [Theory]
    [InlineData("instance_id")][InlineData("host_id")][InlineData("lease_id")]
    [InlineData("memory_id")][InlineData("expected_version")][InlineData("registry_generation")]
    [InlineData("panel")][InlineData("operation")][InlineData("origin")][InlineData("activation")]
    public void WrongBindingOrUnknownActionIsRejected(string field)
    {
        var data = Raw(Request());
        data[field] = field is "expected_version" or "registry_generation" ? -1 : "wrong/target";
        Assert.ThrowsAny<Exception>(() => MemoryPanelClient.Parse(JsonSerializer.SerializeToElement(data), Epoch, Host, Lease));
    }
    [Fact]
    public void DraftBusyDismissedMinimizedPassiveAndExpiredRequestsCannotPresent()
    {
        var request = Request(); var now = request.Expires.AddSeconds(-15); var old = DateTimeOffset.MinValue;
        Assert.True(MemoryPanelClient.CanPresent(request, Epoch, false, false, false, false, old, now));
        Assert.False(MemoryPanelClient.CanPresent(request, Epoch, true, false, true, false, old, now));
        Assert.False(MemoryPanelClient.CanPresent(request, Epoch, false, true, true, false, old, now));
        Assert.False(MemoryPanelClient.CanPresent(request, Epoch, false, false, true, true, old, now));
        Assert.False(MemoryPanelClient.CanPresent(request, Epoch, false, false, true, false, now, now));
        Assert.False(MemoryPanelClient.CanPresent(request, Guid.NewGuid().ToString(), false, false, true, false, old, now));
        Assert.False(MemoryPanelClient.CanPresent(request with { Expires = now }, Epoch, false, false, true, false, old, now));
        Assert.False(MemoryPanelClient.CanPresent(Request("passive"), Epoch, false, false, false, false, old, now));
        Assert.True(MemoryPanelClient.CanPresent(Request("passive"), Epoch, false, false, true, false, old, now));
    }
    [Fact]
    public void SuccessRequiresExactVisibleHighlightGeometry()
    {
        var ack = Selected(Request());
        foreach (var bad in new[] { ack with { Visible = false }, ack with { SelectedId = "memory-other" },
            ack with { SelectedVersion = 2 }, ack with { Anchor = null }, ack with { Generation = -1 },
            ack with { Anchor = new(0, 0, 0, 300) }, ack with { Status = "deferred" } })
            Assert.Throws<InvalidDataException>(() => bad.Validate());
    }
    private sealed class Api : IWidgetApi
    {
        public string CurrentEpoch = Epoch;
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-memory-panel-fixture");
        public Guid CurrentHost, CurrentLease = Guid.NewGuid();
        public MemoryPanelRequest? Pending;
        public int AckWrites, Registrations;
        public bool LoseAck, ChangeResult, WithholdEvent;
        public bool EmptyPoll;
        public long RegisteredGeneration;
        public Task<JsonElement> GetAsync(string path, CancellationToken token) => Task.FromResult(JsonSerializer.SerializeToElement<object>(path.Split('?')[0] switch {
            "/api/v1/runtime/identity" => new { version = 1, instance_id = CurrentEpoch, state_root = Root },
            "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
            "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
            "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
            "/api/v1/status" => new { providers = new Dictionary<string, object>() },
            "/api/v1/projections/settings" => new { settings_version = 9, fields = Array.Empty<object>() },
            _ => throw new InvalidOperationException(path)
        }));
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            var data = JsonSerializer.SerializeToElement(body);
            if (path == "/api/v1/ui/host") {
                Registrations++; CurrentHost = data.GetProperty("host_id").GetGuid(); RegisteredGeneration = data.GetProperty("registry_generation").GetInt64();
                Assert.Equal(new string('a', 64), data.GetProperty("profile_key").GetString());
                return Task.FromResult(JsonSerializer.SerializeToElement(new { schema_version = "1.0", instance_id = CurrentEpoch,
                    host_id = CurrentHost, lease_id = CurrentLease, registry_generation = RegisteredGeneration, expires_at = DateTimeOffset.UtcNow.AddSeconds(30) }));
            }
            if (path.EndsWith("/poll")) {
                Pending ??= Request() with { Epoch = CurrentEpoch, Host = CurrentHost, Lease = CurrentLease, Generation = RegisteredGeneration };
                return Task.FromResult(JsonSerializer.SerializeToElement(new { schema_version = "1.0", instance_id = CurrentEpoch,
                    host_id = CurrentHost, lease_id = CurrentLease, requests = EmptyPoll ? Array.Empty<Dictionary<string, object?>>() : new[] { Raw(Pending) } }));
            }
            AckWrites++;
            if (LoseAck) throw new HttpRequestException("Lost reply");
            return Task.FromResult(JsonSerializer.SerializeToElement(new { schema_version = "1.0", instance_id = CurrentEpoch,
                request_id = data.GetProperty("request_id").GetGuid(), memory_id = ChangeResult ? "memory-wrong" : Pending!.Id,
                expected_version = 1, status = data.GetProperty("status").GetString(), registry_generation = data.GetProperty("registry_generation").GetInt64(),
                event_id = WithholdEvent ? null : "event-presentation" }));
        }
    }
    [Fact]
    public async Task LostAckRetriesOnlyFrozenReceiptNeverTheSelection()
    {
        var api = new Api { LoseAck = true }; var client = new MemoryPanelClient(new string('A', 64)); var selections = 0;
        Task<MemoryPanelAck> Present(MemoryPanelRequest request, CancellationToken _) { selections++; return Task.FromResult(Selected(request)); }
        await client.RefreshAsync(api, Epoch, () => 0, () => false, Present, default);
        api.LoseAck = false;
        await client.RefreshAsync(api, Epoch, () => 0, () => false, Present, default);
        Assert.Equal(1, selections); Assert.Equal(2, api.AckWrites); Assert.Contains("selected", client.Status); Assert.False(client.Busy);
    }
    [Fact]
    public async Task ChangedRegistryAfterLostAckCannotResendPositiveReceipt()
    {
        var api = new Api { LoseAck = true }; var client = new MemoryPanelClient(new string('a', 64)); var selections = 0;
        Task<MemoryPanelAck> Present(MemoryPanelRequest request, CancellationToken _) { selections++; return Task.FromResult(Selected(request)); }
        await client.RefreshAsync(api, Epoch, () => 0, () => false, Present, default);
        api.LoseAck = false;
        await client.RefreshAsync(api, Epoch, () => 1, () => false, Present, default);
        Assert.Equal(1, selections); Assert.Contains("unavailable", client.Status);
    }
    [Fact]
    public async Task UncertainCallbackNeverReplaysSelectionAndBusyDefers()
    {
        var api = new Api(); var client = new MemoryPanelClient(new string('a', 64)); var attempts = 0;
        Task<MemoryPanelAck> Fails(MemoryPanelRequest request, CancellationToken _) { attempts++; throw new IOException("UI failure"); }
        await client.RefreshAsync(api, Epoch, () => 0, () => false, Fails, default);
        await client.RefreshAsync(api, Epoch, () => 0, () => false, Fails, default);
        Assert.Equal(1, attempts); Assert.Equal(1, api.AckWrites); Assert.Contains("unavailable", client.Status);
        var busy = new MemoryPanelClient(new string('a', 64)); var other = new Api();
        await busy.RefreshAsync(other, Epoch, () => 0, () => true, Fails, default);
        Assert.Equal(1, attempts); Assert.Contains("deferred", busy.Status);
    }
    [Theory]
    [InlineData(true, false)][InlineData(false, true)]
    public async Task WrongTargetOrMissingEventCannotConfirmSuccess(bool wrong, bool noEvent)
    {
        var api = new Api { ChangeResult = wrong, WithholdEvent = noEvent };
        var client = new MemoryPanelClient(new string('a', 64));
        bool? confirmed = null;
        await client.RefreshAsync(api, Epoch, () => 0, () => false, (request, _) => Task.FromResult(Selected(request)), default,
            (_, success) => confirmed = success);
        Assert.Contains("unconfirmed", client.Status); Assert.False(client.Busy);
        Assert.False(confirmed);
    }
    [Fact]
    public async Task ExpiredHistoricalKeysPruneWithoutSelectionReplay()
    {
        var api = new Api(); var client = new MemoryPanelClient(new string('a', 64));
        // Bind the fake host before supplying a deliberately obsolete queued request.
        api.EmptyPoll = true;
        await client.RefreshAsync(api, Epoch, () => 0, () => false, (request, _) => Task.FromResult(Selected(request)), default);
        api.Pending = Request() with { Host = api.CurrentHost, Lease = api.CurrentLease, Expires = DateTimeOffset.UtcNow.AddMinutes(-6) };
        api.EmptyPoll = false; var selected = 0;
        await client.RefreshAsync(api, Epoch, () => 0, () => false, (request, _) => { selected++; return Task.FromResult(Selected(request)); }, default);
        Assert.Equal(1, client.RetainedRequests); Assert.Equal(0, selected);
        api.EmptyPoll = true;
        await client.RefreshAsync(api, Epoch, () => 0, () => false, (request, _) => { selected++; return Task.FromResult(Selected(request)); }, default);
        Assert.Equal(0, client.RetainedRequests); Assert.Equal(0, selected);
    }
    [Fact]
    public async Task SharedSessionOptInWorksModelDownAndCompatibilityDoesNotRegister()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root);
        await session.RefreshAsync(default); Assert.Equal(0, api.Registrations); Assert.False(session.CanSend);
        var calls = 0;
        session.EnableMemoryPresentation(new string('a', 64), () => 0, (request, _) => { calls++; return Task.FromResult(Selected(request)); });
        await session.RefreshAsync(default);
        Assert.Equal(1, api.Registrations); Assert.Equal(1, calls); Assert.True(session.CanUseCore); Assert.False(session.MemoryPresentationBusy);
        Assert.Throws<InvalidOperationException>(() => session.EnableMemoryPresentation(new string('a', 64), () => 0, (request, _) => Task.FromResult(Selected(request))));
        using var prototype = new ShellSession(api);
        Assert.Throws<InvalidOperationException>(() => prototype.EnableMemoryPresentation(new string('a', 64), () => 0, (request, _) => Task.FromResult(Selected(request))));
    }
}
