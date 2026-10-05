using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellRetainedTests
{
    private static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
    private sealed class Api : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-retained-fixture");
        public bool Offline, ProjectionError, HasContent = true, HasCard = true;
        public int Version;
        public int Runs = 0;
        public string CardStatus = "planned", ReplyId = "task-a";
        public TaskCompletionSource<JsonElement>? Pending;
        public Exception? PostError;
        public readonly List<string> Gets = [];
        public readonly List<(string Path, JsonElement Body)> Posts = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Gets.Add(path); if (Offline) throw new IOException("Offline fixture");
            if (ProjectionError && path == "/api/v1/projections/objects") throw new IOException("Objects unavailable");
            return Task.FromResult(Json(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, state = "idle", model_state = "down" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 9, settings_revision = 0, fields = Array.Empty<object>() },
                "/api/v1/projections/objects" => new { cards = HasCard ? new[] { new { task_id = "task-a", column = "DONE", status = CardStatus,
                    intent = "Synthetic note", assigned_agent = "codex", board_version = Version, run_count = Runs,
                    column_source = "manual", needs_attention = false, updated_at = "2026-10-04T01:00:00Z" } } : [] },
                "/api/v1/content/references" => new { references = HasContent ? new[] { new { reference_id = "content-a", kind = "file", label = "Synthetic file", path = "C:\\fixture\\note.txt" } } : [] },
                "/api/v1/extensions" => new[] { new { extension_id = "fixture-ext", depth = "integration", version = "1", enabled = false,
                    capability_ids = new[] { "fixture-cap" }, required_grants = new[] { "historic-grant" } } },
                "/api/v1/projections/capabilities" => new { active_extensions = Array.Empty<string>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Posts.Add((path, Json(body))); if (PostError is not null) throw PostError;
            return Pending?.Task ?? Task.FromResult(path == "/api/v1/content/navigate"
                ? Json(new { reference_id = "content-a", status = "unsupported", reason = "No configured handler", limitations = Array.Empty<string>() })
                : Json(new { task_id = ReplyId, status = "planned" }));
        }
    }
    [Fact]
    public async Task SharedProjectionIsOptInAndWorksWithModelDownWithoutEffects()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        Assert.DoesNotContain("/api/v1/projections/objects", api.Gets); session.EnableRetained(); await session.RefreshAsync(default);
        Assert.True(session.RetainedCurrent); Assert.False(session.CanSend); Assert.Single(session.Retained.BoardCards);
        Assert.Single(session.Retained.Content); Assert.Single(session.Retained.Extensions); Assert.Empty(api.Posts);
        Assert.Equal(1, api.Gets.Count(path => path == "/api/v1/projections/objects"));
        await Assert.ThrowsAsync<NotSupportedException>(() => session.RetainedApi.GetAsync("/api/v1/tasks", default));
    }
    [Fact]
    public async Task FailedProjectionRetainsMarkedStaleCacheThenRecovers()
    {
        var api = new Api(); using var session = new ShellSession(api); session.EnableRetained(); await session.RefreshAsync(default);
        api.ProjectionError = true; await session.RefreshAsync(default);
        Assert.False(session.RetainedCurrent); Assert.False(session.Retained.Companion.Connected);
        Assert.Single(session.Retained.BoardCards); Assert.Contains("stale", session.Retained.Error);
        api.ProjectionError = false; await session.RefreshAsync(default); Assert.True(session.RetainedCurrent); Assert.Empty(api.Posts);
    }
    [Fact]
    public async Task LostPlanReplyRetainsBodyKeyEpochAndNeverRefreshReplays()
    {
        var api = new Api { PostError = new IOException("Lost response") }; using var session = new ShellSession(api, api.Root);
        await session.RefreshAsync(default); var request = new { intent = "Exact note", idempotency_key = "plan-key" };
        await Assert.ThrowsAsync<IOException>(() => session.MutateRetainedAsync("/api/v1/board/cards", request, default));
        await session.RefreshAsync(default); Assert.Single(api.Posts);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync("/api/v1/board/cards", new { intent = "Different note", idempotency_key = "plan-key" }, default));
        api.PostError = null; await session.MutateRetainedAsync("/api/v1/board/cards", request, default); Assert.Equal(2, api.Posts.Count);
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync("/api/v1/board/cards", request, default)); Assert.Equal(2, api.Posts.Count);
    }
    [Theory]
    [InlineData("assign")][InlineData("move")][InlineData("remove")]
    public async Task BoardEditsRequireExactCurrentVersionAndIdentity(string action)
    {
        var api = new Api { Version = 2 }; using var session = new ShellSession(api); await session.RefreshAsync(default);
        object body = action == "assign" ? new { expected_version = 1, assigned_agent = "hermes" }
            : action == "move" ? new { expected_version = 1, column = "TODO" } : new { expected_version = 1 };
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync(FullAppProjection.BoardPath("task-a", action), body, default));
        Assert.Empty(api.Posts); api.Version = 1; api.ReplyId = "task-other";
        await Assert.ThrowsAsync<InvalidDataException>(() => session.MutateRetainedAsync(FullAppProjection.BoardPath("task-a", action), body, default)); Assert.Single(api.Posts);
    }
    [Fact]
    public async Task LostNonIdempotentRetryCannotBeReplayedEvenIfStillFailed()
    {
        var api = new Api { CardStatus = "failed", PostError = new IOException("Lost retry ACK") };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<IOException>(() => session.MutateRetainedAsync("/api/v1/board/cards/task-a/retry", new { }, default));
        api.PostError = null; await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync("/api/v1/board/cards/task-a/retry", new { }, default)); Assert.Single(api.Posts);
    }
    [Fact]
    public async Task NavigationRevalidatesExactRegisteredIdAndDisplaysFailureNotSuccess()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        var request = FullAppProjection.NavigationRequest("content-a", "open"); api.HasContent = false;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync("/api/v1/content/navigate", request, default)); Assert.Empty(api.Posts);
        api.HasContent = true; var result = await session.MutateRetainedAsync("/api/v1/content/navigate", request, default);
        Assert.Contains("unsupported", RetainedRequests.NavigationOutcome(result, "content-a")); Assert.Single(api.Posts);
        Assert.Equal("content-a", api.Posts[0].Body.GetProperty("explicit_reference_id").GetString());
    }
    [Fact]
    public async Task RetainedWritesSerializeAndOldEpochReplyIsNotSuccess()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var pending = session.MutateRetainedAsync("/api/v1/board/cards/task-a/move", new { expected_version = 0, column = "TODO" }, default);
        Assert.True(session.MutationBusy);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Other work", null, idempotencyKey: "other"));
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Pending.SetResult(Json(new { task_id = "task-a" })); await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        Assert.False(session.MutationBusy); Assert.Single(api.Posts);
    }
    [Theory]
    [InlineData("offline")][InlineData("host-block")][InlineData("disposed")]
    public async Task RetainedActionsFailClosedWithoutEffects(string condition)
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        if (condition == "offline") { api.Offline = true; await session.RefreshAsync(default); }
        if (condition == "host-block") session.SetHostStatus("Quit pending", true);
        if (condition == "disposed") session.Dispose();
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.MutateRetainedAsync("/api/v1/board/cards", new { intent = "Note", idempotency_key = "key" }, default)); Assert.Empty(api.Posts);
    }
    [Theory]
    [InlineData("codex")][InlineData("claude")][InlineData("hermes")][InlineData("antigravity")][InlineData("sora")][InlineData("unassigned")]
    public void NoteDraftPinsIntentAssigneeAndKnownAdmission(string assignee)
    {
        var draft = new BoardNoteDraft(); draft.Begin("Note", assignee); var key = draft.Key; draft.Begin("Note", assignee);
        Assert.Equal(key, draft.Key); Assert.Throws<InvalidOperationException>(() => draft.Begin("Other", assignee));
        Assert.Throws<ArgumentException>(() => draft.Acknowledge("../settings")); draft.Acknowledge("task-a");
        Assert.Throws<InvalidOperationException>(() => draft.Acknowledge("task-b")); draft.Confirm();
        Assert.True(draft.Confirmed); Assert.Throws<InvalidOperationException>(() => draft.Begin("Note", assignee));
    }
    [Theory]
    [InlineData("board")][InlineData("content")][InlineData("integrations")]
    public void RetainedPanelsAreRecognizedUiOnlyCommands(string panel)
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-retained-command");
        Assert.Equal(panel, ShellOptions.Parse(["--core-url", "http://127.0.0.1:18795", "--token-file", Path.Combine(root, "token"), "--state-root", root, "--show", panel]).Panel);
        Assert.True(new HostCommand(1, "profile", panel).Valid("profile"));
        new ShellPreferences { BoardExpanded = true, Panels = new() { [panel] = new("fixture", 0, 0, 800, 700, 144) } }.Validate();
    }
    [Fact]
    public void RequestVocabularyAndAcknowledgementsRejectArbitraryEffects()
    {
        Assert.Throws<ArgumentException>(() => RetainedRequests.Validate("/api/v1/board/cards/task-a/move", Json(new { expected_version = "zero", column = "DONE" })));
        Assert.Throws<ArgumentException>(() => RetainedRequests.Validate("/api/v1/board/cards/task-a/start", Json(new { })));
        Assert.Throws<ArgumentException>(() => RetainedRequests.Validate("/api/v1/content/navigate", Json(new { utterance = "open arbitrary.exe", verb = "open", explicit_reference_id = "content-a" })));
        Assert.Throws<ArgumentException>(() => RetainedRequests.Validate("/api/v1/board/cards/task-a/remove", Json(new { expected_version = 0, authorized_by = "caller" })));
        Assert.Throws<InvalidDataException>(() => RetainedRequests.NavigationOutcome(Json(new { status = "opened", reason = "OK", reference_id = "content-other" }), "content-a"));
        Assert.Throws<InvalidDataException>(() => RetainedRequests.NavigationOutcome(Json(new { status = "opened", reason = "OK" }), "content-a"));
    }
    [Fact]
    public void ManualCompletedColumnDoesNotForgeTaskSuccess()
    {
        var card = Assert.Single(FullAppProjection.ParseBoard(Json(new { cards = new[] { new { task_id = "task-a", column = "DONE", status = "planned", intent = "Note", column_source = "manual", board_version = 4 } } })));
        Assert.Equal("DONE", card.Column); Assert.Equal("planned", card.Status); Assert.True(card.ManuallyPlaced); Assert.Equal(4, card.BoardVersion);
    }
    [Fact]
    public void PartiallyAdmittedNoteCannotCompleteAgainstAnotherCoreEpoch()
    {
        var draft = new BoardNoteDraft(); draft.Begin("Note", "hermes", "old-core"); draft.Acknowledge("task-a");
        Assert.Throws<InvalidOperationException>(() => draft.Begin("Note", "hermes", "new-core"));
        Assert.False(draft.Confirmed); Assert.Equal("task-a", draft.TaskId);
        draft.Begin("Note", "hermes", "old-core"); draft.Confirm(); Assert.True(draft.Confirmed);
    }
    [Fact]
    public void MalformedProjectionCannotBePresentedAsFreshEmptyBoard()
    {
        var content = Json(new { references = Array.Empty<object>() }); var extensions = Json(Array.Empty<object>());
        var capabilities = Json(new { active_extensions = Array.Empty<string>() });
        Assert.Throws<InvalidDataException>(() => RetainedRequests.ValidateProjectionShapes(Json(new { }), content, extensions, capabilities));
        Assert.Throws<InvalidDataException>(() => RetainedRequests.ValidateProjectionShapes(Json(new { cards = new[] { new { task_id = "task-a", column = "DONE" }, new { task_id = "task-a", column = "TODO" } } }), content, extensions, capabilities));
        Assert.Throws<InvalidDataException>(() => RetainedRequests.ValidateProjectionShapes(Json(new { cards = new[] { new { task_id = "task-a", column = "unknown" } } }), content, extensions, capabilities));
    }
}
