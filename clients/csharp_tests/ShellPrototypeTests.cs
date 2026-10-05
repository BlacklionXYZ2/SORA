using System.Text.Json;
using Sora.DesktopShell;
using Sora.DesktopWidget;

public sealed class ShellPrototypeTests
{
    private sealed class Api : IWidgetApi
    {
        public bool Offline, ModelDown;
        public List<(string Path, JsonElement Body)> Posts = [];
        public TaskCompletionSource<JsonElement>? Pending;
        public Task<JsonElement> GetAsync(string path, CancellationToken token)
        {
            if (Offline) throw new IOException("Fixture disconnected");
            return Task.FromResult(JsonSerializer.SerializeToElement(path.Split('?')[0] switch {
                "/api/v1/events" => (object)new { events = new object[] { new { sequence = 1 } },
                    next_sequence = 1, more_available = false, resync_required = false },
                "/api/v1/messages" => Array.Empty<object>(),
                "/api/v1/tasks" => new { tasks = Array.Empty<object>() },
                "/api/v1/projections/companion" => new { companion = new {
                    dialogue_ready = !ModelDown, model_state = ModelDown ? "down" : "ready",
                    state = "idle", dialogue_model = "Deterministic fixture" }, background_workers_active = 0 },
                "/api/v1/status" => new { providers = new Dictionary<string, object>() },
                "/api/v1/projections/settings" => new { settings_version = 9, fields = Array.Empty<object>() },
                _ => throw new InvalidOperationException(path)
            }));
        }
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken token)
        {
            Posts.Add((path, JsonSerializer.SerializeToElement(body)));
            if (path.EndsWith("/cancel")) return Task.FromResult(JsonSerializer.SerializeToElement(new { state = "cancelling" }));
            return Pending?.Task ?? Task.FromResult(JsonSerializer.SerializeToElement(new { response = "Fixture reply" }));
        }
    }
    [Fact]
    public async Task OfflineNeverInventsSettingsOrLosesDraft()
    {
        var api = new Api { Offline = true }; using var session = new ShellSession(api) { Draft = "Keep this" };
        await session.RefreshAsync(default);
        Assert.False(session.CanSend); Assert.Null(session.Settings);
        Assert.Contains("No settings", session.SettingsError); Assert.Equal("Keep this", session.Draft);
        Assert.Empty(api.Posts);
    }
    [Fact]
    public async Task DisconnectRetainsMarkedStaleSettingsAndReconnectDoesNotReplay()
    {
        var api = new Api(); using var session = new ShellSession(api) { Draft = "Unsent draft" };
        await session.RefreshAsync(default); Assert.True(session.CanSend);
        api.Offline = true; await session.RefreshAsync(default);
        Assert.False(session.CanSend); Assert.NotNull(session.Settings); Assert.Contains("stale", session.SettingsError);
        api.Offline = false; await session.RefreshAsync(default);
        Assert.True(session.CanSend); Assert.Empty(api.Posts); Assert.Equal("Unsent draft", session.Draft);
    }
    [Fact]
    public async Task ModelUnavailableStillReadsSettings()
    {
        var api = new Api { ModelDown = true }; using var session = new ShellSession(api);
        await session.RefreshAsync(default);
        Assert.True(session.Snapshot.Connected); Assert.False(session.CanSend); Assert.NotNull(session.Settings);
        Assert.Contains("Model unavailable", session.Snapshot.StatusLabel);
        Assert.Empty(session.SettingsError);
    }
    [Fact]
    public async Task StopUsesExactNonceAndTypedCancellationRetainsNewDraft()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api) { Draft = "Submitted" };
        await session.RefreshAsync(default); var send = session.SendAsync(default);
        Assert.True(session.Sending); Assert.False(session.CanSend);
        session.Draft = "New draft while waiting"; await session.StopAsync(default);
        Assert.Equal(api.Posts[0].Body.GetProperty("request_id").GetString(),
            api.Posts[1].Body.GetProperty("request_id").GetString());
        Assert.Contains("accepted Stop", session.Operation);
        api.Pending.SetException(new SoraRequestException("Response stopped", "DIALOGUE_CANCELLED"));
        await Assert.ThrowsAsync<SoraRequestException>(() => send);
        Assert.Equal("New draft while waiting", session.Draft); Assert.Contains("Response stopped", session.Operation);
        Assert.False(session.Sending); Assert.Equal(2, api.Posts.Count);
    }
    [Fact]
    public async Task SuccessClearsOnlyTheSubmittedDraftAndCannotDoubleSend()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api) { Draft = "Submitted" };
        await session.RefreshAsync(default); var send = session.SendAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => session.SendAsync(default));
        session.Draft = "Next thought"; api.Pending.SetResult(JsonSerializer.SerializeToElement(new { response = "Reply" }));
        await send; Assert.Equal("Next thought", session.Draft); Assert.Single(api.Posts);
        api.Pending = null; await session.SendAsync(default); Assert.Empty(session.Draft);
    }
    [Fact]
    public async Task AttachmentsUseTypedPathsWithoutEmbeddingOrReadingContentsAndPreserveNewSelections()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api) { Draft = "Read this selected file" };
        var first = Path.Combine(Path.GetTempPath(), "synthetic-unread-file.txt");
        var second = Path.Combine(Path.GetTempPath(), "synthetic-next-file.txt");
        Assert.True(session.AddAttachment(first)); Assert.False(session.AddAttachment(first.ToUpperInvariant()));
        var sentId = session.Attachments.Single().Id;
        await session.RefreshAsync(default); var send = session.SendAsync(default);
        var body = api.Posts.Single().Body;
        Assert.Equal("Read this selected file", body.GetProperty("content").GetString());
        Assert.Equal([first], body.GetProperty("file_paths").EnumerateArray().Select(value => value.GetString()));
        Assert.False(body.TryGetProperty("preview", out _));
        session.RemoveAttachment(sentId); session.AddAttachment(first); session.AddAttachment(second);
        session.Draft = "Next draft";
        api.Pending.SetResult(JsonSerializer.SerializeToElement(new { response = "Fixture reply" }));
        await send; Assert.Equal("Next draft", session.Draft); Assert.Equal(2, session.Attachments.Count);
        Assert.DoesNotContain(session.Attachments, item => item.Id == sentId);
    }

    [Fact]
    public async Task FailedFileTurnRetainsDraftAndAttachmentsAndStopUsesItsNonce()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api) { Draft = "Attached turn" };
        session.AddAttachment(Path.Combine(Path.GetTempPath(), "file-turn.txt"));
        await session.RefreshAsync(default); var send = session.SendAsync(default);
        await session.StopAsync(default);
        Assert.Equal(api.Posts[0].Body.GetProperty("request_id").GetString(),
            api.Posts[1].Body.GetProperty("request_id").GetString());
        api.Pending.SetException(new SoraRequestException("Synthetic cancellation", "DIALOGUE_CANCELLED"));
        await Assert.ThrowsAsync<SoraRequestException>(() => send);
        Assert.Equal("Attached turn", session.Draft); Assert.Single(session.Attachments);
        api.Offline = true; await session.RefreshAsync(default);
        Assert.Single(session.Attachments); Assert.Equal(2, api.Posts.Count);
    }

    [Fact]
    public async Task SuccessRemovesOnlySentSelectionsAndDoesNotClearEditedThenRestoredText()
    {
        var api = new Api { Pending = new(TaskCreationOptions.RunContinuationsAsynchronously) };
        using var session = new ShellSession(api) { Draft = "Original" };
        session.AddAttachment(Path.Combine(Path.GetTempPath(), "sent.txt"));
        await session.RefreshAsync(default); var send = session.SendAsync(default);
        session.Draft = "Edited"; session.Draft = "Original";
        api.Pending.SetResult(JsonSerializer.SerializeToElement(new { response = "Reply" }));
        await send; Assert.Equal("Original", session.Draft); Assert.Empty(session.Attachments);
    }

    [Fact]
    public void SelectionLimitAndMalformedPathsDoNotReadFilesOrModifyPreviousSelections()
    {
        using var session = new ShellSession(new Api());
        foreach (var name in new[] { "one", "two", "three" }) session.AddAttachment(Path.Combine(Path.GetTempPath(), name));
        Assert.Throws<ArgumentException>(() => session.AddAttachment(Path.Combine(Path.GetTempPath(), "four")));
        Assert.Throws<ArgumentException>(() => session.AddAttachment("bad\npath"));
        Assert.Equal(3, session.Attachments.Count);
        var snapshot = session.Attachments; session.RemoveAttachment(snapshot[0].Id);
        Assert.Equal(3, snapshot.Count); Assert.Equal(2, session.Attachments.Count);
    }

    [Fact]
    public void TranscriptIsInertAndAppendDetectionDoesNotHideEditedMessages()
    {
        var original = new WidgetMessage("id", "assistant", "# Heading\n\n```html\n<script>neverExecute()</script>\n```\n[site](https://example.invalid) Ω",
            DateTimeOffset.Parse("2026-10-04T00:00:00Z"));
        var entry = ChatPresentation.Entry(original);
        Assert.Equal("SORA", entry.Speaker); Assert.Equal("id", entry.Id);
        Assert.Contains(entry.Paragraphs, line => line.Code && line.Text == "<script>neverExecute()</script>");
        Assert.Contains("site (https://example.invalid) Ω", entry.PlainText);
        Assert.True(ChatPresentation.IsAppend([original], [original, original with { Id = "next" }]));
        Assert.False(ChatPresentation.IsAppend([original], [original with { Content = "Corrected" }]));
        Assert.False(ChatPresentation.IsAppend([original], []));
    }

    [Theory]
    [InlineData(true, false, false, false, false, false, true)]
    [InlineData(true, true, false, false, false, false, false)]
    [InlineData(true, false, true, false, false, false, false)]
    [InlineData(true, false, false, true, false, false, false)]
    [InlineData(true, false, false, false, true, false, false)]
    [InlineData(true, false, false, false, false, true, false)]
    [InlineData(false, false, false, false, false, false, false)]
    public void ComposerDoesNotSubmitNewlinesOrImeCommit(bool enter, bool shift, bool control, bool alt,
        bool composing, bool commitPending, bool expected) =>
        Assert.Equal(expected, ChatPresentation.ShouldSend(enter, shift, control, alt, composing, commitPending));

    [Fact]
    public void GraphBoundsInputAndDoesNotInventRelationships()
    {
        var nodes = Enumerable.Range(0, 2000).Select(index => new GraphNode($"n{index:0000}", "Node"));
        var scene = GraphLayout.Arrange(nodes, [new("n0000", "n0001", "Fixture evidence"),
            new("n0000", "missing", "Bad"), new("n0000", "n0002", "")]);
        Assert.Equal(75, scene.Nodes.Count); Assert.True(scene.Truncated);
        Assert.Single(scene.Edges); Assert.All(scene.Nodes, node => {
            Assert.InRange(node.X, 0, 1); Assert.InRange(node.Y, 0, 1); });
    }
    [Fact]
    public void GraphIsStableAndRejectsDuplicateIds()
    {
        GraphNode[] nodes = [new("a", "A"), new("b", "B"), new("c", "C")];
        Assert.Equal(GraphLayout.Arrange(nodes, []).Nodes, GraphLayout.Arrange(nodes.Reverse(), []).Nodes);
        Assert.Throws<ArgumentException>(() => GraphLayout.Arrange([nodes[0], nodes[0]], []));
    }
    [Theory]
    [InlineData(0xEDF3FBu, 0x111B2Bu, 4.5)]
    [InlineData(0xAAB9CCu, 0x1A283Bu, 4.5)]
    [InlineData(0x48C7F0u, 0x1A283Bu, 3.0)]
    public void ProposedThemeHasMeasuredContrast(uint foreground, uint background, double minimum) =>
        Assert.True(GraphLayout.Contrast(foreground, background) >= minimum);
}
