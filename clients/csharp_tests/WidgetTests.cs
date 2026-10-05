using System.Drawing;
using System.IO.Compression;
using System.Text.Json;
using Sora.DesktopWidget;

public sealed class WidgetTests
{
    [Fact]
    public void DelegationCarriesExactSelectionAndPreservesRetryKey()
    {
        var body = AgentSelection.TaskBody("Inspect", "ref-1",
            new("hermes-acp", "openai:gpt-6-luna", null), "retry-1");
        Assert.Equal("hermes-acp", body["explicit_provider"]);
        Assert.Equal("openai:gpt-6-luna", body["explicit_model"]);
        Assert.Equal("retry-1", body["idempotency_key"]);
        Assert.Equal("ref-1", body["reference_id"]);
        Assert.False(body.ContainsKey("explicit_effort"));
        Assert.False(AgentSelection.TaskBody("Inspect", null, null).ContainsKey("explicit_model"));
        var project = AgentSelection.TaskBody("Edit", null,
            new("codex", null, null, "C:\\QA\\Project", "direct"));
        Assert.Equal("C:\\QA\\Project", project["working_directory"]);
        Assert.Equal("direct", project["workspace_mode"]);
        Assert.Throws<ArgumentException>(() => AgentSelection.TaskBody("Inspect", null,
            new(null, "model", "low")));
    }

    [Fact]
    public void ChatMarkdownIsReadableWithoutChangingUserTextOrCode()
    {
        var source = "## Summary\n* **Main Workspace:** Ready\nUse `**literal**` and *emphasis*.\n```cs\nvar x = \"**literal**\";\n```";
        Assert.Equal("Summary\n• Main Workspace: Ready\nUse **literal** and emphasis.\nvar x = \"**literal**\";",
            ChatText.Plain(source));
        Assert.Equal("**owner literal**", ChatText.Plain("**owner literal**", false));
        Assert.Equal("Read docs (https://example.com)",
            ChatText.Plain("Read [docs](https://example.com)"));
        Assert.Equal("name_with_underscores", ChatText.Plain("name_with_underscores"));
        Assert.Contains(ChatText.Lines(source), line => line.Code);
    }

    [Fact]
    public void DialogueStatusDoesNotConfuseAvailableSpecialistsWithTheAnsweringModel()
    {
        var state = WidgetSnapshot.Empty with { Connected = true, DialogueReady = true,
            DialogueModel = "Local QA model", ActiveWorkers = 3 };
        Assert.Equal("Ready to talk", state.StatusLabel);
        Assert.Equal("Thinking…", (state with { DialogueState = "thinking" }).StatusLabel);
        Assert.Equal("Speaking…", (state with { DialogueState = "talking" }).StatusLabel);
        Assert.Equal("Model reloading…",
            (state with { DialogueReady = false, ModelState = "reloading" }).StatusLabel);
        Assert.Equal("Reconnecting…", (state with { Connected = false }).StatusLabel);
    }
    [Fact]
    public async Task PollTimeoutDisconnectsWithoutCrashingAndCallerCancellationStillPropagates()
    {
        var api = new CancelledApi();
        var widget = new WidgetSync(api);
        Assert.False((await widget.RefreshAsync()).Connected);
        var full = new FullAppSync(api, widget);
        Assert.False((await full.RefreshAsync()).Companion.Connected);
        using var caller = new CancellationTokenSource();
        caller.Cancel();
        await Assert.ThrowsAsync<TaskCanceledException>(() => widget.RefreshAsync(caller.Token));
        await Assert.ThrowsAsync<TaskCanceledException>(() => full.RefreshAsync(caller.Token));
    }

    private sealed class CancelledApi : IWidgetApi
    {
        public Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken) =>
            throw new TaskCanceledException("Simulated polling deadline");
        public Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken) =>
            throw new NotSupportedException();
    }

    [Fact]
    public void AnchorAndClampRespectNegativeSecondaryMonitorAndSmallWorkArea()
    {
        var secondary = new Rectangle(-1280, 813, 1280, 976);
        Assert.Equal(new Point(-436, 829),
            WidgetGeometry.AnchorTo(secondary, new Size(420, 700), WidgetAnchor.TopRight));
        Assert.Equal(new Point(-1280, 813),
            WidgetGeometry.Clamp(secondary, new Size(1600, 1100), new Point(3000, 3000)));
    }

    [Fact]
    public async Task ReconnectResynchronizesAuthoritativeConversationAndConcurrentSpecialists()
    {
        var api = new ScenarioApi();
        var sync = new WidgetSync(api);
        var initial = await sync.RefreshAsync();
        Assert.True(initial.Connected);
        Assert.Equal(2, initial.ActiveWorkers);
        Assert.Equal(["codex", "hermes"], initial.Tasks.Select(t => t.Backend));
        Assert.True(initial.DialogueReady);
        Assert.Single(initial.Messages);

        api.Fail = true;
        var disconnected = await sync.RefreshAsync();
        Assert.False(disconnected.Connected);
        Assert.Equal(initial.Messages, disconnected.Messages);

        api.Fail = false;
        api.Updated = true;
        var reconnected = await sync.RefreshAsync();
        Assert.True(reconnected.Connected);
        Assert.Equal(3, reconnected.Messages.Count);
        Assert.Equal("SORA is still here", reconnected.Messages[^1].Content);
        Assert.Equal(2, reconnected.ActiveWorkers);
        Assert.Equal(2, reconnected.Sequence);
        Assert.DoesNotContain("private reasoning", reconnected.Messages.Select(m => m.Content));
    }

    [Fact]
    public void ExplicitAttachmentSeparatesLocalImagePreviewFromSentText()
    {
        var path = Path.Combine(Path.GetTempPath(), "sora-widget-test-" + Guid.NewGuid() + ".txt");
        try
        {
            File.WriteAllText(path, "sector 3 lost 2.3 seconds");
            var selected = WidgetAttachments.Inspect(path);
            Assert.True(selected.Embedded);
            var sent = WidgetAttachments.Compose("Analyze this", [selected], "ref-test-1");
            Assert.Contains("sector 3 lost 2.3 seconds", sent);
            Assert.Contains("ref-test-1", sent);
            var image = new WidgetAttachment("C:\\fixture\\frame.png", "frame.png", "image", "local", false);
            var imageSent = WidgetAttachments.Compose("What is this?", [image], null);
            Assert.DoesNotContain("image pixels", imageSent);
            Assert.Contains("contents are not included", imageSent);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void DocumentPreviewReadsSelectedDocxTextWithoutSendingBinaryBytes()
    {
        var path = Path.Combine(Path.GetTempPath(), "sora-widget-doc-" + Guid.NewGuid() + ".docx");
        try
        {
            using (var archive = ZipFile.Open(path, ZipArchiveMode.Create))
            using (var writer = new StreamWriter(archive.CreateEntry("word/document.xml").Open()))
                writer.Write("<w:document xmlns:w='urn:w'><w:body><w:p><w:r><w:t>Readable</w:t></w:r><w:r><w:t>document</w:t></w:r></w:p></w:body></w:document>");
            var selected = WidgetAttachments.Inspect(path);
            Assert.Equal("Readable document", selected.Preview);
            Assert.False(selected.Embedded);
            var sent = WidgetAttachments.Compose("Read this", [selected], null);
            Assert.Contains(path, sent);
            Assert.DoesNotContain("Readable document", sent);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void WidgetApiRejectsNonLoopbackDestination()
    {
        Assert.Throws<ArgumentException>(() =>
            new WidgetApiClient(new Uri("https://example.com"), "token.txt", "widget-owner"));
        Assert.Throws<ArgumentException>(() =>
            new WidgetApiClient(new Uri("http://localhost:8765"), "token.txt", "widget-owner"));
    }

    [Fact]
    public async Task FileAndDesktopDialogueUseExplicitCoreRoutes()
    {
        var api = new RecordingPostApi();
        var sync = new WidgetSync(api);
        await sync.DialogueWithFilesAsync("Summarize this", [@"C:\Users\owner\note.txt"]);
        await sync.DesktopDialogueAsync("What is on screen?");
        Assert.Equal("/api/v1/dialogue", api.Posts[0].Path);
        Assert.Equal("Summarize this", api.Posts[0].Body.GetProperty("content").GetString());
        Assert.Equal(@"C:\Users\owner\note.txt",
            api.Posts[0].Body.GetProperty("file_paths")[0].GetString());
        Assert.Equal("/api/v1/dialogue/desktop", api.Posts[1].Path);
        Assert.Equal("What is on screen?", api.Posts[1].Body.GetProperty("content").GetString());
    }

    [Fact]
    public async Task StopUsesExactConversationRequestNotSpecialistTaskId()
    {
        var api = new RecordingPostApi();
        var sync = new WidgetSync(api);
        await sync.DialogueAsync("Hello", requestId: "turn-one");
        await sync.DialogueWithFilesAsync("Read", [@"C:\fixture\note.txt"], requestId: "turn-two");
        await sync.DesktopDialogueAsync("Look", requestId: "turn-three");
        await sync.CancelDialogueAsync("turn-three");
        Assert.Equal("turn-one", api.Posts[0].Body.GetProperty("request_id").GetString());
        Assert.Equal("turn-two", api.Posts[1].Body.GetProperty("request_id").GetString());
        Assert.Equal("turn-three", api.Posts[2].Body.GetProperty("request_id").GetString());
        Assert.Equal("/api/v1/dialogue/cancel", api.Posts[3].Path);
        Assert.Equal("turn-three", api.Posts[3].Body.GetProperty("request_id").GetString());
        Assert.Equal("DIALOGUE_CANCELLED", new SoraRequestException("Stopped", "DIALOGUE_CANCELLED").Code);
    }

    private sealed class RecordingPostApi : IWidgetApi
    {
        public List<(string Path, JsonElement Body)> Posts { get; } = [];

        public Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken)
        {
            Posts.Add((path, JsonSerializer.SerializeToElement(body)));
            return Task.FromResult(JsonSerializer.SerializeToElement(new { response = "ok" }));
        }

        public Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken) =>
            throw new NotSupportedException();
    }

    private sealed class ScenarioApi : IWidgetApi
    {
        public bool Fail { get; set; }
        public bool Updated { get; set; }

        public Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        public Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken)
        {
            if (Fail) throw new HttpRequestException("Core restarting");
            string json;
            if (path.StartsWith("/api/v1/events?", StringComparison.Ordinal))
                json = Updated
                    ? """{"events":[{"sequence":2}],"next_sequence":2,"more_available":false,"resync_required":false}"""
                    : """{"events":[{"sequence":1}],"next_sequence":1,"more_available":false,"resync_required":false}""";
            else if (path.StartsWith("/api/v1/messages?", StringComparison.Ordinal))
                json = Updated
                    ? """[{"message_id":"m1","role":"user","content":"Hello","created_at":"2026-09-23T06:00:00Z"},{"message_id":"m2","role":"assistant","content":"Hi","created_at":"2026-09-23T06:00:01Z"},{"message_id":"m3","role":"assistant","content":"SORA is still here","created_at":"2026-09-23T06:00:02Z"}]"""
                    : """[{"message_id":"m1","role":"user","content":"Hello","created_at":"2026-09-23T06:00:00Z"}]""";
            else if (path.StartsWith("/api/v1/tasks?", StringComparison.Ordinal))
                json = """{"tasks":[{"task_id":"task-cody","status":"working","effective_backend":"codex"},{"task_id":"task-hermes","status":"working","effective_backend":"hermes"}]}""";
            else if (path == "/api/v1/projections/companion")
                json = """{"companion":{"dialogue_ready":true},"background_workers_active":2}""";
            else if (path == "/api/v1/status")
                json = """{"providers":{"codex":{"available":true,"display_name":"Cody"},"hermes":{"available":true,"display_name":"Hermes"}}}""";
            else throw new ArgumentException(path);
            using var document = JsonDocument.Parse(json);
            return Task.FromResult(document.RootElement.Clone());
        }
    }
}
