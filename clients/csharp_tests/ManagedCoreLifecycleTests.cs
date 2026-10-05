using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using Sora.DesktopShell;

public sealed class ManagedCoreLifecycleTests
{
    private sealed class FixtureHandler(string root) : HttpMessageHandler
    {
        public string Epoch = Guid.NewGuid().ToString();
        public Guid? Session;
        public string Profile = root;
        public bool BadAcknowledgement;
        public bool Oversized;
        public readonly List<(string Path, bool Control, Guid? Request)> Calls = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var path = request.RequestUri!.AbsolutePath;
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("synthetic-api-token-123456789", request.Headers.Authorization.Parameter);
            Assert.DoesNotContain("X-SORA-Host-Control", request.Headers.ToString().Split('\n')
                .Where(line => line.StartsWith("Authorization:")));
            Guid? nonce = null;
            if (request.Content is not null)
            {
                Assert.True(request.Content.Headers.ContentLength > 0);
                using var body = JsonDocument.Parse(await request.Content.ReadAsStringAsync(cancellationToken));
                nonce = body.RootElement.GetProperty("request_id").GetGuid();
                Assert.Equal(Session, body.RootElement.GetProperty("managed_session_id").GetGuid());
            }
            Calls.Add((path, request.Headers.Contains("X-SORA-Host-Control"), nonce));
            if (path != "/api/v1/runtime/identity")
                Assert.Equal(Epoch, request.Headers.GetValues("X-SORA-Core-Instance").Single());
            object projection = path switch {
                "/api/v1/runtime/identity" => new { version = 1, instance_id = Epoch, state_root = Profile },
                "/api/v1/runtime/lifecycle" => new { version = 1, instance_id = Epoch,
                    managed_session_id = Session, state = Session is null ? "external" : "managed",
                    shutdown_request_id = (Guid?)null },
                "/api/v1/runtime/shutdown" => new { version = 1, instance_id = Epoch,
                    managed_session_id = Session, state = "shutdown_requested",
                    shutdown_request_id = BadAcknowledgement ? Guid.NewGuid() : nonce },
                _ => throw new InvalidOperationException(path)
            };
            return new HttpResponseMessage(nonce is null ? HttpStatusCode.OK : HttpStatusCode.Accepted) {
                Content = new StringContent(Oversized ? new string('x', 5000)
                    : JsonSerializer.Serialize(projection), Encoding.UTF8, "application/json") };
        }
    }

    private static (string Root, ShellOptions Options) Profile()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-lifecycle-unit-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var token = Path.Combine(root, "api-token");
        File.WriteAllText(token, "synthetic-api-token-123456789");
        return (root, ShellOptions.Parse(["--core-url", "http://127.0.0.1:18998",
            "--token-file", token, "--state-root", root]));
    }

    private static OwnedCoreLaunch IdleChild()
    {
        // Trusted, effect-free test child: exit through EOF/newline, never Kill().
        var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe")) {
            UseShellExecute = false, RedirectStandardInput = true,
            CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        foreach (var argument in new[] { "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::ReadLine() | Out-Null" }) start.ArgumentList.Add(argument);
        var child = OwnedCoreLaunch.Start(start);
        Assert.False(start.Environment.ContainsKey("SORA_DESKTOP_HOST_CONTROL_TOKEN"));
        Assert.False(start.Environment.ContainsKey("SORA_DESKTOP_HOST_SESSION"));
        return child;
    }

    private static async Task Finish(OwnedCoreLaunch child)
    {
        await child.Process.StandardInput.WriteLineAsync(); child.Process.StandardInput.Close();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await child.Process.WaitForExitAsync(timeout.Token);
        Assert.Equal(0, child.Process.ExitCode); child.Dispose();
    }

    [Fact]
    public async Task AttachedHostCannotPostShutdownEvenWhenProjectionReportsManaged()
    {
        var (root, options) = Profile();
        try
        {
            var handler = new FixtureHandler(root) { Session = Guid.NewGuid() };
            using var client = new ManagedCoreLifecycleClient(options, handler: handler);
            Assert.False((await client.InspectAsync(default)).Owned);
            await Assert.ThrowsAsync<InvalidOperationException>(() => client.RequestShutdownAsync(default));
            Assert.All(handler.Calls, call => Assert.False(call.Control));
            Assert.DoesNotContain(handler.Calls, call => call.Path.EndsWith("shutdown"));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public async Task WrongProfileAndOversizedProjectionFailBeforeShutdown()
    {
        var (root, options) = Profile();
        try
        {
            var handler = new FixtureHandler(root) { Profile = root + "-other" };
            using var client = new ManagedCoreLifecycleClient(options, handler: handler);
            await Assert.ThrowsAsync<InvalidOperationException>(() => client.InspectAsync(default));
            Assert.Single(handler.Calls); handler.Profile = root; handler.Oversized = true;
            await Assert.ThrowsAsync<IOException>(() => client.InspectAsync(default));
            Assert.All(handler.Calls, call => Assert.False(call.Control));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public async Task OwnedChildBindsOnceAndUsesOneShutdownNonceAcrossRetries()
    {
        var (root, options) = Profile(); var child = IdleChild();
        try
        {
            var handler = new FixtureHandler(root) { Session = child.SessionId };
            using var client = new ManagedCoreLifecycleClient(options, child, handler);
            Assert.True((await client.InspectAsync(default)).Owned);
            var first = await client.RequestShutdownAsync(default);
            var retry = await client.RequestShutdownAsync(default);
            Assert.Equal(first.ShutdownRequestId, retry.ShutdownRequestId);
            Assert.Equal("shutdown_requested", first.State);
            Assert.True(child.IsRunning); // ACK is not a claim of process exit.
            Assert.All(handler.Calls, call => Assert.Equal(call.Path.EndsWith("shutdown"), call.Control));
            handler.Epoch = Guid.NewGuid().ToString();
            await Assert.ThrowsAsync<InvalidOperationException>(() => client.RequestShutdownAsync(default));
            Assert.Equal(2, handler.Calls.Count(call => call.Path.EndsWith("shutdown")));
        }
        finally { await Finish(child); Directory.Delete(root, true); }
    }

    [Fact]
    public async Task AnotherSessionCannotBeAdoptedAndMismatchedAckIsNotSuccess()
    {
        var (root, options) = Profile(); var child = IdleChild();
        try
        {
            var handler = new FixtureHandler(root) { Session = child.SessionId, BadAcknowledgement = true };
            using var client = new ManagedCoreLifecycleClient(options, child, handler);
            await Assert.ThrowsAsync<IOException>(() => client.RequestShutdownAsync(default));
            handler.Session = Guid.NewGuid();
            await Assert.ThrowsAsync<InvalidOperationException>(() => client.RequestShutdownAsync(default));
            Assert.Single(handler.Calls, call => call.Path.EndsWith("shutdown"));
        }
        finally { await Finish(child); Directory.Delete(root, true); }
    }
}
