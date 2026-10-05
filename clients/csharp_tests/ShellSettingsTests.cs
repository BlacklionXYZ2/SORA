using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellSettingsTests
{
    private sealed class Api : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public string Root = Path.Combine(Path.GetTempPath(), "sora-settings-fixture");
        public int Revision = 3, Version = 9;
        public bool Offline, DiskChanged, CanReload = true;
        public TaskCompletionSource<JsonElement>? PendingPost, PendingSettingsRead;
        public Exception? PostError;
        public List<(string Path, JsonElement Body)> Posts = [];
        public JsonElement Projection() => JsonSerializer.SerializeToElement(new {
            settings_version = Version, settings_revision = Revision, disk_changed = DiskChanged,
            can_reload = CanReload, fields = new[] { new { key = "llama.context_size", value = 8192, editable = true } }
        });
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            if (Offline) throw new IOException("offline fixture");
            if (path == "/api/v1/projections/settings") return PendingSettingsRead?.Task ?? Task.FromResult(Projection());
            return Task.FromResult(JsonSerializer.SerializeToElement(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(),
                "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Posts.Add((path, JsonSerializer.SerializeToElement(body))); if (PostError is not null) throw PostError;
            return PendingPost?.Task ?? Task.FromResult(Projection());
        }
    }
    private static object Edit(int revision = 3, int version = 9, string key = "llama.context_size") =>
        new { version, expected_revision = revision, changes = new Dictionary<string, object> { [key] = 4096 } };

    [Fact]
    public async Task SaveUsesExactBodySharedTransportAndCanonicalCache()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        Assert.True(session.SettingsCurrent); session.Draft = "unrelated chat";
        await session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        var post = Assert.Single(api.Posts); Assert.Equal(4096, post.Body.GetProperty("changes").GetProperty("llama.context_size").GetInt32());
        Assert.Equal(3, session.Settings!.Value.GetProperty("settings_revision").GetInt32());
        Assert.Equal("unrelated chat", session.Draft); Assert.True(session.SettingsCurrent); Assert.False(session.MutationBusy);
    }
    [Theory]
    [InlineData("revision")] [InlineData("disk")] [InlineData("version")] [InlineData("field")]
    [InlineData("route")] [InlineData("extra")] [InlineData("reload-disabled")]
    public async Task PreflightRejectsStaleUnknownOrUnsupportedRequestsWithoutPost(string reason)
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        string path = "/api/v1/settings"; object body = Edit();
        if (reason == "revision") api.Revision++;
        if (reason == "disk") api.DiskChanged = true;
        if (reason == "version") api.Version = 8;
        if (reason == "field") body = Edit(key: "authority.override");
        if (reason == "route") path = "/api/v1/desktop/act";
        if (reason == "extra") body = new { version = 9, expected_revision = 3, changes = new { }, authorized_by = "caller" };
        if (reason == "reload-disabled") { path = "/api/v1/model/reload"; api.CanReload = false; body = new { expected_revision = 3 }; }
        await Assert.ThrowsAnyAsync<Exception>(() => session.SettingsApi.PostAsync(path, body, default));
        Assert.Empty(api.Posts); Assert.False(session.MutationBusy);
    }
    [Theory]
    [InlineData("offline")] [InlineData("host-block")] [InlineData("disposed")]
    public async Task UnavailableHostCannotSubmitSettings(string reason)
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        if (reason == "offline") { api.Offline = true; await session.RefreshAsync(default); }
        if (reason == "host-block") session.SetHostStatus("shutdown", true);
        if (reason == "disposed") session.Dispose();
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default));
        Assert.Empty(api.Posts); Assert.False(session.SettingsCurrent);
    }
    [Fact]
    public async Task PendingSaveSerializesOtherEffectsAndOldEpochResponseIsUnknown()
    {
        var api = new Api { PendingPost = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var save = session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        Assert.True(session.MutationBusy);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.SettingsApi.PostAsync("/api/v1/settings/refresh", new { }, default));
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.PendingPost.SetResult(api.Projection()); await Assert.ThrowsAsync<InvalidOperationException>(() => save);
        Assert.Single(api.Posts); Assert.False(session.SettingsCurrent); Assert.Contains("unconfirmed", session.SettingsError);
    }
    [Theory]
    [InlineData(2)] [InlineData(5)]
    public async Task WrongRevisionAcknowledgementIsNotSavedSuccess(int replyRevision)
    {
        var api = new Api { PendingPost = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        var save = session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        api.Revision = replyRevision; api.PendingPost.SetResult(api.Projection());
        await Assert.ThrowsAsync<InvalidDataException>(() => save); Assert.False(session.SettingsCurrent);
        Assert.False(session.MutationBusy); Assert.Single(api.Posts);
    }
    [Fact]
    public async Task UnknownSaveIsNeverReplayedByRefresh()
    {
        var api = new Api { PostError = new IOException("unknown outcome") };
        using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<IOException>(() => session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default));
        Assert.False(session.SettingsCurrent); await session.RefreshAsync(default); Assert.Single(api.Posts);
        Assert.True(session.SettingsCurrent);
    }
    [Fact]
    public async Task ReplacedCoreBeforeNextPollCannotReceiveSaveEvenWithSameSettingsRevision()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        api.Epoch = Guid.NewGuid().ToString();
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default));
        Assert.Empty(api.Posts); Assert.False(session.MutationBusy);
    }
    [Fact]
    public async Task ReplacedCoreAfterSubmissionDoesNotAcknowledgeOldSave()
    {
        var api = new Api { PendingPost = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var save = session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        api.Epoch = Guid.NewGuid().ToString(); api.PendingPost.SetResult(api.Projection());
        await Assert.ThrowsAsync<InvalidOperationException>(() => save);
        Assert.Single(api.Posts); Assert.False(session.SettingsCurrent);
    }
    [Fact]
    public async Task LateFailedPollDoesNotInvalidateConfirmedSave()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        api.PendingSettingsRead = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending = api.PendingSettingsRead; var poll = session.RefreshAsync(default);
        api.PendingSettingsRead = null;
        await session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        pending.SetException(new IOException("old read failed")); await poll;
        Assert.True(session.SettingsCurrent); Assert.Equal("", session.SettingsError);
    }
    [Fact]
    public async Task RefreshAndReloadAreSeparateExplicitEffects()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        await session.SettingsApi.PostAsync("/api/v1/settings/refresh", new { }, default);
        await session.SettingsApi.PostAsync("/api/v1/model/reload", new { expected_revision = 3 }, default);
        Assert.Equal(new[] { "/api/v1/settings/refresh", "/api/v1/model/reload" }, api.Posts.Select(p => p.Path));
        await Assert.ThrowsAsync<NotSupportedException>(() => session.SettingsApi.GetAsync("/api/v1/state", default));
    }
    [Fact]
    public async Task LatePollCannotReplaceTheAcknowledgedSavedRevision()
    {
        var api = new Api(); using var session = new ShellSession(api); await session.RefreshAsync(default);
        api.PendingSettingsRead = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var pendingRead = api.PendingSettingsRead;
        var poll = session.RefreshAsync(default);
        var old = api.Projection(); api.PendingSettingsRead = null;
        api.PendingPost = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var save = session.SettingsApi.PostAsync("/api/v1/settings", Edit(), default);
        api.Revision = 4; api.PendingPost.SetResult(api.Projection()); await save;
        // Resolve the already captured read, not a new request.
        // The shared read-generation fence must reject its older revision.
        pendingRead.SetResult(old); await poll;
        Assert.Equal(4, session.Settings!.Value.GetProperty("settings_revision").GetInt32());
    }
}
