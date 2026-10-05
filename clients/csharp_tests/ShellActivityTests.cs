using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellActivityTests
{
    private sealed class Api : IWidgetApi
    {
        public bool Offline;
        public string State = "working", ReturnedId = "task-a", ReplyId = "task-a";
        public string Epoch = Guid.NewGuid().ToString();
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-activity-fixture");
        public TaskCompletionSource<JsonElement>? TaskRead;
        public TaskCompletionSource<JsonElement>? PostReply;
        public List<(string Path, JsonElement Body)> Posts = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            if (Offline) throw new IOException("Offline fixture");
            if (path == "/api/v1/tasks/task-a") return TaskRead?.Task ?? Task.FromResult(JsonSerializer.SerializeToElement(new { task_id = ReturnedId, status = State }));
            return Task.FromResult(JsonSerializer.SerializeToElement(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = new object[] { new { sequence = 1 } }, next_sequence = 1, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(),
                "/api/v1/tasks" => new { tasks = new[] { new { task_id = "task-a", status = State, effective_backend = "fixture" } } },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 10, fields = Array.Empty<object>() },
                "/api/v1/tasks/task-a/evidence" => new { task = new { task_id = ReturnedId }, result = (object?)null, owner_request = "Owner request", evidence_note = "Provider report" },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Posts.Add((path, JsonSerializer.SerializeToElement(body)));
            return PostReply?.Task ?? Task.FromResult(JsonSerializer.SerializeToElement(new { task_id = ReplyId, cancelled = true, steered = true }));
        }
    }

    [Fact]
    public async Task TaskControlDoesNotRequireDialogueModelAndDoesNotAlterChat()
    {
        var api = new Api(); using var session = new ShellSession(api) { Draft = "Chat draft" };
        await session.RefreshAsync(default); Assert.False(session.CanSend); Assert.True(session.CanUseCore);
        await session.ControlTaskAsync("task-a", "steer", "Exact instruction", default);
        Assert.Equal("Exact instruction", api.Posts.Single().Body.GetProperty("instruction").GetString());
        Assert.Equal("/api/v1/tasks/task-a/steer", api.Posts[0].Path);
        Assert.Equal("Chat draft", session.Draft); Assert.Null(session.RequestId); Assert.False(session.TaskControlBusy);
    }

    [Theory]
    [InlineData("completed")][InlineData("failed")][InlineData("cancelled")][InlineData("planned")]
    [InlineData("cancel_requested")][InlineData("interrupted")][InlineData("future-unknown")]
    public async Task FreshTerminalOrUnknownStateRefusesMutation(string status)
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        api.State = status;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        Assert.Empty(api.Posts); Assert.False(session.TaskControlBusy);
    }

    [Fact]
    public async Task ExactIdMismatchAndOfflineOrHostBlockRefuseEffects()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        api.ReturnedId = "task-b";
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        await Assert.ThrowsAsync<InvalidDataException>(() => session.TaskEvidenceAsync("task-a", default));
        session.SetHostStatus("Owned shutdown", true);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        session.SetHostStatus("Ready", false); api.Offline = true; await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.TaskEvidenceAsync("task-a", default));
        Assert.Empty(api.Posts);
    }

    [Fact]
    public async Task ConcurrentControlRejectedAndEpochChangeCannotRetargetTask()
    {
        var api = new Api { TaskRead = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var first = session.ControlTaskAsync("task-a", "cancel", "", default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "steer", "Second", default));
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.TaskRead.SetResult(JsonSerializer.SerializeToElement(new { task_id = "task-a", status = "working" }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => first);
        Assert.Empty(api.Posts); Assert.False(session.TaskControlBusy);
    }

    [Fact]
    public async Task MismatchedAcknowledgementIsNotSuccessAndIsNotReplayed()
    {
        var api = new Api { ReplyId = "task-b" }; using var session = new ShellSession(api);
        await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidDataException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        await session.RefreshAsync(default); Assert.Single(api.Posts);
    }

    [Fact]
    public async Task OldEpochAcknowledgementAfterRestartIsNotCurrentSuccessOrReplay()
    {
        var api = new Api { PostReply = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var control = session.ControlTaskAsync("task-a", "cancel", "", default);
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.PostReply.SetResult(JsonSerializer.SerializeToElement(new { task_id = "task-a", cancelled = true }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => control);
        await session.RefreshAsync(default); Assert.Single(api.Posts); Assert.False(session.TaskControlBusy);
    }

    [Fact]
    public async Task InvalidTargetsAndInstructionsNeverReadOrMutateAnotherResource()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<ArgumentException>(() => session.ControlTaskAsync("../settings", "cancel", "", default));
        await Assert.ThrowsAsync<ArgumentException>(() => session.ControlTaskAsync("task-a", "evidence", "", default));
        await Assert.ThrowsAsync<ArgumentException>(() => session.ControlTaskAsync("task-a", "steer", " ", default));
        await Assert.ThrowsAsync<ArgumentException>(() => session.ControlTaskAsync("task-a", "steer", new string('x', 8001), default));
        Assert.Empty(api.Posts);
    }

    [Fact]
    public void EvidenceKeepsOwnerBriefAndProviderCoverageDistinctAndTextInert()
    {
        var data = JsonSerializer.SerializeToElement(new {
            task = new { task_id = "task-a", status = "completed", companion_brief = "SORA suggestion", requested_model = "Exact model", working_directory = "Exact project", workspace_base_ref = "main" },
            owner_request = "Original owner wording", result = new { summary = "<script>inert</script>", files_changed = new[] { "file.txt" }, artifacts = new[] { "artifact-report" } },
            evidence_note = "Provider report, not independent verification"
        });
        var text = TaskPresentation.Evidence("task-a", data);
        Assert.Contains("Original owner wording", text); Assert.Contains("not the owner's instruction", text);
        Assert.Contains("<script>inert</script>", text); Assert.Contains("provider report", text);
        Assert.Contains("Exact model", text); Assert.Contains("Exact project", text); Assert.Contains("artifact-report", text);
        Assert.Throws<InvalidDataException>(() => TaskPresentation.Evidence("task-b", data));
    }

    [Fact]
    public void ActivityHostCommandAndUiPlacementAreBoundedAndOldStoresRemainValid()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-activity-host-fixture");
        var options = ShellOptions.Parse(["--core-url", "http://127.0.0.1:18792", "--token-file", Path.Combine(root, "token"), "--state-root", root, "--show", "activity"]);
        Assert.Equal("activity", options.Panel); Assert.True(new HostCommand(1, "p", "activity").Valid("p"));
        Assert.False(new HostCommand(1, "other", "activity").Valid("p"));
        new ShellPreferences().Validate();
        new ShellPreferences { Panels = new() { ["activity"] = new("fixture", 0, 0, 920, 700, 96) } }.Validate();
    }
}
