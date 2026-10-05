using System.Diagnostics;
using System.Text.Json;
using Sora.DesktopShell;

public sealed class CoreDescriptorTests
{
    private static string Root()
    {
        var root = Path.Combine(Path.GetTempPath(), "sora-descriptor-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root); return root;
    }
    private static CoreDescriptor Value(string root) => new(1, root, "http://127.0.0.1:18891",
        Path.Combine(root, "private", "token"), Guid.NewGuid(), Environment.ProcessId,
        new DateTimeOffset(Process.GetCurrentProcess().StartTime.ToUniversalTime()), "attached", Guid.NewGuid().ToString());

    [Fact]
    public void DescriptorLockContentionPreservesHintAndRetryRetainsFingerprint()
    {
        var root = Root();
        try
        {
            var store = new CoreDescriptorStore(root); var value = Value(root); store.Save(value);
            var path = Path.Combine(root, "desktop-shell", "runtime.json"); var original = File.ReadAllBytes(path);
            using (var held = new FileStream(path + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
            {
                Assert.Throws<IOException>(() => store.Save(value with { State = "stopped" }));
                Assert.Equal(original, File.ReadAllBytes(path)); Assert.Equal(value, store.Current);
            }
            store.Save(value with { State = "stopped" });
            Assert.Equal("stopped", new CoreDescriptorStore(root).Current!.State);
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public async Task RealLoopbackProbeDistinguishesOccupiedFromRefused()
    {
        var listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0);
        listener.Start();
        var endpoint = new Uri("http://127.0.0.1:" + ((System.Net.IPEndPoint)listener.LocalEndpoint).Port);
        try { Assert.Equal(ListenerState.Occupied, await ShellCoreCoordinator.ProbeAsync(endpoint, default)); }
        finally { listener.Stop(); }
        Assert.Equal(ListenerState.Absent, await ShellCoreCoordinator.ProbeAsync(endpoint, default));
    }

    [Fact]
    public void DescriptorIsReadableValidatedHintAndRejectsCompetingWrites()
    {
        var root = Root();
        try
        {
            var store = new CoreDescriptorStore(root); var value = Value(root);
            store.Save(value); var loaded = new CoreDescriptorStore(root);
            Assert.Equal(value, loaded.Current); Assert.Equal("", loaded.Error);
            var path = Path.Combine(root, "desktop-shell", "runtime.json");
            var original = File.ReadAllText(path); Assert.Contains("\n", original);
            Assert.DoesNotContain("credential", original); Assert.DoesNotContain("Bearer", original);
            File.WriteAllText(path, original + " ");
            Assert.Throws<IOException>(() => store.Save(value with { State = "stopped" }));
            Assert.Equal(original + " ", File.ReadAllText(path));
        }
        finally { Directory.Delete(root, true); }
    }

    [Theory]
    [InlineData("{\"version\":2}")]
    [InlineData("null")]
    [InlineData("[]")]
    [InlineData("{\"version\":1,\"version\":2}")]
    [InlineData("broken")]
    public void InvalidDescriptorIsPreservedAndNeverOverwritten(string text)
    {
        var root = Root();
        try
        {
            var folder = Path.Combine(root, "desktop-shell"); Directory.CreateDirectory(folder);
            var path = Path.Combine(folder, "runtime.json"); File.WriteAllText(path, text);
            var store = new CoreDescriptorStore(root);
            Assert.Null(store.Current); Assert.NotEmpty(store.Error);
            Assert.Throws<IOException>(() => store.Save(Value(root)));
            Assert.Equal(text, File.ReadAllText(path));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public void ProcessIdentityRequiresStartTimeAndDescriptorRequiresProfile()
    {
        using var process = Process.GetCurrentProcess();
        var started = new DateTimeOffset(process.StartTime.ToUniversalTime());
        Assert.True(CoreDescriptorStore.ProcessMatches(process.Id, started));
        Assert.False(CoreDescriptorStore.ProcessMatches(process.Id, started.AddSeconds(1)));
        Assert.False(CoreDescriptorStore.ProcessMatches(int.MaxValue, started));
        var root = Root();
        try
        {
            var store = new CoreDescriptorStore(root);
            Assert.Throws<IOException>(() => store.Save(Value(root) with { StateRoot = root + "-wrong" }));
            Assert.Throws<IOException>(() => store.Save(Value(root) with { LauncherPid = process.Id }));
            Assert.Throws<ArgumentException>(() => store.Save(Value(root) with { CoreUrl = "https://example.com" }));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public void FixedLaunchArgumentsPreserveTypedPathsWithoutEncodedCommands()
    {
        var root = Root();
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "scripts"));
            File.WriteAllText(Path.Combine(root, "scripts", "start-manual-test.ps1"), "# synthetic test marker");
            var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            var options = ShellOptions.Parse(["--core-url", "http://127.0.0.1:18891", "--token-file",
                Path.Combine(root, "private", "token"), "--state-root", root, "--managed-project-root", root,
                "--managed-powershell", shell, "--managed-settings", Path.Combine(root, "folder with ' quotes", "settings.json"),
                "--managed-model", "model with spaces", "--managed-provider", "deterministic",
                "--managed-no-avatar", "true", "--managed-setup-voice", "true", "--managed-discovery", "explicit",
                "--managed-codex-model", "codex model ' selection", "--managed-antigravity-model", "agent model",
                "--managed-antigravity-effort", "high", "--managed-antigravity-skip-permissions", "true",
                "--managed-unified-settings-only", "true"]);
            var start = options.Managed!.StartInfo(options);
            Assert.False(start.UseShellExecute); Assert.True(start.CreateNoWindow);
            Assert.Contains("-File", start.ArgumentList); Assert.DoesNotContain("-EncodedCommand", start.ArgumentList);
            Assert.Contains(options.Managed.Settings!, start.ArgumentList);
            Assert.Contains("model with spaces", start.ArgumentList); Assert.Contains("-NoAvatar", start.ArgumentList);
            Assert.Contains("-SetupVoice", start.ArgumentList); Assert.False(options.Managed.DiscoverEndpoint);
            Assert.Contains("codex model ' selection", start.ArgumentList); Assert.Contains("agent model", start.ArgumentList);
            Assert.Contains("-AntigravityEffort", start.ArgumentList); Assert.Contains("high", start.ArgumentList);
            Assert.Contains("-AntigravitySkipPermissions", start.ArgumentList);
            Assert.Contains("-UnifiedSettingsOnly", start.ArgumentList);
            Assert.False(start.Environment.ContainsKey("SORA_DESKTOP_HOST_CONTROL_TOKEN"));
        }
        finally { Directory.Delete(root, true); }
    }

    [Theory]
    [InlineData("--managed-antigravity-effort", "max")]
    [InlineData("--managed-codex-model", "bad\nmodel")]
    [InlineData("--managed-antigravity-model", "")]
    [InlineData("--managed-antigravity-skip-permissions", "yes")]
    public void UnsupportedSpecialistLaunchSelectionsFailBeforeStartup(string option, string value)
    {
        var root = Root();
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "scripts"));
            File.WriteAllText(Path.Combine(root, "scripts", "start-manual-test.ps1"), "# never executed");
            var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            Assert.Throws<ArgumentException>(() => ShellOptions.Parse(["--core-url", "http://127.0.0.1:18891",
                "--token-file", Path.Combine(root, "private", "token"), "--state-root", root,
                "--managed-project-root", root, "--managed-powershell", shell, option, value]));
            Assert.False(File.Exists(Path.Combine(root, "desktop-shell", "runtime.json")));
        }
        finally { Directory.Delete(root, true); }
    }
}
