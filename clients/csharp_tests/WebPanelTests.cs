using System.Net;
using System.Text;
using System.Text.Json;
using Sora.DesktopShell;
using Xunit;

public sealed class WebPanelTests
{
    private sealed class RecordingHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
    {
        public List<(HttpRequestMessage Request, string? Body)> Calls { get; } = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var body = request.Content is null ? null : await request.Content.ReadAsStringAsync(token);
            Calls.Add((request, body));
            return respond(request);
        }
    }

    private static (PanelApiProxy Proxy, RecordingHandler Handler, string TokenFile) Proxy(
        Func<HttpRequestMessage, HttpResponseMessage>? respond = null, string token = "owner-token-0123456789")
    {
        var tokenFile = Path.Combine(Path.GetTempPath(), "sora-panel-token-" + Guid.NewGuid().ToString("N"));
        File.WriteAllText(tokenFile, token + "\n");
        var handler = new RecordingHandler(respond ?? (_ => new HttpResponseMessage(HttpStatusCode.OK)
            { Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json") }));
        return (new PanelApiProxy(new Uri("http://127.0.0.1:8765"), tokenFile, () => "core-a", handler), handler, tokenFile);
    }

    [Theory]
    [InlineData("{\"type\":\"window.hide\"}", PanelCommandKind.Hide, null)]
    [InlineData("{\"type\":\"window.drag\"}", PanelCommandKind.Drag, null)]
    [InlineData("{\"type\":\"panel.open\",\"panel\":\"voice\"}", PanelCommandKind.OpenPanel, "voice")]
    [InlineData("{\"type\":\"panel.ready\"}", PanelCommandKind.Ready, null)]
    public void BridgeAcceptsKnownMessages(string json, PanelCommandKind kind, string? panel)
    {
        var command = PanelBridge.Parse(json);
        Assert.NotNull(command);
        Assert.Equal(kind, command!.Kind);
        Assert.Equal(panel, command.Panel);
    }

    [Theory]
    [InlineData("{\"type\":\"shell.exec\",\"command\":\"calc\"}")]
    [InlineData("{\"type\":\"panel.open\",\"panel\":\"C:\\\\Windows\"}")]
    [InlineData("{\"type\":\"panel.open\"}")]
    [InlineData("{\"type\":\"window.resize\",\"edge\":\"middle\"}")]
    [InlineData("{\"type\":7}")]
    [InlineData("[\"window.hide\"]")]
    [InlineData("\"window.hide\"")]
    [InlineData("not json")]
    [InlineData("{\"type\":\"file.pick\",\"kind\":\"script\",\"requestId\":\"pick-1\"}")]
    [InlineData("{\"type\":\"file.pick\",\"kind\":\"gguf\",\"requestId\":\"bad id!\"}")]
    [InlineData("{\"type\":\"file.pick\",\"kind\":\"gguf\"}")]
    public void BridgeDropsAnythingElse(string json) => Assert.Null(PanelBridge.Parse(json));

    [Fact]
    public void BridgeFilePickStartsOnlyInAnExistingLocalFolder()
    {
        var folder = Path.GetTempPath();
        var json = "{\"type\":\"file.pick\",\"kind\":\"gguf\",\"requestId\":\"pick-1\",\"start\":"
            + System.Text.Json.JsonSerializer.Serialize(folder) + "}";
        Assert.Equal(Path.GetFullPath(folder), PanelBridge.Parse(json)!.StartFolder);
        Assert.Null(PanelBridge.StartFolder(@"\server\share"));
        Assert.Null(PanelBridge.StartFolder("relative\folder"));
        Assert.Null(PanelBridge.StartFolder(Path.Combine(folder, "no-such-folder-" + Guid.NewGuid())));
        Assert.Null(PanelBridge.Parse("{\"type\":\"file.pick\",\"kind\":\"gguf\",\"requestId\":\"pick-1\",\"start\":5}"));
    }

    [Fact]
    public void BridgeDirtyReportsAreBooleansOnly()
    {
        Assert.True(PanelBridge.Parse("{\"type\":\"panel.dirty\",\"dirty\":true}")!.Dirty);
        Assert.False(PanelBridge.Parse("{\"type\":\"panel.dirty\",\"dirty\":false}")!.Dirty);
        Assert.Null(PanelBridge.Parse("{\"type\":\"panel.dirty\",\"dirty\":\"yes\"}"));
        Assert.Null(PanelBridge.Parse("{\"type\":\"panel.dirty\"}"));
    }

    [Fact]
    public void BridgePanelOpenCarriesOnlyAnExactSelection()
    {
        var command = PanelBridge.Parse("{\"type\":\"panel.open\",\"panel\":\"activity\",\"select\":\"task-1\"}");
        Assert.Equal(("activity", "task-1"), (command!.Panel, command.Select));
        Assert.Null(PanelBridge.Parse("{\"type\":\"panel.open\",\"panel\":\"activity\"}")!.Select);
        Assert.Null(PanelBridge.Parse("{\"type\":\"panel.open\",\"panel\":\"activity\",\"select\":\"../x\"}"));
        Assert.Null(PanelBridge.Parse("{\"type\":\"panel.open\",\"panel\":\"activity\",\"select\":7}"));
    }

    [Fact]
    public void BridgeFilePicksCarryAKnownKindAndSafeRequestId()
    {
        var command = PanelBridge.Parse("{\"type\":\"file.pick\",\"kind\":\"gguf\",\"requestId\":\"pick-1\"}");
        Assert.Equal(PanelCommandKind.PickFile, command!.Kind);
        Assert.Equal(("gguf", "pick-1"), (command.PickKind, command.RequestId));
        Assert.Equal("GGUF model (*.gguf)|*.gguf", PanelBridge.Filter("gguf"));
        Assert.Null(PanelBridge.Filter("dir"));
        Assert.Null(PanelBridge.Parse("{\"type\":\"file.pick\",\"kind\":\"gguf\",\"requestId\":\"" + new string('a', 65) + "\"}"));
    }

    [Fact]
    public void BridgeResizeEdgesMapToWindowsHitTests()
    {
        Assert.Equal(PanelCommandKind.Resize, PanelBridge.Parse("{\"type\":\"window.resize\",\"edge\":\"se\"}")!.Kind);
        Assert.Equal(17, PanelBridge.HitTest("se"));
        Assert.Equal(10, PanelBridge.HitTest("w"));
        Assert.Null(PanelBridge.Parse("{\"type\":\"window.hide\",\"padding\":\"" + new string('x', 5000) + "\"}"));
    }

    [Theory]
    [InlineData("GET", "https://panels.sora.example/api/v1/messages?limit=100", "/api/v1/messages?limit=100")]
    [InlineData("POST", "https://panels.sora.example/api/v1/dialogue", "/api/v1/dialogue")]
    [InlineData("GET", "https://panels.sora.example/api/v1/memory?q=a..b", "/api/v1/memory?q=a..b")]
    [InlineData("DELETE", "https://panels.sora.example/api/v1/messages", null)]
    [InlineData("GET", "https://evil.example/api/v1/messages", null)]
    [InlineData("GET", "http://panels.sora.example/api/v1/messages", null)]
    [InlineData("GET", "https://panels.sora.example:444/api/v1/messages", null)]
    [InlineData("GET", "https://panels.sora.example/api/v1/../v0/x", null)]
    [InlineData("GET", "https://panels.sora.example/api/v1//x", null)]
    [InlineData("GET", "https://panels.sora.example/chat/index.html", null)]
    public void ProxyOnlyForwardsPanelApiCalls(string method, string uri, string? expected) =>
        Assert.Equal(expected, PanelApiProxy.CorePath(method, uri));

    [Fact]
    public async Task ProxyAddsTokenAndCoreIdentityAndPassesBodyAndStatus()
    {
        var (proxy, handler, tokenFile) = Proxy(_ => new HttpResponseMessage(HttpStatusCode.Created)
            { Content = new StringContent("{\"response\":\"hi\"}") });
        using (proxy)
        {
            var result = await proxy.ForwardAsync("POST", "https://panels.sora.example/api/v1/dialogue",
                "{\"content\":\"hello\",\"request_id\":\"r1\"}", CancellationToken.None);
            Assert.Equal(201, result.Status);
            Assert.Equal("{\"response\":\"hi\"}", result.Body);
            var (request, body) = Assert.Single(handler.Calls);
            Assert.Equal("http://127.0.0.1:8765/api/v1/dialogue", request.RequestUri!.ToString());
            Assert.Equal("Bearer owner-token-0123456789", request.Headers.Authorization!.ToString());
            Assert.Equal("core-a", Assert.Single(request.Headers.GetValues("X-SORA-Core-Instance")));
            Assert.Equal("{\"content\":\"hello\",\"request_id\":\"r1\"}", body);
        }
        File.Delete(tokenFile);
    }

    [Fact]
    public async Task ProxyRefusalsAndFailuresNeverReachCoreOrLeakTheToken()
    {
        var (proxy, handler, tokenFile) = Proxy(_ => throw new HttpRequestException("refused"));
        using (proxy)
        {
            var refused = await proxy.ForwardAsync("GET", "https://evil.example/api/v1/messages", null, default);
            Assert.Equal(404, refused.Status);
            Assert.Empty(handler.Calls);
            var tooLarge = await proxy.ForwardAsync("POST", "https://panels.sora.example/api/v1/dialogue",
                new string('x', PanelApiProxy.MaxBodyBytes + 1), default);
            Assert.Equal(413, tooLarge.Status);
            var down = await proxy.ForwardAsync("GET", "https://panels.sora.example/api/v1/messages", null, default);
            Assert.Equal(503, down.Status);
            Assert.Equal("CORE_UNAVAILABLE", JsonDocument.Parse(down.Body).RootElement.GetProperty("error").GetProperty("code").GetString());
            foreach (var body in new[] { refused.Body, tooLarge.Body, down.Body })
                Assert.DoesNotContain("owner-token", body);
        }
        File.Delete(tokenFile);
    }

    [Fact]
    public async Task ProxyWaitsForAMissingOrShortTokenWithoutCallingCore()
    {
        var (proxy, handler, tokenFile) = Proxy(token: "short");
        using (proxy)
        {
            var result = await proxy.ForwardAsync("GET", "https://panels.sora.example/api/v1/messages", null, default);
            Assert.Equal(503, result.Status);
            Assert.Empty(handler.Calls);
        }
        File.Delete(tokenFile);
    }

    [Fact]
    public void ProxyOnlyTalksToLoopbackCore() =>
        Assert.Throws<ArgumentException>(() => new PanelApiProxy(new Uri("http://192.168.1.5:8765"), "token", () => null));

    [Fact]
    public void PanelFilesServeOnlyShippedPanelFiles()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-panels-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "chat"));
        File.WriteAllText(Path.Combine(root, "chat", "index.html"), "<html></html>");
        File.WriteAllText(Path.Combine(root, "chat", "notes.txt"), "not a panel type");
        File.WriteAllText(Path.Combine(Path.GetDirectoryName(root)!, "secret.html"), "outside");
        try
        {
            var page = PanelFiles.Resolve(root, "GET", "https://panels.sora.example/chat/index.html?v=1");
            Assert.NotNull(page);
            Assert.Equal("text/html; charset=utf-8", page!.Value.ContentType);
            foreach (var (method, uri) in new[]
            {
                ("POST", "https://panels.sora.example/chat/index.html"),
                ("GET", "https://panels.sora.example/api/v1/status"),
                ("GET", "https://other.example/chat/index.html"),
                ("GET", "http://panels.sora.example/chat/index.html"),
                ("GET", "https://panels.sora.example/../secret.html"),
                ("GET", "https://panels.sora.example/%2e%2e/secret.html"),
                ("GET", "https://panels.sora.example/chat/notes.txt"),
                ("GET", "https://panels.sora.example/chat/missing.html"),
            })
                Assert.Null(PanelFiles.Resolve(root, method, uri));
        }
        finally
        {
            Directory.Delete(root, true);
            File.Delete(Path.Combine(Path.GetDirectoryName(root)!, "secret.html"));
        }
    }
}
