using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellHostTests
{
    [Fact]
    public void ExplicitProfileOptionsAndIdentityAreBounded()
    {
        var root = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "sora-host-options"));
        var options = ShellOptions.Parse(["--core-url", "http://127.0.0.1:18798", "--token-file",
            Path.Combine(root, "private", "token"), "--state-root", root, "--show", "settings"]);
        Assert.True(options.Hosted); Assert.Equal("settings", options.Panel);
        Assert.Equal(ShellProfile.Key(root, "user"), ShellProfile.Key(root + Path.DirectorySeparatorChar, "user"));
        Assert.NotEqual(ShellProfile.Key(root, "user"), ShellProfile.Key(root, "other-user"));
        var id = Guid.NewGuid().ToString();
        Assert.Equal(id, ShellProfile.ValidateIdentity(JsonSerializer.SerializeToElement(new {
            version = 1, instance_id = id, state_root = root }), root));
        Assert.Throws<InvalidOperationException>(() => ShellProfile.ValidateIdentity(JsonSerializer.SerializeToElement(new {
            version = 1, instance_id = id, state_root = root + "-other" }), root));
        Assert.Throws<ArgumentException>(() => ShellOptions.Parse(["--core-url", "http://example.com", "--token-file", "token"]));
        Assert.Throws<ArgumentException>(() => ShellOptions.Parse(["--core-url", "http://127.0.0.1/", "--token-file",
            Path.Combine(root, "..", "outside-token"), "--state-root", root]));
        Assert.False(new HostCommand(1, "profile", "execute").Valid("profile"));
        Assert.True(new HostCommand(1, "profile", "menu").Valid("profile"));
        Assert.False(new HostCommand(1, "other", "chat").Valid("profile"));
    }

    [Fact]
    public async Task CurrentUserIpcDispatchesOnlyBoundedProfileCommands()
        => await Task.Run(RunIpcSmoke);

    private static void RunIpcSmoke()
    {
        // Mutex ownership is thread-affine. Construction/disposal stay on this synchronous test thread.
        var key = Convert.ToHexString(System.Security.Cryptography.RandomNumberGenerator.GetBytes(32));
        using var instance = new ShellInstance(key);
        Assert.True(instance.Primary);
        using var cancel = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var panels = new List<string>();
        var server = Task.Run(() => instance.ServeAsync(command => {
            lock (panels) panels.Add(command.Panel);
            return Task.FromResult(true);
        }, cancel.Token));
        var accepted = instance.SummonAsync("settings", cancel.Token).GetAwaiter().GetResult();
        Assert.True(accepted); lock (panels) Assert.Equal(["settings"], panels);
        cancel.Cancel(); server.GetAwaiter().GetResult();
        // A secondary process/thread must not acquire the profile mutex. Test on another thread:
        // Task.Run(...).GetResult() may inline on this mutex-owning thread and recursively acquire it.
        // A dedicated thread makes this genuinely a secondary owner, independently of pool scheduling.
        bool? secondary = null; Exception? secondaryError = null;
        var thread = new Thread(() => {
            try { using var other = new ShellInstance(key); secondary = other.Primary; }
            catch (Exception error) { secondaryError = error; }
        });
        thread.Start(); Assert.True(thread.Join(TimeSpan.FromSeconds(5)));
        Assert.Null(secondaryError); Assert.Equal(false, secondary);
    }

    private sealed class WrongProfileApi : IWidgetApi
    {
        public readonly List<string> Gets = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Gets.Add(path);
            return Task.FromResult(JsonSerializer.SerializeToElement(new { version = 1,
                instance_id = Guid.NewGuid().ToString(), state_root = Path.Combine(Path.GetTempPath(), "wrong-core") }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) =>
            throw new InvalidOperationException("No effects should be called");
    }
    [Fact]
    public async Task WrongProfileFailsBeforeConversationOrSettingsRead()
    {
        var api = new WrongProfileApi();
        using var session = new ShellSession(api, Path.Combine(Path.GetTempPath(), "expected-core"));
        session.Draft = "Retain me"; await session.RefreshAsync(default);
        Assert.False(session.CanSend); Assert.Null(session.Settings); Assert.Equal("Retain me", session.Draft);
        Assert.Contains("mismatched", session.SettingsError); Assert.Equal(["/api/v1/runtime/identity"], api.Gets);
    }

    private sealed class RestartingApi(string root) : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public bool ProjectionsDown;
        public readonly List<string> Gets = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Gets.Add(path);
            if (path == "/api/v1/runtime/identity") return Task.FromResult(JsonSerializer.SerializeToElement(new {
                version = 1, instance_id = Epoch, state_root = root }));
            if (ProjectionsDown) throw new IOException("Projection connection dropped after identity check");
            return Task.FromResult(JsonSerializer.SerializeToElement(path.Split('?')[0] switch {
                "/api/v1/events" => (object)new { events = Array.Empty<object>(), next_sequence = 90,
                    more_available = false, resync_required = false },
                "/api/v1/messages" => new[] { new { message_id = "known-message", role = "assistant",
                    content = "Known canonical fixture", created_at = "2026-10-03T18:00:00Z" } },
                "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new {
                    dialogue_ready = true, model_state = "ready", state = "idle", dialogue_model = "Fixture" },
                    background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 9, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token) =>
            throw new InvalidOperationException("Reconnect must not replay effects");
    }
    [Fact]
    public async Task EpochChangeResetsCursorButRetainsStaleTranscriptUntilSuccessfulResync()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-epoch-fixture");
        var api = new RestartingApi(root); string? bound = null;
        using var session = new ShellSession(api, root, value => bound = value) { Draft = "Retained draft" };
        await session.RefreshAsync(default); Assert.True(session.CanSend);
        Assert.Single(session.Snapshot.Messages); Assert.Equal(api.Epoch, bound);
        api.Epoch = Guid.NewGuid().ToString(); api.ProjectionsDown = true; api.Gets.Clear();
        await session.RefreshAsync(default);
        Assert.False(session.CanSend); Assert.Equal(0, session.Snapshot.Sequence);
        Assert.Single(session.Snapshot.Messages); Assert.Contains("stale", session.SettingsError);
        Assert.Contains("/api/v1/events?since_sequence=0&limit=100", api.Gets);
        Assert.Equal("Retained draft", session.Draft); Assert.Equal(api.Epoch, bound);
        api.ProjectionsDown = false; await session.RefreshAsync(default);
        Assert.True(session.CanSend); Assert.Single(session.Snapshot.Messages);
    }
}
