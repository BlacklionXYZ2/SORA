using System.Diagnostics;
using System.Net.Sockets;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

public enum ListenerState { Absent, Occupied, Unknown }

// Inject only boundary I/O for deterministic failure/recovery checks. Production
// defaults still authenticate identity and start the exact owned child.
internal sealed record ShellCoreOperations
{
    public Func<Uri, CancellationToken, Task<ListenerState>> Probe { get; init; } = ShellCoreCoordinator.ProbeAsync;
    public Func<int, DateTimeOffset, bool?> ProcessMatches { get; init; } = CoreDescriptorStore.ProcessMatches;
    public Func<ProcessStartInfo, OwnedCoreLaunch> Launch { get; init; } = OwnedCoreLaunch.Start;
    public Func<ShellOptions, OwnedCoreLaunch, ManagedCoreLifecycleClient> Control { get; init; }
        = (options, child) => new ManagedCoreLifecycleClient(options, child);
    public Func<ShellOptions, CancellationToken, Task<string>> Attach { get; init; } = async (options, token) => {
        using var api = new WidgetApiClient(options.CoreUrl, options.TokenFile, "device-local");
        var identity = await api.GetAsync("/api/v1/runtime/identity", token);
        return ShellProfile.ValidateIdentity(identity, options.StateRoot!);
    };
}

public sealed class ShellCoreCoordinator : IDisposable
{
    private readonly CoreDescriptorStore descriptors;
    private readonly ShellCoreOperations operations;
    private readonly Guid hostId = Guid.NewGuid();
    private readonly int hostPid = Environment.ProcessId;
    private readonly DateTimeOffset hostStarted = new(Process.GetCurrentProcess().StartTime.ToUniversalTime());
    private readonly object diagnosticLock = new();
    private CancellationTokenSource startup = new();
    private Task? initialization;
    private OwnedCoreLaunch? launch;
    private DateTime? launchedAt;
    private ManagedCoreLifecycleClient? control;
    private Task stdout = Task.CompletedTask, stderr = Task.CompletedTask;
    private string lastOutput = "";
    private bool shutdownIntent;
    private bool disposed;
    public ShellOptions Options { get; }
    public string Status { get; private set; }
    public string Phase { get; private set; } = "disconnected";
    public bool EffectsBlocked => Phase is "starting" or "stopping" or "failed";
    public bool HasOwnedLaunch => launch is not null;
    public event EventHandler? Changed;

    public ShellCoreCoordinator(ShellOptions options) : this(options, new ShellCoreOperations()) { }

    internal ShellCoreCoordinator(ShellOptions options, ShellCoreOperations operations)
    {
        this.operations = operations;
        descriptors = new CoreDescriptorStore(options.StateRoot!);
        Options = options;
        if (options.Managed?.DiscoverEndpoint == true && descriptors.Current is { } hint)
            Options = options with { CoreUrl = new Uri(hint.CoreUrl), TokenFile = hint.TokenFile };
        Status = options.Managed is null ? "Attached mode · external Core stays running on Quit."
            : "Managed profile · checking identity before launch; recovery remains available.";
    }

    public static async Task<ListenerState> ProbeAsync(Uri endpoint, CancellationToken token)
    {
        using var client = new TcpClient();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        // Windows can take just over two seconds to report a real loopback
        // refusal. A shorter deadline incorrectly classifies absence as unknown.
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        try { await client.ConnectAsync(endpoint.DnsSafeHost, endpoint.Port, timeout.Token); return ListenerState.Occupied; }
        catch (SocketException error) when (error.SocketErrorCode == SocketError.ConnectionRefused)
        { return ListenerState.Absent; }
        catch (Exception error) when (error is SocketException or OperationCanceledException)
        { token.ThrowIfCancellationRequested(); return ListenerState.Unknown; }
    }

    private void Set(string phase, string message)
    { Phase = phase; Status = message; Changed?.Invoke(this, EventArgs.Empty); }

    private void Record(string state, string? epoch = null)
    {
        // Preserve an orphaned launch hint when attaching after host loss; it is
        // never adopted, but must still prevent duplicate startup before API bind.
        var previous = descriptors.Current;
        descriptors.Save(new(1, Options.StateRoot!, Options.CoreUrl.ToString(), Options.TokenFile,
            hostId, hostPid, hostStarted, state, epoch ?? (state == "stopped" ? previous?.CoreInstanceId : null),
            launch?.SessionId ?? previous?.ManagedSessionId,
            launch?.Process.Id ?? previous?.LauncherPid,
            launch is not null ? new DateTimeOffset(launch.Process.StartTime.ToUniversalTime())
                : previous?.LauncherStartedUtc));
    }

    public Task StartOrAttachAsync()
    {
        if (disposed || shutdownIntent) return Task.CompletedTask;
        if (initialization?.IsCompleted == false) return initialization;
        startup.Dispose(); startup = new CancellationTokenSource();
        initialization = InitializeAsync(startup.Token); return initialization;
    }

    private async Task InitializeAsync(CancellationToken token)
    {
        try
        {
            if (Options.Managed is not null && descriptors.Error.Length > 0)
                throw new IOException(descriptors.Error);
            if (launch is not null && !launch.Process.HasExited)
            { await AwaitReadinessAsync(token); return; }
            Set("starting", "Checking saved profile and listener · no Core has been launched yet.");
            if (descriptors.Current is { } previous && new Uri(previous.CoreUrl) != Options.CoreUrl)
            {
                if (await operations.Probe(new Uri(previous.CoreUrl), token) != ListenerState.Absent)
                    throw new IOException("Saved profile endpoint is occupied/uncertain. Use its port; no second Core was started.");
            }
            var listener = await operations.Probe(Options.CoreUrl, token);
            token.ThrowIfCancellationRequested();
            if (listener == ListenerState.Occupied)
            {
                var epoch = await operations.Attach(Options, token);
                token.ThrowIfCancellationRequested();
                if (descriptors.Error.Length == 0) Record("attached", epoch);
                Set("attached", "Verified same-profile external Core · attached only; Quit leaves Core and tasks running.");
                return;
            }
            if (listener != ListenerState.Absent)
                throw new IOException("Listener absence could not be established; no managed launch.");
            if (Options.Managed is null)
            { Set("disconnected", "Attached Core unavailable · retry connection; this mode does not launch services."); return; }
            if (descriptors.Current is { LauncherPid: { } pid, LauncherStartedUtc: { } started }
                && operations.ProcessMatches(pid, started) != false)
                throw new IOException("Previous profile launcher is still running or unverifiable. No adoption/duplicate launch; recover the existing session.");
            if (launch is not null) { control?.Dispose(); control = null; launch.Dispose(); launch = null; }
            token.ThrowIfCancellationRequested();
            launchedAt = DateTime.Now;
            launch = operations.Launch(Options.Managed.StartInfo(Options));
            stdout = PumpAsync(launch.Process.StandardOutput, launch);
            stderr = PumpAsync(launch.Process.StandardError, launch);
            control = operations.Control(Options, launch);
            Record("starting");
            Set("starting", $"Owned Core launcher {launch.Process.Id} starting · panels/recovery available; no automatic restart.");
            await AwaitReadinessAsync(token);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception error)
        {
            string detail; lock (diagnosticLock) detail = lastOutput;
            Set("failed", "Startup/connection not confirmed. " + SafeError(error) +
                (detail.Length > 0 ? " · Last startup output: " + detail : "") +
                " · Retry is explicit; live services are not replaced or force-killed.");
        }
    }

    private async Task AwaitReadinessAsync(CancellationToken token, bool forShutdown = false)
    {
        using var readinessDeadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        readinessDeadline.CancelAfter(TimeSpan.FromSeconds(660));
        var waiting = readinessDeadline.Token;
        try
        {
            while (true)
            {
                waiting.ThrowIfCancellationRequested();
                if (launch!.Process.HasExited)
                {
                    if (forShutdown) return; // caller still verifies endpoint absence
                    throw new IOException($"Owned Core launcher exited during startup ({launch.Process.ExitCode}).");
                }
                if (await operations.Probe(Options.CoreUrl, waiting).WaitAsync(waiting) == ListenerState.Occupied)
                {
                    var ready = await control!.InspectAsync(waiting).WaitAsync(waiting);
                    waiting.ThrowIfCancellationRequested();
                    if (!ready.Owned) throw new IOException("Listening Core does not match the owned launch.");
                    Record("owned", ready.InstanceId);
                    Set(forShutdown ? "stopping" : "owned", forShutdown
                        ? "Owned Core ready for pending Quit · awaiting graceful cleanup; effects remain blocked."
                        : "Owned Core connected · model readiness is separate; Quit awaits owned Core/voice/avatar cleanup.");
                    return;
                }
                await Task.Delay(500, waiting);
            }
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        { throw new TimeoutException("Core readiness exceeded eleven minutes. The owned launcher may still be alive; no duplicate restart."); }
    }

    private async Task PumpAsync(StreamReader reader, OwnedCoreLaunch owner)
    {
        // Bounded chunk/line retention, no raw log file or credential persistence.
        var buffer = new char[512]; var line = new System.Text.StringBuilder(600);
        try
        {
            int count;
            while ((count = await reader.ReadAsync(buffer)) > 0)
                for (var index = 0; index < count; index++)
                    if (buffer[index] is '\r' or '\n')
                    {
                        if (line.Length == 0) continue;
                        var clean = owner.Redact(line.ToString());
                        lock (diagnosticLock) lastOutput = clean;
                        line.Clear();
                    }
                    else if (!char.IsControl(buffer[index]) && line.Length < 600) line.Append(buffer[index]);
            if (line.Length > 0) lock (diagnosticLock) lastOutput = owner.Redact(line.ToString());
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException) { }
    }

    private static string SafeError(Exception error) => error is IOException or TimeoutException
        or InvalidOperationException or ArgumentException ? error.Message : error.GetType().Name;

    public void CheckChild()
    {
        if (Phase == "owned" && launch?.Process.HasExited == true)
            Set("failed", $"Owned launcher exited ({launch.Process.ExitCode}); connection may be stale. Explicit Retry only; no automatic restart.");
    }

    public async Task<bool> QuitAsync(CancellationToken token, TimeSpan? timeout = null)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(timeout ?? TimeSpan.FromSeconds(30));
        shutdownIntent = true; startup.Cancel();
        Set("stopping", "Quit requested · awaiting initialization and exact owned exit; ACK alone is not completion.");
        try
        {
            // Cancellation of startup is not completion. Bound the whole Quit,
            // including unresponsive initialization, before inspecting ownership.
            if (initialization is not null) await initialization.WaitAsync(deadline.Token);
            deadline.Token.ThrowIfCancellationRequested();
            if (launch is null) return true; // Never stop an external Core.
            if (!launch.Process.HasExited)
            {
                Set("stopping", "Quit pending · waiting for the owned Core API within the Quit deadline; host effects remain blocked.");
                await AwaitReadinessAsync(deadline.Token, forShutdown: true);
                if (!launch.Process.HasExited) await control!.RequestShutdownAsync(deadline.Token);
                await launch.Process.WaitForExitAsync(deadline.Token);
            }
            if (await operations.Probe(Options.CoreUrl, deadline.Token) != ListenerState.Absent)
                throw new IOException("Owned launcher exited, but listener absence is not established.");
            await Task.WhenAll(stdout, stderr).WaitAsync(deadline.Token);
            Record("stopped"); Set("stopped", "Owned launcher exited and listener is absent; graceful cleanup confirmed.");
            return true;
        }
        catch (Exception error)
        {
            shutdownIntent = false;
            Set("failed", "Quit cleanup not confirmed. " + SafeError(error) +
                " · Host/recovery retained. No force kill or duplicate launch. Retry Quit after startup/cleanup settles.");
            return false;
        }
    }

    // The owner's Quit closes every part this host launched, after Core's own graceful shutdown
    // has had its chance: the recorded helpers (llama.cpp, Laya, avatar, voice, Core) and the
    // launcher's process tree. An attached external Core is never touched.
    public IReadOnlyList<string> CloseEverything()
    {
        if (launch is null || launchedAt is null || Options.StateRoot is null) return [];
        var stopped = HelperCleanup.StopAll(Options.StateRoot, launchedAt.Value).ToList();
        try
        {
            if (!launch.Process.HasExited) { launch.Process.Kill(entireProcessTree: true); stopped.Add("launcher"); }
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception) { }
        if (stopped.Count > 0) { Record("stopped"); Set("stopped", "Quit closed: " + string.Join(", ", stopped) + "."); }
        return stopped;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true; startup.Cancel(); startup.Dispose(); control?.Dispose(); launch?.Dispose();
        // Disposing handles never terminates a service. Normal host Quit awaits
        // cleanup above; OS/process loss leaves a descriptor hint, not adoption.
    }
}
