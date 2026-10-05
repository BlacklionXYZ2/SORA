using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

namespace Sora.CSharpTests;

public sealed class MemoryActivityTests
{
    private static readonly string Epoch = Guid.NewGuid().ToString("D");
    private static Dictionary<string, object?> Event(string type = "memory.retrieved", long sequence = 1) => new() {
        ["event_id"] = "event-memory-" + sequence, ["sequence"] = sequence,
        ["timestamp"] = DateTimeOffset.UtcNow.ToString("O"), ["event_type"] = type,
        ["payload"] = new Dictionary<string, object?> {
            ["instance_id"] = Epoch, ["dialogue_request_id"] = "dialogue-memory",
            ["retrieval_id"] = "retrieval-memory", ["source"] = "canonical", ["stage"] = "chooser",
            ["memories"] = new[] { new { memory_id = "memory-a", entity_version = 3 } },
            ["request_id"] = Guid.NewGuid(), ["host_id"] = Guid.NewGuid(), ["registry_generation"] = 0,
            ["status"] = "selected", ["memory_id"] = "memory-a", ["entity_version"] = 3,
            ["content"] = "PRIVATE-CONTENT", ["rationale"] = "PRIVATE-REASONING", ["lease_id"] = "PRIVATE-LEASE"
        }
    };
    private static Dictionary<string, object?> Payload(Dictionary<string, object?> data) =>
        (Dictionary<string, object?>)data["payload"]!;

    [Fact]
    public void RetrievalCopiesOnlyMetadataAndCannotImplySelectionOrModelThoughts()
    {
        var value = Assert.Single(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(Event())));
        Assert.Equal("Memory context selected", value.Label); Assert.Equal("context-selected", value.Status);
        Assert.Equal("retrieval-memory", value.RetrievalId); Assert.Equal("dialogue-memory", value.DialogueRequest);
        Assert.Equal(3, value.Version); Assert.Equal(Epoch, value.Core);
        Assert.DoesNotContain("PRIVATE", JsonSerializer.Serialize(value));
    }
    [Theory]
    [InlineData("selected", "Memory selected · host report")]
    [InlineData("already-visible", "Memory selected · host report")]
    [InlineData("deferred", "Memory deferred")]
    [InlineData("unavailable", "Memory unavailable")]
    [InlineData("rejected", "Memory rejected")]
    public void OnlyTerminalHostEventsDescribePresentation(string status, string label)
    {
        var data = Event("ui.memory.presented"); Payload(data)["status"] = status;
        var value = Assert.Single(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
        Assert.Equal(label, value.Label); Assert.Null(value.RetrievalId);
        Assert.DoesNotContain("PRIVATE", JsonSerializer.Serialize(value));
    }
    [Theory]
    [InlineData("pending")][InlineData("queued")][InlineData("dispatched")][InlineData("future-success")]
    public void DispatchAndUnknownStatusCannotBecomeSuccessChips(string status)
    {
        var data = Event("ui.memory.presented"); Payload(data)["status"] = status;
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
    }
    [Theory]
    [InlineData("instance_id")][InlineData("retrieval_id")][InlineData("dialogue_request_id")]
    [InlineData("source")][InlineData("stage")][InlineData("memories")]
    public void MalformedRetrievalIsAbsentNotPartiallyTrusted(string field)
    {
        var data = Event(); Payload(data)[field] = "wrong/private/value";
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
    }
    [Fact]
    public void NonNumericVersionsAndOversizedArraysAreRejectedWithoutThrowing()
    {
        var data = Event(); Payload(data)["memories"] = new[] { new { memory_id = "memory-a", entity_version = "3" } };
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
        Payload(data)["memories"] = Enumerable.Range(1, 65).Select(i => new { memory_id = "memory-" + i, entity_version = 1 }).ToArray();
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
        data = Event("ui.memory.presented"); Payload(data)["registry_generation"] = "0";
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
        data["sequence"] = "1";
        Assert.Empty(WidgetMemoryActivity.Parse(JsonSerializer.SerializeToElement(data)));
    }
    private sealed class Api : IWidgetApi
    {
        public object[] Events = []; public bool Resync, Offline; public long Sequence;
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-memory-activity-fixture");
        public readonly List<(string Path, JsonElement Body)> Posts = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            if (Offline) throw new IOException("Offline fixture");
            return Task.FromResult(JsonSerializer.SerializeToElement<object>(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Events, next_sequence = Sequence, more_available = false, resync_required = Resync },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 9, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            var value = JsonSerializer.SerializeToElement(body); Posts.Add((path, value));
            return Task.FromResult(JsonSerializer.SerializeToElement(new {
                schema_version = "1.0", instance_id = Epoch, request_id = value.GetProperty("request_id").GetGuid(),
                memory_id = value.GetProperty("memory_id").GetString(), expected_version = value.GetProperty("expected_version").GetInt64(), status = "pending"
            }));
        }
    }
    [Fact]
    public async Task SyncDeduplicatesBoundsRetainsOfflineAndClearsOnResyncOrNewCore()
    {
        var api = new Api { Events = Enumerable.Range(1, 70).Select(i => (object)Event(sequence: i)).ToArray(), Sequence = 70 };
        var sync = new WidgetSync(api); await sync.RefreshAsync();
        Assert.Equal(64, sync.Current.MemoryActivity.Count); Assert.Equal(7, sync.Current.MemoryActivity[0].Sequence);
        await sync.RefreshAsync(); Assert.Equal(64, sync.Current.MemoryActivity.Count);
        api.Offline = true; await sync.RefreshAsync(); Assert.False(sync.Current.Connected); Assert.Equal(64, sync.Current.MemoryActivity.Count);
        api.Offline = false; api.Events = []; api.Resync = true; await sync.RefreshAsync(); Assert.Empty(sync.Current.MemoryActivity);
        api.Resync = false; api.Events = [Event()]; await sync.RefreshAsync(); Assert.Single(sync.Current.MemoryActivity);
        sync.ResetForNewCore(); Assert.Empty(sync.Current.MemoryActivity); Assert.False(sync.Current.Connected);
    }
    [Fact]
    public async Task OwnerChipRequestUsesExactVersionAndReportsRequestedNotSelected()
    {
        var api = new Api(); using var session = new ShellSession(api, stateRoot: api.Root) { Draft = "Retained Chat draft" };
        await session.RefreshAsync(default); Assert.True(session.CanUseCore); Assert.False(session.CanSend);
        await session.RequestMemoryPanelAsync("memory-a", 3, default);
        var post = Assert.Single(api.Posts); Assert.Equal("/api/v1/ui/present-memory", post.Path);
        Assert.Equal("memory-a", post.Body.GetProperty("memory_id").GetString());
        Assert.Equal(3, post.Body.GetProperty("expected_version").GetInt64());
        Assert.Equal(Epoch, post.Body.GetProperty("instance_id").GetString());
        Assert.Equal(4, post.Body.EnumerateObject().Count());
        Assert.Contains("requested", session.Operation); Assert.DoesNotContain("confirmed", session.Operation);
        Assert.False(session.MutationBusy); Assert.Equal("Retained Chat draft", session.Draft);
        session.SetHostStatus("Host shutting down", true);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.RequestMemoryPanelAsync("memory-a", 3, default));
        Assert.Single(api.Posts);
    }
    [Fact]
    public void FinalPendingCheckRejectsCancellationAndMismatchedTargets()
    {
        var request = new MemoryPanelRequest(Epoch, Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "memory-a", 3, 0, "explicit", DateTimeOffset.UtcNow.AddSeconds(15));
        var data = new Dictionary<string, object?> { ["schema_version"] = "1.0", ["instance_id"] = Epoch,
            ["request_id"] = request.Request, ["memory_id"] = request.Id, ["expected_version"] = 3, ["status"] = "pending" };
        Assert.True(MemoryPanelClient.StillPending(JsonSerializer.SerializeToElement(data), request));
        data["status"] = "rejected"; Assert.False(MemoryPanelClient.StillPending(JsonSerializer.SerializeToElement(data), request));
        data["status"] = "pending"; data["expected_version"] = 4;
        Assert.Throws<InvalidDataException>(() => MemoryPanelClient.StillPending(JsonSerializer.SerializeToElement(data), request));
        data["expected_version"] = 3; data["instance_id"] = Guid.NewGuid().ToString();
        Assert.Throws<InvalidDataException>(() => MemoryPanelClient.StillPending(JsonSerializer.SerializeToElement(data), request));
    }
}
