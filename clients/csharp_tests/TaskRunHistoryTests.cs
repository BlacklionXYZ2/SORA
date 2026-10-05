using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class TaskRunHistoryTests
{
    private static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
    private static object Event(int number, string type = "run.running") => new {
        event_id = "event-" + number, sequence = number, event_type = type, source = "core",
        task_id = "task-a", run_id = "run-a", correlation_id = "task-a", timestamp = "2026-10-04T02:00:00+01:00",
        payload = new { secret_capture = "PRIVATE-CAPTURE", private_patch = "PRIVATE-PATCH" }
    };
    private static object Run(string task = "task-a", string id = "run-a") => new {
        task_id = task, run_id = id, attempt = 1, provider = "fixture", status = "completed",
        outcome = "completed", started_at = "2026-10-04T02:00:00+01:00", finished_at = "2026-10-04T02:01:00+01:00"
    };
    private sealed class Api : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-history-read-fixture");
        public object[] Events = [Event(1)];
        public bool Resync, FailProjection;
        public TaskCompletionSource<JsonElement>? Detail;
        public JsonElement Page = Json(new { task_id = "task-a", runs = new[] { new { run = Run(), result_id = "result-a" } }, next_cursor = "YWJj", total = 2 });
        public List<string> Reads = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Reads.Add(path);
            if (path == "/api/v1/tasks/task-a/runs/run-a") return Detail?.Task ?? Task.FromResult(Json(new { task_id = "task-a", run = Run(), result = (object?)null, evidence_note = "Provider report", artifacts = Array.Empty<object>() }));
            if (path.StartsWith("/api/v1/tasks/task-a/runs?")) return Task.FromResult(Page);
            if (FailProjection && path.StartsWith("/api/v1/messages")) throw new IOException("Partial refresh fixture");
            return Task.FromResult(Json(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Events, next_sequence = 70, more_available = false, resync_required = Resync },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 10, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) => throw new InvalidOperationException("Read-only test must not mutate");
    }

    [Fact]
    public void PublicActivityCopiesOnlyKnownPublicMetadataNotPrivatePayloads()
    {
        var activity = WidgetActivity.Parse(Json(Event(1, "run.completed")))!;
        Assert.Equal("core", activity.Source); Assert.Equal("task-a", activity.CorrelationId);
        Assert.Equal("Completed · provider report", activity.Label);
        Assert.DoesNotContain("PRIVATE", JsonSerializer.Serialize(activity));
        Assert.Null(WidgetActivity.Parse(Json(Event(2, "capture.created"))));
        Assert.Null(WidgetActivity.Parse(Json(Event(3, "provider.private_trace"))));
    }
    [Theory]
    [InlineData("task_id", "../settings")][InlineData("event_id", "bad/id")]
    [InlineData("run_id", "bad/id")][InlineData("timestamp", "not a date")]
    [InlineData("source", "bad\nsource")][InlineData("correlation_id", "bad\ncorrelation")]
    public void MalformedActivityMetadataIsSkipped(string field, string value)
    {
        var fields = Json(Event(1)).Deserialize<Dictionary<string, object>>()!; fields[field] = value;
        Assert.Null(WidgetActivity.Parse(Json(fields)));
    }
    [Fact]
    public async Task ActivityWindowIsBoundedDeduplicatedAndResetWithoutAnotherPoller()
    {
        var api = new Api { Events = Enumerable.Range(1, 70).Select(i => Event(i)).ToArray() };
        var sync = new WidgetSync(api); var first = await sync.RefreshAsync();
        Assert.Equal(64, first.PublicActivity.Count); Assert.Equal(7, first.PublicActivity[0].Sequence);
        var replay = await sync.RefreshAsync(); Assert.Equal(64, replay.PublicActivity.Count);
        Assert.Equal(2, api.Reads.Count(path => path.StartsWith("/api/v1/events?")));
        api.Resync = true; api.Events = [];
        Assert.Empty((await sync.RefreshAsync()).PublicActivity);
        api.Resync = false; api.Events = [Event(71)]; await sync.RefreshAsync();
        sync.ResetForNewCore(); Assert.Empty(sync.Current.PublicActivity);
    }
    [Fact]
    public async Task FailedProjectionDoesNotCommitPartialEventEvidence()
    {
        var api = new Api(); var sync = new WidgetSync(api); await sync.RefreshAsync();
        api.Events = [Event(2)]; api.FailProjection = true;
        var stale = await sync.RefreshAsync(); Assert.False(stale.Connected);
        Assert.Single(stale.PublicActivity); Assert.Equal("event-1", stale.PublicActivity[0].EventId);
    }
    [Fact]
    public async Task HistoryReadersWorkModelDownAndOutsideLatestTaskListWithoutMutation()
    {
        var api = new Api(); using var session = new ShellSession(api) { Draft = "Keep Chat draft" };
        await session.RefreshAsync(default); Assert.False(session.CanSend); Assert.Empty(session.Snapshot.Tasks);
        var page = await session.TaskRunsAsync("task-a", "YWJj", default);
        var detail = await session.TaskRunEvidenceAsync("task-a", "run-a", default);
        Assert.Equal("task-a", page.GetProperty("task_id").GetString()); Assert.Equal("run-a", detail.GetProperty("run").GetProperty("run_id").GetString());
        Assert.Contains("/api/v1/tasks/task-a/runs?limit=50&cursor=YWJj", api.Reads);
        Assert.Equal("Keep Chat draft", session.Draft); Assert.False(session.MutationBusy);
    }
    [Fact]
    public async Task HistoryReadFromPreviousCoreEpochCannotBePresentedAsCurrent()
    {
        var api = new Api { Detail = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var read = session.TaskRunEvidenceAsync("task-a", "run-a", default);
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Detail.SetResult(Json(new { task_id = "task-a", run = Run() }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => read);
    }
    [Fact]
    public async Task WrongTaskPageIsRejectedAndHostBlockDoesNotMakeRequest()
    {
        var api = new Api { Page = Json(new { task_id = "task-other", runs = Array.Empty<object>() }) };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidDataException>(() => session.TaskRunsAsync("task-a", null, default));
        session.SetHostStatus("Quitting", true); var count = api.Reads.Count;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.TaskRunsAsync("task-a", null, default));
        Assert.Equal(count, api.Reads.Count);
    }
    [Theory]
    [InlineData("../settings", "run-a", null)][InlineData("task-a", "../settings", null)]
    [InlineData("task-a", null, "cursor&evil=1")][InlineData("task-a", "run-a", "YWJj")]
    public void InvalidPathsCannotReadAnotherResource(string task, string? run, string? cursor) =>
        Assert.Throws<ArgumentException>(() => TaskPresentation.RunsPath(task, run, cursor));
    [Fact]
    public void DuplicateAndCrossTaskAttemptsAreRejected()
    {
        var duplicate = Json(new { task_id = "task-a", runs = new[] { new { run = Run() }, new { run = Run() } } });
        Assert.Throws<InvalidDataException>(() => TaskPresentation.ValidateRuns("task-a", duplicate));
        var wrong = Json(new { task_id = "task-a", runs = new[] { new { run = Run("task-other") } } });
        Assert.Throws<InvalidDataException>(() => TaskPresentation.ValidateRuns("task-a", wrong));
    }
    [Fact]
    public void ExactAttemptEvidenceIsInertAndNeverSubstitutesLatestResult()
    {
        var empty = Json(new { task_id = "task-a", run = Run(), result = (object?)null, evidence_note = "Coverage fixture" });
        Assert.Contains("latest result is not substituted", TaskPresentation.RunEvidence("task-a", "run-a", empty));
        var data = Json(new { task_id = "task-a", run = Run(), result = new {
            result_id = "result-a", task_id = "task-a", run_id = "run-a", summary = "<script>inert</script>",
            commands_run = new[] { "inert command" }, files_changed = new[] { "relative.txt" }, private_patch = "PRIVATE"
        }, text_truncated = true, omitted_items = new { actions_taken = 4 }, evidence_note = "Provider report" });
        var text = TaskPresentation.RunEvidence("task-a", "run-a", data);
        Assert.Contains("<script>inert</script>", text); Assert.Contains("relative.txt", text); Assert.Contains("result-a", text);
        Assert.Contains("Omitted actions_taken: 4", text); Assert.DoesNotContain("PRIVATE", text);
        Assert.Throws<InvalidDataException>(() => TaskPresentation.RunEvidence("task-a", "run-other", data));
    }
}
