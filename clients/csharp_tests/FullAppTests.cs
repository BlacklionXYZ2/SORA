using System.Text.Json;
using Sora.DesktopWidget;

public sealed class FullAppTests
{
    private static JsonElement Json(string content) => JsonDocument.Parse(content).RootElement.Clone();

    [Fact]
    public void SharedProjectionShowsCanonicalStateWithoutCredentialOrGrantIds()
    {
        var companion = new WidgetSnapshot(true, "", 12,
            [new WidgetMessage("message-1", "user", "Analyze this", DateTimeOffset.UtcNow)],
            [], [], 2, true);
        var tasks = Json("""{"tasks":[{"task_id":"task-1","creator_message_id":"message-1","status":"running","effective_backend":"hermes","result_ref":null,"updated_at":"2026-09-23T07:00:00Z"}]}""");
        var extensions = Json("""[{"extension_id":"integration-media","depth":"integration","version":"1.0","enabled":true,"capability_ids":["media.play"],"required_grants":["grant-media"],"config":{"secret":"must-not-render"}}]""");
        var content = Json("""{"references":[{"reference_id":"content:file:one","kind":"file","label":"report.txt","path":"C:\\Data\\report.txt","handler_id":"editor"}]}""");
        var permissions = Json("""{"total":1,"truncated":false,"grants":[{"device_id":"device-local","project_id":"project-sora","operation":"tool.invoke","resource":"content.navigate:test","status":"active","expires_at":"2026-09-24T07:00:00Z","used_count":0,"max_uses":1}]}""");
        var capabilities = Json("""{"active_extensions":["integration-media"]}""");
        var settings = Json("""{"owner_id":"owner-local","project_id":"project-sora","dialogue_backend":"openai-compatible","dialogue_model":"test-model","dialogue_base_url":"http://127.0.0.1:1234/v1","dialogue_api_key_configured":true,"worker_count":2,"context_max_chars":8000,"content_roots":["C:\\Data"],"editor_roots":[],"content_handlers":[{"handler_id":"editor","kinds":["file"]}],"coding_workspace_configured":false,"secrets":["***REDACTED***"]}""");

        var snapshot = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, settings);

        Assert.Equal("Analyze this", snapshot.Tasks[0].Description);
        Assert.Equal("hermes", snapshot.Tasks[0].Backend);
        Assert.Equal(2, snapshot.Companion.ActiveWorkers);
        Assert.Equal("content.navigate:test", snapshot.Permissions[0].Resource);
        Assert.Equal("C:\\Data", snapshot.Settings!.ContentRoots[0]);
        Assert.Equal("content:file:one", snapshot.Content[0].Id);
        Assert.True(snapshot.Settings.DialogueKeyConfigured);
        Assert.False(snapshot.Settings.DialogueManaged);
        var managedSettings = Json(settings.GetRawText().Replace(
            "\"dialogue_backend\":", "\"dialogue_managed\":true,\"dialogue_backend\":"));
        var managed = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, managedSettings);
        Assert.True(managed.Settings!.DialogueManaged);
        Assert.Equal(JsonValueKind.Undefined, managed.Settings.UnifiedSettings.ValueKind);
        var unifiedSettings = Json(managedSettings.GetRawText().Replace(
            "\"dialogue_backend\":", "\"settings_version\":2,\"fields\":[],\"dialogue_backend\":"));
        var unified = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, unifiedSettings);
        Assert.Equal(2, unified.Settings!.UnifiedSettings.GetProperty("settings_version").GetInt32());
        Assert.Equal(0, unified.Settings.UnifiedSettings.GetProperty("fields").GetArrayLength());
        var v4Settings = Json(unifiedSettings.GetRawText().Replace("\"settings_version\":2", "\"settings_version\":4"));
        var v4 = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, v4Settings);
        Assert.Equal(4, v4.Settings!.UnifiedSettings.GetProperty("settings_version").GetInt32());
        var v5Settings = Json(unifiedSettings.GetRawText().Replace("\"settings_version\":2", "\"settings_version\":5"));
        var v5 = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, v5Settings);
        Assert.Equal(5, v5.Settings!.UnifiedSettings.GetProperty("settings_version").GetInt32());
        var v6Settings = Json(unifiedSettings.GetRawText().Replace("\"settings_version\":2", "\"settings_version\":6"));
        var v6 = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, v6Settings);
        Assert.Equal(6, v6.Settings!.UnifiedSettings.GetProperty("settings_version").GetInt32());
        Assert.Equal(0, v6.Settings.UnifiedSettings.GetProperty("fields").GetArrayLength());
        var v9Settings = Json(unifiedSettings.GetRawText().Replace("\"settings_version\":2", "\"settings_version\":9"));
        var v9 = FullAppProjection.Parse(companion, tasks, extensions, content, permissions,
            capabilities, v9Settings);
        Assert.Equal(9, v9.Settings!.UnifiedSettings.GetProperty("settings_version").GetInt32());
        Assert.Equal(1, snapshot.Settings.SecretCount);
        Assert.DoesNotContain("must-not-render", JsonSerializer.Serialize(snapshot));
        Assert.DoesNotContain("grant-media", JsonSerializer.Serialize(snapshot.Settings));
    }

    [Fact]
    public void TaskAndContentActionsAreExactAndBounded()
    {
        Assert.Equal("/api/v1/tasks/task-1/steer", FullAppProjection.TaskPath("task-1", "steer"));
        Assert.Equal("/api/v1/tasks/task-1/cancel", FullAppProjection.TaskPath("task-1", "cancel"));
        Assert.Equal("/api/v1/board/cards/task-1/start", FullAppProjection.BoardPath("task-1", "start"));
        Assert.Equal("/api/v1/board/cards/task-1/move", FullAppProjection.BoardPath("task-1", "move"));
        Assert.Equal("/api/v1/board/cards/task-1/assign", FullAppProjection.BoardPath("task-1", "assign"));
        Assert.Equal("/api/v1/board/cards/task-1/remove", FullAppProjection.BoardPath("task-1", "remove"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.BoardPath("../private", "start"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.BoardPath("task-1", "delete"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.TaskPath("../settings", "cancel"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.TaskPath("task-1", "delete"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.NavigationRequest("../private", "open"));
        Assert.Throws<ArgumentException>(() => FullAppProjection.NavigationRequest("ref-1", "execute"));
        Assert.Contains("explicit_reference_id", JsonSerializer.Serialize(
            FullAppProjection.NavigationRequest("ref-1", "open")));
    }

    [Fact]
    public void BoardProjectionKeepsAssignmentSeparateFromRunProvenance()
    {
        var companion = WidgetSnapshot.Empty;
        var board = Json("""{"cards":[{"task_id":"task-1","column":"DONE","column_source":"manual","status":"planned","intent":"Sample note","specialist":null,"assigned_agent":"claude","needs_attention":false,"run_count":0,"board_version":2,"updated_at":"2026-09-23T07:00:00Z"}]}""");
        var snapshot = FullAppProjection.Parse(companion, Json("""{"tasks":[]}"""), Json("[]"),
            Json("""{"references":[]}"""), Json("""{"total":0,"truncated":false,"grants":[]}"""),
            Json("""{"active_extensions":[]}"""),
            Json("""{"owner_id":"owner","project_id":"project","dialogue_backend":"deterministic","dialogue_api_key_configured":false,"worker_count":1,"context_max_chars":1000,"content_roots":[],"editor_roots":[],"content_handlers":[],"coding_workspace_configured":false,"secrets":[]}"""), board);
        Assert.Equal("claude", snapshot.BoardCards[0].AssignedAgent);
        Assert.Equal("planned", snapshot.BoardCards[0].Status);
        Assert.Equal("DONE", snapshot.BoardCards[0].Column);
        Assert.True(snapshot.BoardCards[0].ManuallyPlaced);
        Assert.Equal(2, snapshot.BoardCards[0].BoardVersion);
    }

    [Fact]
    public void SettingsEditorUsesRevisionedCredentialFreePayloadAndPendingProjection()
    {
        var request = JsonSerializer.Serialize(FullAppProjection.SettingsUpdate(3,
            "openai-compatible", " local-model ", "http://127.0.0.1:1234/v1",
            20, 3, 12000, @"C:\Models"));
        Assert.Contains("\"expected_revision\":3", request);
        Assert.Contains("\"dialogue_model\":\"local-model\"", request);
        Assert.Contains("\"dialogue_model_folder\":\"C:\\\\Models\"", request);
        Assert.DoesNotContain("api_key", request);
        Assert.Throws<ArgumentException>(() => FullAppProjection.SettingsUpdate(3,
            "openai-compatible", "model", "https://user:secret@example.com/v1", 20, 3, 12000));
        Assert.Throws<ArgumentException>(() => FullAppProjection.SettingsUpdate(3,
            "openai-compatible", "model", "http://example.com/v1", 20, 3, 12000));
        Assert.Throws<ArgumentException>(() => FullAppProjection.SettingsUpdate(3,
            "deterministic", null, null, 20, 0, 12000));

        var settings = Json("""{"owner_id":"owner","project_id":"project","dialogue_backend":"deterministic","dialogue_model":null,"dialogue_model_folder":null,"dialogue_base_url":null,"dialogue_timeout_seconds":30,"dialogue_api_key_configured":true,"worker_count":2,"context_max_chars":8000,"settings_revision":3,"active_settings_revision":2,"restart_required":true,"pending_settings":{"dialogue_backend":"openai-compatible","dialogue_model":"local-model","dialogue_model_folder":"C:\\Models","dialogue_base_url":"http://127.0.0.1:1234/v1","dialogue_timeout_seconds":20,"worker_count":3,"context_max_chars":12000},"content_roots":[],"editor_roots":[],"content_handlers":[],"coding_workspace_configured":false,"secrets":["***REDACTED***"]}""");
        var snapshot = FullAppProjection.Parse(WidgetSnapshot.Empty, Json("""{"tasks":[]}"""),
            Json("[]"), Json("""{"references":[]}"""),
            Json("""{"total":0,"truncated":false,"grants":[]}"""),
            Json("""{"active_extensions":[]}"""), settings);
        Assert.Equal(3, snapshot.Settings!.SettingsRevision);
        Assert.Equal(2, snapshot.Settings.ActiveSettingsRevision);
        Assert.True(snapshot.Settings.RestartRequired);
        Assert.Equal("deterministic", snapshot.Settings.DialogueBackend);
        Assert.Equal("local-model", snapshot.Settings.Pending!.DialogueModel);
        Assert.Equal(@"C:\Models", snapshot.Settings.Pending.DialogueModelFolder);
        Assert.DoesNotContain("***REDACTED***", JsonSerializer.Serialize(snapshot));
    }

    [Fact]
    public async Task FullAppAndWidgetConvergeOnSameCanonicalSnapshotAfterReconnect()
    {
        var api = new SharedApi();
        var widget = new WidgetSync(api);
        var full = new FullAppSync(api, widget);
        var first = await full.RefreshAsync();
        Assert.Same(widget.Current, first.Companion);
        Assert.Equal("working", first.Tasks[0].Status);
        Assert.Single(first.Content);
        Assert.Single(first.BoardCards);
        Assert.Equal("DOING", first.BoardCards[0].Column);

        api.Fail = true;
        var offline = await full.RefreshAsync();
        Assert.False(offline.Companion.Connected);
        Assert.Single(offline.Content);
        Assert.Single(offline.Companion.Messages);

        api.Fail = false;
        api.Completed = true;
        var recovered = await full.RefreshAsync();
        Assert.Same(widget.Current, recovered.Companion);
        Assert.True(recovered.Companion.Connected);
        Assert.Equal("completed", recovered.Tasks[0].Status);
        Assert.Equal("DONE", recovered.BoardCards[0].Column);
        Assert.Equal(2, recovered.Companion.Messages.Count);
    }

    private sealed class SharedApi : IWidgetApi
    {
        public bool Fail { get; set; }
        public bool Completed { get; set; }

        public Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        public Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken)
        {
            if (Fail) throw new HttpRequestException("Core is restarting");
            string json;
            if (path.StartsWith("/api/v1/events?", StringComparison.Ordinal))
                json = Completed
                    ? """{"events":[{"sequence":2}],"next_sequence":2,"more_available":false,"resync_required":false}"""
                    : """{"events":[{"sequence":1}],"next_sequence":1,"more_available":false,"resync_required":false}""";
            else if (path.StartsWith("/api/v1/messages?", StringComparison.Ordinal))
                json = Completed
                    ? """[{"message_id":"m1","role":"user","content":"Hello","created_at":"2026-09-23T07:00:00Z"},{"message_id":"m2","role":"assistant","content":"Done","created_at":"2026-09-23T07:01:00Z"}]"""
                    : """[{"message_id":"m1","role":"user","content":"Hello","created_at":"2026-09-23T07:00:00Z"}]""";
            else if (path.StartsWith("/api/v1/tasks?", StringComparison.Ordinal))
                json = Completed
                    ? """{"tasks":[{"task_id":"task-1","creator_message_id":"m1","status":"completed","effective_backend":"codex","result_ref":"result-1","updated_at":"2026-09-23T07:01:00Z"}]}"""
                    : """{"tasks":[{"task_id":"task-1","creator_message_id":"m1","status":"working","effective_backend":"codex","result_ref":null,"updated_at":"2026-09-23T07:00:00Z"}]}""";
            else if (path == "/api/v1/projections/companion")
                json = """{"companion":{"dialogue_ready":true},"background_workers_active":1}""";
            else if (path == "/api/v1/status")
                json = """{"providers":{"codex":{"available":true,"display_name":"Cody"}}}""";
            else if (path == "/api/v1/extensions") json = "[]";
            else if (path == "/api/v1/content/references")
                json = """{"references":[{"reference_id":"content:file:one","kind":"file","label":"one.txt","path":"C:\\Data\\one.txt","handler_id":"editor"}]}""";
            else if (path == "/api/v1/projections/permissions")
                json = """{"total":0,"truncated":false,"grants":[]}""";
            else if (path == "/api/v1/projections/capabilities")
                json = """{"active_extensions":[]}""";
            else if (path == "/api/v1/projections/settings")
                json = """{"owner_id":"owner-local","project_id":"project-sora","dialogue_backend":"deterministic","dialogue_model":null,"dialogue_base_url":null,"dialogue_api_key_configured":false,"worker_count":2,"context_max_chars":8000,"content_roots":[],"editor_roots":[],"content_handlers":[],"coding_workspace_configured":false,"secrets":[]}""";
            else if (path == "/api/v1/projections/objects")
                json = Completed
                    ? """{"cards":[{"task_id":"task-1","column":"DONE","status":"completed","intent":"Hello","specialist":"codex","needs_attention":false,"run_count":1,"updated_at":"2026-09-23T07:01:00Z"}]}"""
                    : """{"cards":[{"task_id":"task-1","column":"DOING","status":"working","intent":"Hello","specialist":"codex","needs_attention":false,"run_count":1,"updated_at":"2026-09-23T07:00:00Z"}]}""";
            else throw new ArgumentException(path);
            return Task.FromResult(Json(json));
        }
    }
}
