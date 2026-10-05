using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellVoiceTests
{
    private static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
    private static JsonElement Voice(string state = "ready", bool? microphone = false, bool enabled = true, bool running = true) =>
        Json(new { state, message = "Worker fixture", microphone_open = microphone, enabled, running,
            devices = new[] { new { key = "WASAPI|Fixture mic", input_channels = 1, output_channels = 0 } } });
    private sealed class Api : IWidgetApi
    {
        public string Epoch = Guid.NewGuid().ToString();
        public readonly string Root = Path.Combine(Path.GetTempPath(), "sora-voice-session-fixture");
        public JsonElement Status = Voice();
        public bool FailVoice, FailAll;
        public TaskCompletionSource<JsonElement>? VoiceRead, Reply;
        public readonly List<string> Reads = [];
        public readonly List<(string Path, JsonElement Body)> Posts = [];
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            Reads.Add(path); if (FailAll) throw new IOException("Offline fixture");
            if (path == "/api/v1/voice/local") {
                if (FailVoice) throw new IOException("Voice fixture unavailable");
                return VoiceRead?.Task ?? Task.FromResult(Status);
            }
            return Task.FromResult(Json(path.Split('?')[0] switch {
                "/api/v1/runtime/identity" => (object)new { version = 1, instance_id = Epoch, state_root = Root },
                "/api/v1/events" => new { events = Array.Empty<object>(), next_sequence = 0, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(), "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new { dialogue_ready = false, model_state = "down", state = "idle" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 9, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        { Posts.Add((path, Json(body))); return Reply?.Task ?? Task.FromResult(Status); }
    }
    [Fact]
    public async Task SharedVoicePollIsOptInReadOnlyAndWorksModelDownWithPanelsAbsent()
    {
        var api = new Api(); using var session = new ShellSession(api) { Draft = "Keep Chat draft" };
        await session.RefreshAsync(default); Assert.DoesNotContain("/api/v1/voice/local", api.Reads);
        session.EnableVoice(); await session.RefreshAsync(default);
        Assert.True(session.VoiceCurrent); Assert.False(session.CanSend); Assert.Empty(api.Posts);
        Assert.Single(api.Reads, path => path == "/api/v1/voice/local");
        Assert.Equal("Mic closed · worker report", session.MicrophoneLabel);
        api.Status = Voice("recording", true); await session.RefreshAsync(default);
        Assert.Equal("Mic ON · recording", session.MicrophoneLabel);
        Assert.Equal("Keep Chat draft", session.Draft);
    }
    [Fact]
    public async Task VoiceFailureRetainsStaleUnknownCaptureWithoutDisconnectingGoodCore()
    {
        var api = new Api { Status = Voice("recording", true) }; using var session = new ShellSession(api);
        session.EnableVoice(); await session.RefreshAsync(default);
        api.FailVoice = true; await session.RefreshAsync(default);
        Assert.True(session.CanUseCore); Assert.False(session.VoiceCurrent);
        Assert.Contains("UNKNOWN", session.MicrophoneLabel); Assert.Contains("last reported recording", session.MicrophoneLabel);
        api.FailVoice = false; api.FailAll = true; await session.RefreshAsync(default);
        Assert.False(session.VoiceCurrent); Assert.Contains("UNKNOWN", session.MicrophoneLabel);
    }
    [Fact]
    public void OldCoreWithoutMicrophoneMetadataNeverClaimsClosed()
    {
        var data = Json(new { state = "ready", message = "Old Core", running = true, enabled = true, devices = Array.Empty<object>() });
        var projection = VoiceProjection.Parse(data);
        Assert.Null(projection.MicrophoneOpen); Assert.Contains("UNKNOWN", projection.MicrophoneLabel(true));
        Assert.Contains("UNKNOWN", (projection with { Enabled = false }).MicrophoneLabel(true));
    }
    [Theory]
    [InlineData("start", "stopped", false)][InlineData("begin", "ready", true)]
    [InlineData("end", "recording", true)][InlineData("stop", "thinking", true)]
    [InlineData("stop_output", "speaking", true)][InlineData("close", "stopped", false)]
    public async Task ExplicitVoiceActionsUseOnlyFixedRouteAndAction(string action, string state, bool running)
    {
        var api = new Api { Status = Voice(state, false, running: running) }; using var session = new ShellSession(api) { Draft = "Chat unchanged" };
        await session.RefreshAsync(default); await session.VoiceActionAsync(action, default);
        var post = Assert.Single(api.Posts); Assert.Equal("/api/v1/voice/local", post.Path);
        Assert.Single(post.Body.EnumerateObject()); Assert.Equal(action, post.Body.GetProperty("action").GetString());
        Assert.Equal("Chat unchanged", session.Draft); Assert.Null(session.RequestId); Assert.False(session.MutationBusy);
    }
    [Fact]
    public async Task StaticOffBlocksBeginButExplicitCloseStillAllowed()
    {
        var api = new Api { Status = Voice(enabled: false) }; using var session = new ShellSession(api); await session.RefreshAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.VoiceActionAsync("begin", default)); Assert.Empty(api.Posts);
        await session.VoiceActionAsync("close", default); Assert.Single(api.Posts);
    }
    [Fact]
    public async Task WrongOldEpochAndUnsupportedActionsCannotRetargetOrRead()
    {
        var api = new Api(); using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var count = api.Reads.Count;
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.VoiceActionAsync("end", default, "old-core"));
        await Assert.ThrowsAsync<ArgumentException>(() => session.VoiceActionAsync("arbitrary", default));
        Assert.Equal(count, api.Reads.Count); Assert.Empty(api.Posts);
    }
    [Fact]
    public async Task BeginPreflightCannotCrossCoreRestartOrDispatchToNewWorker()
    {
        var api = new Api { VoiceRead = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var action = session.VoiceActionAsync("begin", default, api.Epoch);
        api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.VoiceRead.SetResult(Voice());
        await Assert.ThrowsAsync<InvalidOperationException>(() => action); Assert.Empty(api.Posts);
    }
    [Fact]
    public async Task PendingVoiceBlocksOtherMutationAndQuitStateAndIsNotReplayed()
    {
        var api = new Api { Reply = new(TaskCreationOptions.RunContinuationsAsynchronously) }; using var session = new ShellSession(api);
        session.EnableVoice(); await session.RefreshAsync(default); var action = session.VoiceActionAsync("begin", default);
        Assert.True(session.VoiceBusy); Assert.True(session.MutationBusy);
        Assert.False(session.VoiceCurrent); Assert.Contains("UNKNOWN", session.MicrophoneLabel);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.ControlTaskAsync("task-a", "cancel", "", default));
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.VoiceActionAsync("start", default));
        api.Reply.SetException(new IOException("Unknown outcome fixture"));
        await Assert.ThrowsAsync<IOException>(() => action); await session.RefreshAsync(default);
        Assert.Single(api.Posts); Assert.False(session.MutationBusy); Assert.True(session.VoiceCurrent);
    }
    [Fact]
    public async Task OldEpochVoiceAcknowledgementIsNotCurrentSuccess()
    {
        var api = new Api { Reply = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api, api.Root); await session.RefreshAsync(default);
        var action = session.VoiceActionAsync("begin", default); api.Epoch = Guid.NewGuid().ToString(); await session.RefreshAsync(default);
        api.Reply.SetResult(Voice("recording", true));
        await Assert.ThrowsAsync<InvalidOperationException>(() => action); Assert.False(session.VoiceCurrent); Assert.Single(api.Posts);
    }
    [Fact]
    public async Task ReleaseBeforeBeginAcknowledgementSendsExactlyOneEndAfterBegin()
    {
        var calls = new List<string>(); var reply = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var hold = new PressToTalk(async action => { calls.Add(action); if (action == "begin") await reply.Task; });
        var begin = hold.BeginAsync(); await hold.ReleaseAsync(); await hold.ReleaseAsync();
        Assert.False(hold.Held); Assert.True(hold.Beginning); Assert.Equal(new[] { "begin" }, calls);
        reply.SetResult(); await begin; Assert.Equal(new[] { "begin", "end" }, calls); Assert.False(hold.Beginning);
    }
    [Fact]
    public async Task FocusLossBeforeBeginAcknowledgementDiscardsInsteadOfSendingSpeech()
    {
        var calls = new List<string>(); var reply = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var hold = new PressToTalk(async action => { calls.Add(action); if (action == "begin") await reply.Task; });
        var begin = hold.BeginAsync(); await hold.ReleaseAsync(discard: true); reply.SetResult(); await begin;
        Assert.Equal(new[] { "begin", "stop" }, calls);
    }
    [Fact]
    public async Task UnknownBeginWithExplicitReleaseTriesSafetyStopButNeverReplaysBegin()
    {
        var calls = new List<string>(); var reply = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var hold = new PressToTalk(async action => { calls.Add(action); if (action == "begin") await reply.Task; });
        var begin = hold.BeginAsync(); await hold.ReleaseAsync(); reply.SetException(new IOException("Uncertain begin"));
        await Assert.ThrowsAsync<IOException>(() => begin); Assert.Equal(new[] { "begin", "stop" }, calls); Assert.False(hold.Held);
    }
    [Fact]
    public async Task SynchronousBeginFailureDoesNotLeaveHoldLatchedOrInventRelease()
    {
        var hold = new PressToTalk(_ => throw new InvalidOperationException("Nothing sent"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => hold.BeginAsync()); Assert.False(hold.Held); Assert.False(hold.Beginning);
    }
    [Fact]
    public void VoicePanelCommandAndPlacementRemainUiOnly()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-voice-command-fixture");
        Assert.Equal("voice", ShellOptions.Parse(["--core-url", "http://127.0.0.1:18795", "--token-file", Path.Combine(root, "token"), "--state-root", root, "--show", "voice"]).Panel);
        Assert.True(new HostCommand(1, "p", "voice").Valid("p"));
        new ShellPreferences { Panels = new() { ["voice"] = new("fixture", 0, 0, 840, 530, 144) } }.Validate();
        new ShellPreferences().Validate();
    }
    [Fact]
    public void UnknownStatesMissingPolicyAndMalformedDevicesCannotBecomeCurrent()
    {
        Assert.Throws<InvalidDataException>(() => VoiceProjection.Parse(Voice("invented")));
        Assert.Throws<InvalidDataException>(() => VoiceProjection.Parse(Json(new { state = "ready", message = "", running = true, devices = Array.Empty<object>() })));
        Assert.Throws<InvalidDataException>(() => VoiceProjection.Parse(Json(new { state = "ready", message = "", running = true, enabled = true,
            devices = new[] { new { key = "same", input_channels = -1, output_channels = 0 } } })));
    }
    [Fact]
    public void AmbiguousDeviceKeysAreHonestInventoryNotAFabricatedSelectionOrLostMicStatus()
    {
        var data = Json(new { state = "recording", message = "Worker fixture", running = true, enabled = true, microphone_open = true,
            devices = new[] { new { key = "same", index = 1, input_channels = 1, output_channels = 0 }, new { key = "same", index = 2, input_channels = 1, output_channels = 0 } } });
        var projection = VoiceProjection.Parse(data); Assert.Equal(2, projection.Devices.Count);
        Assert.Equal(1, projection.Devices[0].Index); Assert.Equal(2, projection.Devices[1].Index);
        Assert.Equal("Mic ON · recording", projection.MicrophoneLabel(true));
    }
}
