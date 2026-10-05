using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellAgentWorkflowTests
{
    private sealed class Api : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public string Root = Path.Combine(Path.GetTempPath(), "sora-secondary-fixture");
        public bool Offline;
        public TaskCompletionSource<JsonElement>? Read, Post;
        public Exception? PostError;
        public string ReplyTaskId = "task-a";
        public List<string> Gets = [];
        public List<(string Path, JsonElement Body)> Posts = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Gets.Add(path);
            if (Offline) throw new IOException("Offline fixture");
            if (path is "/api/v1/agents/catalogue" or "/api/v1/paths")
                return Read?.Task ?? Task.FromResult(JsonSerializer.SerializeToElement(new { providers = Array.Empty<object>(), leases = Array.Empty<object>(), events = Array.Empty<object>(), notice = "Evidence coverage" }));
            return Task.FromResult(JsonSerializer.SerializeToElement(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(),
                "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 10, settings_revision = 3, fields = Array.Empty<object>() },
                "/api/v1/tasks/task-a" => new { task_id = "task-a", status = "working" },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Posts.Add((path, JsonSerializer.SerializeToElement(body)));
            if (PostError is not null) throw PostError;
            return Post?.Task ?? Task.FromResult(JsonSerializer.SerializeToElement(new { task_id = ReplyTaskId, status = "queued", acknowledgement = "Admitted, not completed" }));
        }
    }

    [Fact]
    public async Task CachedCatalogueAndPathsUseSharedCoreWithoutInferenceOrMutation()
    {
        var api = new Api(); using var session = new ShellSession(api);
        await session.RefreshAsync(default); Assert.True(session.CanUseCore); Assert.False(session.CanSend);
        await session.AgentCatalogueAsync(); await session.ProjectPathsAsync(); await session.SettingsAsync();
        Assert.Empty(api.Posts); Assert.Contains("/api/v1/agents/catalogue", api.Gets); Assert.Contains("/api/v1/paths", api.Gets);
    }

    [Theory]
    [InlineData("offline")][InlineData("host-block")][InlineData("disposed")]
    public async Task SecondaryReadsAndMutationsFailClosed(string condition)
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        if (condition == "offline") { api.Offline = true; await session.RefreshAsync(default); }
        if (condition == "host-block") session.SetHostStatus("Owned shutdown", true);
        if (condition == "disposed") session.Dispose();
        var getCount = api.Gets.Count;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.AgentCatalogueAsync());
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ProjectPathsAsync(true));
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Owner wording", null, idempotencyKey: "key"));
        Assert.Equal(getCount, api.Gets.Count); Assert.Empty(api.Posts);
    }

    [Fact]
    public async Task ExactTaskModelEffortProjectAndModeAreNotMixedWithChatDraft()
    {
        var api = new Api(); using var session = new ShellSession(api) { Draft = "Independent conversation" };
        await session.RefreshAsync(default);
        var selection = new AgentSelection("hermes-acp", "exact model", "low", "C:\\fixture\\project", "read-only");
        var receipt = await session.DelegateAsync("Exact owner request", null, selection: selection, idempotencyKey: "same-key");
        var post = Assert.Single(api.Posts); Assert.Equal("/api/v1/tasks", post.Path);
        Assert.Equal("Exact owner request", post.Body.GetProperty("intent").GetString());
        Assert.Equal("hermes-acp", post.Body.GetProperty("explicit_provider").GetString());
        Assert.Equal("exact model", post.Body.GetProperty("explicit_model").GetString());
        Assert.Equal("low", post.Body.GetProperty("explicit_effort").GetString());
        Assert.Equal("C:\\fixture\\project", post.Body.GetProperty("working_directory").GetString());
        Assert.Equal("read-only", post.Body.GetProperty("workspace_mode").GetString());
        Assert.Equal("same-key", post.Body.GetProperty("idempotency_key").GetString());
        Assert.Equal("task-a", receipt.GetProperty("task_id").GetString());
        Assert.Equal("Independent conversation", session.Draft); Assert.Null(session.RequestId);
    }

    [Fact]
    public async Task UnconfirmedSubmissionCanOnlyBeExplicitlyRetriedWithIdenticalBodyAndEpoch()
    {
        var api = new Api { PostError = new IOException("Unconfirmed fixture response") };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<IOException>(() => session.DelegateAsync("Owner request", null, idempotencyKey: "key"));
        await session.RefreshAsync(default); Assert.Single(api.Posts); // no automatic replay
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Changed request", null, idempotencyKey: "key"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Owner request", null, selection: new("codex-app-server", "different"), idempotencyKey: "key"));
        Assert.Single(api.Posts); api.PostError = null;
        await session.DelegateAsync("Owner request", null, idempotencyKey: "key"); Assert.Equal(2, api.Posts.Count);
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Owner request", null, idempotencyKey: "key"));
        Assert.Equal(2, api.Posts.Count);
    }

    [Fact]
    public async Task AcknowledgementFromOldEpochIsNotCurrentSuccess()
    {
        var api = new Api { Post = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var pending = session.DelegateAsync("Owner request", null, idempotencyKey: "key");
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Post.SetResult(JsonSerializer.SerializeToElement(new { task_id = "task-a" }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        Assert.False(session.MutationBusy); Assert.Single(api.Posts);
    }

    [Fact]
    public async Task CatalogueAndPathReadCannotReturnOldEpochAsCurrentEvidence()
    {
        var api = new Api { Read = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var catalogue = session.AgentCatalogueAsync(); var paths = session.ProjectPathsAsync();
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Read.SetResult(JsonSerializer.SerializeToElement(new { providers = Array.Empty<object>() }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => catalogue);
        await Assert.ThrowsAsync<InvalidOperationException>(() => paths); Assert.Empty(api.Posts);
    }

    [Fact]
    public async Task SecondaryMutationAndTaskControlAreSerialized()
    {
        var api = new Api { Post = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        var pending = session.ProjectPathsAsync(true);
        Assert.True(session.SecondaryMutationBusy); Assert.True(session.MutationBusy);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Owner request", null, idempotencyKey: "key"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.AgentCatalogueAsync(true));
        Assert.Single(api.Posts); api.Post.SetResult(JsonSerializer.SerializeToElement(new { notice = "Retained" }));
        await pending; Assert.False(session.MutationBusy);
    }

    [Fact]
    public async Task PurposesSaveOnlyPatchesCanonicalRevisionCheckedRows()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        await session.SaveModelPurposesAsync(9, 3, "hermes", JsonSerializer.SerializeToElement(new[] { new { id = "model", purpose = "Local inspection" } }));
        var post = Assert.Single(api.Posts); Assert.Equal("/api/v1/settings", post.Path);
        Assert.Equal(9, post.Body.GetProperty("version").GetInt32()); Assert.Equal(3, post.Body.GetProperty("expected_revision").GetInt32());
        Assert.Single(post.Body.GetProperty("changes").EnumerateObject());
        Assert.True(post.Body.GetProperty("changes").TryGetProperty("agents.hermes.model_choices", out _));
        await Assert.ThrowsAsync<ArgumentException>(() => session.SaveModelPurposesAsync(9, 3, "unsupported", JsonSerializer.SerializeToElement(Array.Empty<object>())));
        Assert.Single(api.Posts); Assert.False(session.MutationBusy);
    }

    [Fact]
    public async Task ExplicitMetadataProbeAndReconciliationUseOnlyExistingRoutes()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        await session.AgentCatalogueAsync(true); await session.ProjectPathsAsync(true);
        Assert.Equal(new[] { "/api/v1/agents/catalogue/refresh", "/api/v1/paths/reconcile" }, api.Posts.Select(post => post.Path));
    }

    [Fact]
    public async Task KnownPreAdmissionInvalidInputCanBeCorrectedButOtherErrorsStayPinned()
    {
        var api = new Api { PostError = new SoraRequestException("Invalid model", "INVALID_INPUT") };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<SoraRequestException>(() => session.DelegateAsync("Bad request", null, idempotencyKey: "key"));
        api.PostError = null; await session.DelegateAsync("Corrected request", null, idempotencyKey: "key");
        Assert.Equal(2, api.Posts.Count);
    }

    [Fact]
    public async Task InvalidAcknowledgementCannotBecomeTaskSuccessOrAutomaticReplay()
    {
        var api = new Api { ReplyTaskId = "../settings" }; using var session = new ShellSession(api);
        await session.RefreshAsync(default);
        await Assert.ThrowsAsync<ArgumentException>(() => session.DelegateAsync("Owner request", null, idempotencyKey: "key"));
        await session.RefreshAsync(default); Assert.Single(api.Posts); Assert.False(session.MutationBusy);
    }

    [Fact]
    public async Task MismatchedProfileAndHostBlockDuringSubmissionFailClosed()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root);
        await session.RefreshAsync(default);
        api.Root += "-other-profile"; await session.RefreshAsync(default); Assert.False(session.CanUseCore);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.DelegateAsync("Owner request", null, idempotencyKey: "key"));
        Assert.Empty(api.Posts); api.Root = api.Root[..^14]; await session.RefreshAsync(default);
        Assert.True(session.CanUseCore);
        api.Post = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending = session.DelegateAsync("Owner request", null, idempotencyKey: "key");
        session.SetHostStatus("Owned shutdown", true);
        api.Post.SetResult(JsonSerializer.SerializeToElement(new { task_id = "task-a" }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        Assert.Single(api.Posts); Assert.False(session.MutationBusy);
    }

    [Fact]
    public void SubmissionDraftPinsSelectionAndCannotDuplicateAnAcknowledgedTask()
    {
        var draft = new TaskSubmissionDraft(); var selection = new AgentSelection("codex-app-server", "model", "low", "project", "direct");
        Assert.False(draft.Attempted); var key = draft.Begin("Owner request", null, selection);
        Assert.True(draft.Attempted); Assert.Equal(key, draft.Begin("Owner request", null, selection));
        Assert.Throws<InvalidOperationException>(() => draft.Begin("Owner request", null, selection with { WorkingDirectory = "other" }));
        Assert.Throws<InvalidOperationException>(() => draft.Begin("Other request", null, selection));
        draft.Acknowledge(); Assert.True(draft.Confirmed);
        Assert.Throws<InvalidOperationException>(() => draft.Begin("Owner request", null, selection));
        Assert.NotEqual(key, new TaskSubmissionDraft().Key);
    }

    [Theory]
    [InlineData("agents")][InlineData("paths")]
    public void SecondaryPanelsAreBoundedProfileCommandsAndRecognizedUiOnlyPlacements(string panel)
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-secondary-command-fixture");
        Assert.Equal(panel, ShellOptions.Parse(["--core-url", "http://127.0.0.1:18794", "--token-file", Path.Combine(root, "private", "token"), "--state-root", root, "--show", panel]).Panel);
        Assert.True(new HostCommand(1, "profile", panel).Valid("profile")); Assert.False(new HostCommand(1, "other", panel).Valid("profile"));
        new ShellPreferences { Panels = new() { [panel] = new("fixture", 0, 0, 800, 700, 96) } }.Validate();
        Assert.Throws<ArgumentException>(() => ShellOptions.Parse(["--core-url", "http://127.0.0.1:18794", "--token-file", "token", "--show", panel]));
    }
}
