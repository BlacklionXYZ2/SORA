using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class MemoryEditTests
{
    private const string Epoch = "00000000-0000-0000-0000-000000000123";
    private const string OtherEpoch = "00000000-0000-0000-0000-000000000456";
    private static MemoryDetailView Detail(string id = "memory-a", string epoch = Epoch, long version = 1, string state = "active") =>
        new(epoch, "owner-local", "project-local", 7, "2026-10-04T08:00:00+01:00", "Evidence withheld",
            new(id, "owner-local", "project-local", version, state, "dialogue", "private", "durable", "owner", false, "old", false, null),
            "Original owner words", null, [], false);
    private static JsonElement Ack(MemoryMutationIntent intent, string epoch = Epoch, Action<Dictionary<string, object?>>? alter = null)
    {
        var data = new Dictionary<string, object?> {
            ["schema_version"] = "1.0", ["instance_id"] = epoch, ["committed_instance_id"] = intent.Epoch,
            ["request_id"] = intent.RequestId.ToString("D"), ["owner_id"] = intent.Owner, ["project_id"] = intent.Project,
            ["memory_id"] = intent.Id, ["action"] = intent.Action, ["expected_version"] = intent.Version,
            ["entity_version"] = intent.Version + 1, ["successor_id"] = intent.Action == "correct" ? "memory-new" : null,
            ["successor_version"] = intent.Action == "correct" ? 1 : null, ["content_sha256"] = intent.ContentHash,
            ["projection_revision"] = 8, ["event_id"] = "event-ack", ["committed_at"] = "2026-10-04T08:10:00+01:00",
            ["replayed"] = true, ["retention_note"] = MemoryEditPresentation.ForgetMeaning,
            ["reasoning"] = "PRIVATE-REASONING", ["capture_path"] = "PRIVATE-PATH"
        };
        alter?.Invoke(data); return JsonSerializer.SerializeToElement(data);
    }
    [Fact]
    public void DefiniteAdmissionRejectionsKeepEditableDraftButUnknownFailuresFreezeIt()
    {
        foreach (var code in new[] { "MEMORY_VERSION_CONFLICT", "MEMORY_STATE_CONFLICT", "CORE_INSTANCE_CHANGED", "RUNTIME_CHANGED", "RUNTIME_SHUTTING_DOWN", "INVALID_MEMORY_MUTATION", "NOT_FOUND", "FORBIDDEN" })
            Assert.True(MemoryEditPresentation.DefiniteRejection(code));
        foreach (var code in new[] { "MEMORY_UNAVAILABLE", "INTERNAL_ERROR", "MEMORY_REQUEST_CONFLICT", "TIMEOUT", null })
            Assert.False(MemoryEditPresentation.DefiniteRejection(code));
    }
    [Fact]
    public void CorrectionBoundCountsUnicodeScalarsNotUtf16CodeUnits()
    {
        var draft = new MemoryEditDraft(Detail()); draft.Edit(string.Concat(Enumerable.Repeat("🐱", 16384)));
        Assert.Equal(32768, draft.Begin("correct", Epoch).Content!.Length);
        var oversized = new MemoryEditDraft(Detail()); oversized.Edit(new string('a', 16385));
        Assert.Throws<ArgumentException>(() => oversized.Begin("correct", Epoch)); Assert.Null(oversized.Pending);
    }
    [Fact]
    public void DraftPinsIdentityVersionAndFreezesExactBodyForUnknownRetry()
    {
        var draft = new MemoryEditDraft(Detail()); draft.Edit("Corrected words 🐱");
        var first = draft.Begin("correct", Epoch); var again = draft.Begin("correct", Epoch);
        Assert.Same(first, again); Assert.True(draft.NeedsResolution); Assert.Equal("memory-a", first.Id); Assert.Equal(1, first.Version);
        Assert.Equal("/api/v1/memories/memory-a/correct", first.Path);
        Assert.Throws<InvalidOperationException>(() => draft.Edit("changed after submission"));
        Assert.Throws<InvalidOperationException>(() => draft.Begin("forget", Epoch));
        Assert.Throws<InvalidOperationException>(() => draft.Begin("correct", OtherEpoch));
        Assert.Throws<InvalidOperationException>(() => draft.Review(Detail(version: 2)));
        Assert.DoesNotContain("owner_id", JsonSerializer.Serialize(first.Body()));
    }
    [Fact]
    public void ConflictReviewKeepsAuthoredTextAndRequiresSameCanonicalRecord()
    {
        var draft = new MemoryEditDraft(Detail()); draft.Edit("Authored correction"); draft.Begin("correct", Epoch); draft.Reject();
        Assert.Throws<InvalidOperationException>(() => draft.Review(Detail("memory-wrong")));
        draft.Review(Detail(epoch: OtherEpoch, version: 2));
        Assert.Equal("Authored correction", draft.Text); Assert.Equal(2, draft.Begin("correct", OtherEpoch).Version);
    }
    [Theory]
    [InlineData("expired")][InlineData("superseded")]
    public void InactiveCannotBeCorrectedButForgetIsExactRecord(string state)
    {
        var draft = new MemoryEditDraft(Detail(state: state));
        Assert.Throws<InvalidOperationException>(() => draft.Begin("correct", Epoch));
        Assert.Null(draft.Begin("forget", Epoch).Content);
    }
    [Fact]
    public void HistoricalReceiptCanResolveAcrossEpochButDoesNotProveCurrentState()
    {
        var draft = new MemoryEditDraft(Detail()); var intent = draft.Begin("correct", Epoch);
        var ack = MemoryEditPresentation.Ack(Ack(intent, OtherEpoch), intent, OtherEpoch);
        Assert.True(ack.Historical); Assert.Equal(Epoch, ack.CommittedEpoch); Assert.Equal("memory-new", ack.Successor);
        Assert.DoesNotContain("PRIVATE", ack.ToString()); draft.Confirm(ack);
        Assert.False(draft.NeedsResolution); Assert.Throws<InvalidOperationException>(() => draft.Begin("correct", Epoch));
    }
    [Theory]
    [InlineData("memory_id")][InlineData("owner_id")][InlineData("project_id")][InlineData("request_id")]
    [InlineData("action")][InlineData("instance_id")][InlineData("content_sha256")]
    public void ReceiptCannotConfirmDifferentTargetOrAuthoredContent(string field)
    {
        var intent = new MemoryEditDraft(Detail()).Begin("correct", Epoch);
        Assert.ThrowsAny<Exception>(() => MemoryEditPresentation.Ack(Ack(intent, alter: d => d[field] = "wrong"), intent, Epoch));
    }
    [Fact]
    public void ForgetReceiptMustNotClaimSuccessorOrReturnOldContent()
    {
        var intent = new MemoryEditDraft(Detail()).Begin("forget", Epoch);
        var ack = MemoryEditPresentation.Ack(Ack(intent), intent, Epoch); Assert.Null(ack.Successor);
        Assert.Throws<InvalidDataException>(() => MemoryEditPresentation.Ack(Ack(intent, alter: d => d["successor_id"] = "memory-other"), intent, Epoch));
        Assert.Contains("not erased", MemoryEditPresentation.ForgetMeaning);
    }
    [Theory]
    [InlineData("")][InlineData(" ")][InlineData("bad\0text")]
    public void InvalidCorrectionIsNotCaptured(string text)
    {
        var draft = new MemoryEditDraft(Detail()); draft.Edit(text);
        Assert.Throws<ArgumentException>(() => draft.Begin("correct", Epoch)); Assert.Null(draft.Pending);
    }
    private sealed class Api : IWidgetApi
    {
        public string Epoch = MemoryEditTests.Epoch;
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-memory-edit-fixture");
        public int Writes;
        public MemoryMutationIntent? LastIntent;
        public TaskCompletionSource<JsonElement>? PendingWrite;
        public bool LoseAck;
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            if (path.StartsWith("/api/v1/memory-mutations/")) return Task.FromResult(Ack(LastIntent!, Epoch));
            return Task.FromResult(JsonSerializer.SerializeToElement<object>(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 10, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Writes++; var json = JsonSerializer.SerializeToElement(body);
            LastIntent = new(json.GetProperty("instance_id").GetString()!, Guid.Parse(json.GetProperty("request_id").GetString()!),
                path.Split('/')[4], "owner-local", "project-local", json.GetProperty("expected_version").GetInt64(), path.Split('/')[5],
                json.TryGetProperty("content", out var content) ? content.GetString() : null);
            if (LoseAck) throw new HttpRequestException("Lost acknowledgement");
            return PendingWrite?.Task ?? Task.FromResult(Ack(LastIntent, Epoch));
        }
    }
    [Fact]
    public async Task ModelDownDoesNotBlockMemoryEditAndReceiptReadDoesNotReplay()
    {
        var api = new Api { LoseAck = true }; using var session = new ShellSession(api, api.Root);
        await session.RefreshAsync(default); Assert.True(session.CanUseCore); Assert.False(session.Snapshot.DialogueReady);
        var intent = new MemoryEditDraft(Detail()).Begin("correct", Epoch);
        await Assert.ThrowsAsync<HttpRequestException>(() => session.EditMemoryAsync(intent, CancellationToken.None));
        var receipt = await session.MemoryReceiptAsync(intent, CancellationToken.None);
        Assert.True(receipt.Historical); Assert.Equal(1, api.Writes);
        api.Epoch = OtherEpoch; await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.EditMemoryAsync(intent, CancellationToken.None)); Assert.Equal(1, api.Writes);
        Assert.Equal(OtherEpoch, (await session.MemoryReceiptAsync(intent, CancellationToken.None)).Epoch); Assert.Equal(1, api.Writes);
    }
    [Fact]
    public async Task PendingMemoryMutationSharesEffectSlotAndRejectsOldEpochAck()
    {
        var api = new Api { PendingWrite = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default); Assert.True(session.CanUseCore);
        var intent = new MemoryEditDraft(Detail()).Begin("correct", Epoch);
        var write = session.EditMemoryAsync(intent, CancellationToken.None); Assert.False(write.IsCompleted); Assert.True(session.MutationBusy);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.EditMemoryAsync(intent, CancellationToken.None)); Assert.Equal(1, api.Writes);
        api.Epoch = OtherEpoch; await session.RefreshAsync(default); api.PendingWrite.SetResult(Ack(intent));
        await Assert.ThrowsAsync<InvalidOperationException>(() => write); Assert.False(session.MutationBusy);
    }
}
