using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using Sora.DesktopShell;

public sealed class ShellCoreCoordinatorTests
{
    private sealed class StartupControlHandler(string root, OwnedCoreLaunch child) : HttpMessageHandler
    {
        public string Epoch = Guid.NewGuid().ToString();
        public bool WrongSession;
        public int ShutdownCalls;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var path = request.RequestUri!.AbsolutePath;
            var session = WrongSession ? Guid.NewGuid() : child.SessionId;
            Guid? requestId = null;
            if (request.Content is not null)
            {
                using var body = JsonDocument.Parse(await request.Content.ReadAsStringAsync(token));
                requestId = body.RootElement.GetProperty("request_id").GetGuid();
                Assert.Equal(child.SessionId, body.RootElement.GetProperty("managed_session_id").GetGuid());
                Assert.True(request.Headers.Contains("X-SORA-Host-Control"));
                ShutdownCalls++;
                await child.Process.StandardInput.WriteLineAsync(); // effect-free fixture exits normally
                child.Process.StandardInput.Close();
            }
            object response = path == "/api/v1/runtime/identity"
                ? new { version = 1, instance_id = Epoch, state_root = root }
                : new { version = 1, instance_id = Epoch, managed_session_id = session,
                    state = requestId is null ? "managed" : "shutdown_requested", shutdown_request_id = requestId };
            return new HttpResponseMessage(requestId is null ? HttpStatusCode.OK : HttpStatusCode.Accepted) {
                Content = new StringContent(JsonSerializer.Serialize(response), Encoding.UTF8, "application/json") };
        }
    }

    private static OwnedCoreLaunch EffectFreeChild()
    {
        var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe")) {
            UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "-NoProfile", "-NonInteractive", "-Command", "[Console]::ReadLine() | Out-Null" })
            start.ArgumentList.Add(argument);
        return OwnedCoreLaunch.Start(start);
    }

    private static async Task FinishChild(OwnedCoreLaunch? child)
    {
        if (child is null || child.Process.HasExited) return;
        await child.Process.StandardInput.WriteLineAsync(); child.Process.StandardInput.Close();
        await child.Process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(0, child.Process.ExitCode);
    }
    private sealed class Fixture : IDisposable
    {
        public string Root { get; } = Path.Combine(Path.GetTempPath(), "sora-coordinator-" + Guid.NewGuid().ToString("N"));
        public ShellOptions Options { get; }
        public int Launches, Attaches, Probes;
        public Fixture()
        {
            Directory.CreateDirectory(Path.Combine(Root, "scripts"));
            File.WriteAllText(Path.Combine(Root, "scripts", "start-manual-test.ps1"), "# fixture; never executed");
            var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            Options = ShellOptions.Parse(["--core-url", "http://127.0.0.1:18892", "--token-file",
                Path.Combine(Root, "private", "token"), "--state-root", Root, "--managed-project-root", Root,
                "--managed-powershell", shell, "--managed-no-avatar", "true"]);
        }
        public ShellCoreOperations Operations(ListenerState listener = ListenerState.Absent) => new() {
            Probe = (_, _) => { Probes++; return Task.FromResult(listener); },
            Attach = (_, _) => { Attaches++; return Task.FromResult(Guid.NewGuid().ToString()); },
            Launch = _ => { Launches++; throw new IOException("Synthetic launcher failure; no process started."); }
        };
        public void Hint(Uri? endpoint = null)
        {
            using var process = Process.GetCurrentProcess();
            var started = new DateTimeOffset(process.StartTime.ToUniversalTime());
            new CoreDescriptorStore(Root).Save(new(1, Root, (endpoint ?? Options.CoreUrl).ToString(),
                Options.TokenFile, Guid.NewGuid(), process.Id, started, "starting", null,
                Guid.NewGuid(), process.Id, started));
        }
        public void Dispose() => Directory.Delete(Root, true);
    }

    [Fact]
    public async Task UnknownListenerNeverAttachesOrLaunchesAndQuitLeavesItAlone()
    {
        using var fixture = new Fixture();
        using var core = new ShellCoreCoordinator(fixture.Options, fixture.Operations(ListenerState.Unknown));
        await core.StartOrAttachAsync();
        Assert.Equal("failed", core.Phase); Assert.True(core.EffectsBlocked);
        Assert.Equal(0, fixture.Launches); Assert.Equal(0, fixture.Attaches);
        Assert.True(await core.QuitAsync(default)); Assert.False(core.HasOwnedLaunch);
    }

    [Fact]
    public async Task VerifiedListenerAttachesWithoutAdoptingHintOwnership()
    {
        using var fixture = new Fixture(); fixture.Hint();
        using var core = new ShellCoreCoordinator(fixture.Options, fixture.Operations(ListenerState.Occupied));
        await core.StartOrAttachAsync();
        Assert.Equal("attached", core.Phase); Assert.False(core.EffectsBlocked);
        Assert.False(core.HasOwnedLaunch); Assert.Equal(0, fixture.Launches); Assert.Equal(1, fixture.Attaches);
        Assert.True(await core.QuitAsync(default)); Assert.Equal(0, fixture.Launches);
        Assert.Equal("attached", new CoreDescriptorStore(fixture.Root).Current!.State);
    }

    [Fact]
    public async Task MismatchedIdentityIsFailureNotPermissionToPickAnotherPort()
    {
        using var fixture = new Fixture();
        var operations = fixture.Operations(ListenerState.Occupied) with {
            Attach = (_, _) => throw new InvalidOperationException("Synthetic mismatched profile") };
        using var core = new ShellCoreCoordinator(fixture.Options, operations);
        await core.StartOrAttachAsync(); Assert.Equal("failed", core.Phase);
        Assert.Equal(0, fixture.Launches); Assert.False(core.HasOwnedLaunch);
        Assert.False(File.Exists(Path.Combine(fixture.Root, "desktop-shell", "runtime.json")));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(null)]
    [InlineData(false)]
    public async Task PreviousLauncherMustBePositivelyAbsentBeforeReplacement(bool? matches)
    {
        using var fixture = new Fixture(); fixture.Hint();
        var original = File.ReadAllBytes(Path.Combine(fixture.Root, "desktop-shell", "runtime.json"));
        using var core = new ShellCoreCoordinator(fixture.Options,
            fixture.Operations() with { ProcessMatches = (_, _) => matches });
        await core.StartOrAttachAsync(); Assert.Equal("failed", core.Phase);
        // false permits the one synthetic start attempt; true/null refuse it.
        Assert.Equal(matches == false ? 1 : 0, fixture.Launches);
        Assert.Equal(original, File.ReadAllBytes(Path.Combine(fixture.Root, "desktop-shell", "runtime.json")));
    }

    [Fact]
    public async Task ExplicitDifferentEndpointCannotBypassOccupiedSavedEndpoint()
    {
        using var fixture = new Fixture(); fixture.Hint(new Uri("http://127.0.0.1:18893"));
        var options = fixture.Options with { Managed = fixture.Options.Managed! with { DiscoverEndpoint = false } };
        using var core = new ShellCoreCoordinator(options, fixture.Operations(ListenerState.Occupied));
        await core.StartOrAttachAsync(); Assert.Equal("failed", core.Phase);
        Assert.Equal(1, fixture.Probes); Assert.Equal(0, fixture.Attaches); Assert.Equal(0, fixture.Launches);
    }

    [Fact]
    public async Task InvalidHintIsPreservedWithoutAnyListenerOrLaunchOperation()
    {
        using var fixture = new Fixture();
        var path = Path.Combine(fixture.Root, "desktop-shell", "runtime.json");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, "broken original");
        using var core = new ShellCoreCoordinator(fixture.Options, fixture.Operations());
        await core.StartOrAttachAsync(); Assert.Equal("failed", core.Phase);
        Assert.Equal(0, fixture.Probes); Assert.Equal(0, fixture.Launches);
        Assert.Equal("broken original", File.ReadAllText(path));
    }

    [Fact]
    public async Task QuitDeadlineCoversUnresponsiveInitializationAndDoesNotPermitLateLaunch()
    {
        using var fixture = new Fixture();
        var blockedProbe = new TaskCompletionSource<ListenerState>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var core = new ShellCoreCoordinator(fixture.Options,
            fixture.Operations() with { Probe = (_, _) => blockedProbe.Task });
        var starting = core.StartOrAttachAsync();
        Assert.Same(starting, core.StartOrAttachAsync());
        try
        {
            var quit = core.QuitAsync(default, TimeSpan.FromMilliseconds(50));
            Assert.False(await quit.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Equal("failed", core.Phase); Assert.True(core.EffectsBlocked);
            Assert.Contains("Host/recovery retained", core.Status); Assert.Equal(0, fixture.Launches);
            Assert.Same(starting, core.StartOrAttachAsync()); // still no duplicate while original I/O hangs
        }
        finally { blockedProbe.TrySetResult(ListenerState.Absent); await starting; }
        Assert.Equal(0, fixture.Launches); // canceled initialization cannot start a late child
        Assert.True(await core.QuitAsync(default));
    }

    [Fact]
    public async Task CanceledQuitCannotReportSuccessOrLateAttachment()
    {
        using var fixture = new Fixture();
        var blockedAttach = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var core = new ShellCoreCoordinator(fixture.Options, fixture.Operations(ListenerState.Occupied)
            with { Attach = (_, _) => blockedAttach.Task });
        var starting = core.StartOrAttachAsync();
        using var canceled = new CancellationTokenSource(); canceled.Cancel();
        try { Assert.False(await core.QuitAsync(canceled.Token)); }
        finally { blockedAttach.SetResult(Guid.NewGuid().ToString()); await starting; }
        Assert.Equal("failed", core.Phase); Assert.Equal(0, fixture.Launches);
        Assert.False(File.Exists(Path.Combine(fixture.Root, "desktop-shell", "runtime.json")));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PendingStartupQuitWaitsForExactOwnershipAndNeverAdoptsAnotherSession(bool wrongSession)
    {
        using var fixture = new Fixture();
        Directory.CreateDirectory(Path.GetDirectoryName(fixture.Options.TokenFile)!);
        File.WriteAllText(fixture.Options.TokenFile, "synthetic-api-token-123456789");
        OwnedCoreLaunch? child = null; StartupControlHandler? handler = null;
        var quitting = false; var apiReady = false;
        var operations = fixture.Operations() with {
            Launch = _ => child = EffectFreeChild(),
            Control = (options, launch) => {
                handler = new StartupControlHandler(fixture.Root, launch) { WrongSession = wrongSession };
                return new ManagedCoreLifecycleClient(options, launch, handler);
            },
            Probe = async (_, token) => {
                if (child is null || child.Process.HasExited) return ListenerState.Absent;
                if (!quitting) await Task.Delay(Timeout.Infinite, token); // initial startup waiting for API
                return apiReady ? ListenerState.Occupied : ListenerState.Absent;
            }
        };
        using var core = new ShellCoreCoordinator(fixture.Options, operations);
        var starting = core.StartOrAttachAsync();
        try
        {
            Assert.True(core.HasOwnedLaunch); Assert.Equal("starting", core.Phase);
            quitting = true;
            var quit = core.QuitAsync(default, TimeSpan.FromSeconds(10));
            await starting; Assert.False(quit.IsCompleted); Assert.True(core.EffectsBlocked);
            apiReady = true;
            Assert.Equal(!wrongSession, await quit.WaitAsync(TimeSpan.FromSeconds(15)));
            Assert.Equal(wrongSession ? 0 : 1, handler!.ShutdownCalls);
            if (wrongSession)
            { Assert.Equal("failed", core.Phase); Assert.True(child!.Process.HasExited == false); }
            else
            {
                Assert.Equal("stopped", core.Phase); Assert.Equal(0, child!.Process.ExitCode);
                Assert.Equal(handler.Epoch, new CoreDescriptorStore(fixture.Root).Current!.CoreInstanceId);
            }
        }
        finally { await FinishChild(child); await starting; }
    }

    [Fact]
    public async Task PendingStartupQuitTimesOutWithoutKillingChildAndCanRetryAfterExit()
    {
        using var fixture = new Fixture(); OwnedCoreLaunch? child = null; var quitting = false;
        var operations = fixture.Operations() with {
            Launch = _ => child = EffectFreeChild(),
            Probe = async (_, token) => {
                if (child is null || child.Process.HasExited) return ListenerState.Absent;
                if (!quitting) await Task.Delay(Timeout.Infinite, token);
                return ListenerState.Absent;
            }
        };
        using var core = new ShellCoreCoordinator(fixture.Options, operations);
        var starting = core.StartOrAttachAsync();
        try
        {
            quitting = true;
            Assert.False(await core.QuitAsync(default, TimeSpan.FromMilliseconds(100)).WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Equal("failed", core.Phase); Assert.True(core.HasOwnedLaunch); Assert.False(child!.Process.HasExited);
            Assert.Contains("Host/recovery retained", core.Status);
            Assert.Equal("starting", new CoreDescriptorStore(fixture.Root).Current!.State);
            await FinishChild(child);
            Assert.True(await core.QuitAsync(default)); Assert.Equal("stopped", core.Phase);
        }
        finally { await FinishChild(child); await starting; }
    }
}
