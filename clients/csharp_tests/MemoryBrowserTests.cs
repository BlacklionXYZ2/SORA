using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class MemoryBrowserTests
{
    private const string Epoch = "00000000-0000-0000-0000-000000000123";
    private static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
    private static Dictionary<string, object?> Item(string id = "memory-a") => new() {
        ["schema_version"] = "1.0", ["memory_id"] = id, ["owner_id"] = "owner-local", ["project_id"] = "project-local",
        ["entity_version"] = 1, ["state"] = "active", ["scope"] = "dialogue", ["sensitivity"] = "private", ["retention"] = "durable",
        ["provenance"] = "owner-stated fixture", ["metadata_truncated"] = false, ["content_preview"] = "Remembered words",
        ["content_truncated"] = false, ["valid_until"] = null, ["content"] = "<script>inert</script> owner words",
        ["superseded_by"] = null, ["evidence_withheld"] = true,
        ["evidence"] = new[] { new { reference_id = "content-a", label = "Owner evidence", kind = "file" } },
        ["reasoning"] = "PRIVATE-REASONING", ["rationale"] = "PRIVATE-RATIONALE", ["capture_path"] = "PRIVATE-PATH"
    };
    private static Dictionary<string, object?> Header(string epoch = Epoch) => new() {
        ["schema_version"] = "1.0", ["instance_id"] = epoch, ["owner_id"] = "owner-local", ["project_id"] = "project-local",
        ["projection_revision"] = 17, ["observed_at"] = "2026-10-04T08:00:00+01:00", ["evidence_note"] = "Literal search; private capture excluded"
    };
    private static JsonElement Page(MemoryQuery? query = null, string epoch = Epoch, object[]? items = null)
    {
        query ??= new(); var data = Header(epoch);
        data["state_filter"] = query.State; data["project_filter"] = query.Project; data["scope_filter"] = query.Scope;
        data["query"] = query.Query; data["limit"] = 50; data["memories"] = items ?? [Item()]; data["total"] = 2; data["next_cursor"] = "YWJj";
        return Json(data);
    }
    private static JsonElement Detail(string id = "memory-a", string epoch = Epoch)
    { var data = Header(epoch); data["memory"] = Item(id); return Json(data); }
    private sealed class Api : IWidgetApi
    {
        public string Epoch = MemoryBrowserTests.Epoch;
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-memory-read-fixture");
        public List<string> Reads = [];
        public TaskCompletionSource<JsonElement>? Pending;
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Reads.Add(path);
            if (path == "/api/v1/memories/memory-a") return Pending?.Task ?? Task.FromResult(Detail(epoch: Epoch));
            if (path.StartsWith("/api/v1/memories?")) return Task.FromResult(Page(epoch: Epoch));
            return Task.FromResult(Json(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 10, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) => throw new InvalidOperationException("Read-only browser tests must not mutate");
    }
    [Fact]
    public void LiteralSearchIsEncodedAndNeverRoutesToAnExecutableOrDifferentEndpoint()
    {
        var path = new MemoryQuery("100%_exact & ../settings", Scope: "dialogue").Path("YWJj");
        Assert.StartsWith("/api/v1/memories?", path); Assert.Contains("q=100%25_exact%20%26%20..%2Fsettings", path);
        Assert.EndsWith("&cursor=YWJj", path); Assert.Equal("/api/v1/memories/memory-a", MemoryPresentation.DetailPath("memory-a"));
    }
    [Theory]
    [InlineData("../settings")][InlineData("memory-a/extra")][InlineData("bad?owner=other")][InlineData("")][InlineData("%2e%2e")]
    public void InvalidExactIdCannotReadAnotherResource(string id) => Assert.Throws<ArgumentException>(() => MemoryPresentation.DetailPath(id));
    [Theory]
    [InlineData("")][InlineData("bad!")][InlineData("abc&state=all")][InlineData("abc=1")]
    public void InvalidCursorIsRejectedBeforeRequest(string cursor) => Assert.Throws<ArgumentException>(() => new MemoryQuery().Path(cursor));
    [Fact]
    public void UnsupportedOversizedAndControlFiltersAreRejected()
    {
        foreach (var query in new[] { new MemoryQuery(State: "deleted"), new MemoryQuery(Project: "other-project"),
            new MemoryQuery(new string('x', 257)), new MemoryQuery("a\0b"), new MemoryQuery(Scope: new string('x', 129)) })
            Assert.Throws<ArgumentException>(() => query.Path());
    }
    [Fact]
    public void PublicProjectionIsCopiedWithoutPrivateUnknownFieldsOrInventedMetrics()
    {
        var page = MemoryPresentation.Page(Page(), new(), Epoch); var detail = MemoryPresentation.Detail(Detail(), "memory-a", Epoch);
        Assert.Single(page.Items); Assert.Equal("memory-a", detail.Item.Id);
        var text = MemoryPresentation.Inspection(detail); Assert.Contains("<script>inert</script>", text); Assert.Contains("not recorded", text);
        Assert.DoesNotContain("PRIVATE", text); Assert.DoesNotContain("PRIVATE", JsonSerializer.Serialize(detail));
        Assert.DoesNotContain("PRIVATE", JsonSerializer.Serialize(page)); Assert.Single(detail.Evidence);
    }
    [Theory]
    [InlineData("owner_id", "owner-other")][InlineData("project_id", "project-other")][InlineData("state", "deleted")]
    [InlineData("state", "unknown")][InlineData("valid_until", "2026-10-04T08:00:00")]
    public void CrossScopeDeletedAndNaiveTimestampRowsAreRejected(string field, string value)
    {
        var item = Item(); item[field] = value;
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Page(Page(items: [item]), new(), Epoch));
    }
    [Fact]
    public void WrongCoreIdFiltersDuplicateIdsAndOversizedPagesAreRejected()
    {
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Page(Page(epoch: Guid.NewGuid().ToString()), new(), Epoch));
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Page(Page(), new("different query"), Epoch));
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Page(Page(items: [Item(), Item()]), new(), Epoch));
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Page(Page(items: Enumerable.Range(0, 51).Select(i => (object)Item("memory-" + i)).ToArray()), new(), Epoch));
        Assert.Throws<InvalidDataException>(() => MemoryPresentation.Detail(Detail("memory-other"), "memory-a", Epoch));
    }
    [Fact]
    public void PrivateDuplicateOrOversizedEvidenceIsRejectedAndSuccessorIsNotFollowed()
    {
        var data = Header(); var item = Item(); data["memory"] = item;
        item["state"] = "superseded"; item["superseded_by"] = "memory-next";
        var value = MemoryPresentation.Detail(Json(data), "memory-a", Epoch);
        Assert.Equal("memory-a", value.Item.Id); Assert.Contains("inspect explicitly", MemoryPresentation.Inspection(value));
        foreach (var refs in new[] {
            new[] { new { reference_id = "capture-private", label = "Private", kind = "file" } },
            Enumerable.Repeat(new { reference_id = "content-a", label = "Evidence", kind = "file" }, 2).ToArray(),
            Enumerable.Range(0, 65).Select(i => new { reference_id = "content-" + i, label = "Evidence", kind = "file" }).ToArray()
        }) {
            item["evidence"] = refs;
            Assert.Throws<InvalidDataException>(() => MemoryPresentation.Detail(Json(data), "memory-a", Epoch));
        }
    }
    [Fact]
    public void LatePagesAfterNewQueryAndLateDetailsAfterNewSelectionCannotReplaceCurrentTarget()
    {
        var state = new MemoryBrowserState(); state.Observe(Epoch, true);
        var oldPage = state.BeginPage(new()); var newPage = state.BeginPage(new("new"));
        Assert.False(state.AcceptPage(oldPage, MemoryPresentation.Page(Page(), new(), Epoch)));
        Assert.True(state.AcceptPage(newPage, MemoryPresentation.Page(Page(new("new")), new("new"), Epoch)));
        var oldDetail = state.BeginDetail("memory-a"); state.Select("memory-b");
        Assert.False(state.AcceptDetail(oldDetail, MemoryPresentation.Detail(Detail(), "memory-a", Epoch)));
        Assert.Equal("memory-b", state.SelectedId); Assert.Null(state.Detail);
    }
    [Fact]
    public void DisconnectRetainsStaleCacheReconnectDoesNotMakeItFreshAndEpochChangeClearsTargets()
    {
        var state = new MemoryBrowserState(); state.Observe(Epoch, true);
        Assert.True(state.AcceptPage(state.BeginPage(new()), MemoryPresentation.Page(Page(), new(), Epoch)));
        Assert.True(state.AcceptDetail(state.BeginDetail("memory-a"), MemoryPresentation.Detail(Detail(), "memory-a", Epoch)));
        state.Observe(Epoch, false); Assert.NotNull(state.Page); Assert.NotNull(state.Detail);
        Assert.False(state.PageCurrent); Assert.False(state.DetailCurrent); Assert.Throws<InvalidOperationException>(() => state.BeginPage(new()));
        state.Observe(Epoch, true); Assert.False(state.DetailCurrent); Assert.False(state.PageCurrent);
        var late = state.BeginDetail("memory-a"); state.Observe(Guid.NewGuid().ToString(), true);
        Assert.False(state.AcceptDetail(late, MemoryPresentation.Detail(Detail(), "memory-a", Epoch)));
        Assert.Null(state.Page); Assert.Null(state.Detail); Assert.Null(state.SelectedId);
    }
    [Fact]
    public void WrongDetailScopeAndTargetCannotBecomeCurrent()
    {
        var state = new MemoryBrowserState(); state.Observe(Epoch, true);
        state.AcceptPage(state.BeginPage(new()), MemoryPresentation.Page(Page(), new(), Epoch));
        var read = state.BeginDetail("memory-a"); var value = MemoryPresentation.Detail(Detail(), "memory-a", Epoch);
        Assert.Throws<InvalidDataException>(() => state.AcceptDetail(read, value with { Owner = "owner-other" }));
        Assert.Throws<InvalidDataException>(() => state.AcceptDetail(read, value with { Item = value.Item with { Id = "memory-other" } }));
        Assert.False(state.DetailCurrent); Assert.Null(state.Detail);
    }
    [Fact]
    public async Task SharedReadersWorkWhenModelDownWithoutSendingOrChangingChatDraft()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root) { Draft = "Keep Chat draft" };
        await session.RefreshAsync(default); Assert.True(session.CanUseCore, session.Snapshot.Error); Assert.False(session.CanSend);
        var page = await session.MemoryPageAsync(new(), null, default); var detail = await session.MemoryDetailAsync("memory-a", default);
        Assert.Single(page.Items); Assert.Equal("memory-a", detail.Item.Id); Assert.Equal("Keep Chat draft", session.Draft);
        Assert.False(session.MutationBusy); Assert.Contains(new MemoryQuery().Path(), api.Reads);
        session.SetHostStatus("Shutting down", true); var count = api.Reads.Count;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MemoryPageAsync(new(), null, default)); Assert.Equal(count, api.Reads.Count);
    }
    [Fact]
    public async Task SharedReadFromReplacedCoreCannotBeReturnedAsCurrent()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default); Assert.True(session.CanUseCore, session.Snapshot.Error);
        var old = session.MemoryDetailAsync("memory-a", default); Assert.False(old.IsCompleted); api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Pending.SetResult(Detail()); await Assert.ThrowsAsync<InvalidOperationException>(() => old);
    }
    [Fact]
    public void MemoryPanelHasBoundedHostCommandAndUiOnlyPlacementWithoutStoringMemories()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-memory-placement");
        var options = ShellOptions.Parse(["--core-url", "http://127.0.0.1:18899", "--token-file", Path.Combine(root, "token"),
            "--state-root", root, "--show", "memory"]);
        Assert.Equal("memory", options.Panel); Assert.True(new HostCommand(1, "profile", "memory").Valid("profile"));
        Assert.False(new HostCommand(1, "profile", "memory/other").Valid("profile"));
        new ShellPreferences { Panels = new() { ["memory"] = new("fixture", 0, 0, 1060, 740, 96) } }.Validate();
    }
}
