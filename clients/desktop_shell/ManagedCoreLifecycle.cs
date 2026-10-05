using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Sora.DesktopShell;

// Authority exists only after this host successfully starts this exact process.
// It is not reconstructed from a descriptor, a PID, API projection or UI JSON.
public sealed class OwnedCoreLaunch : IDisposable
{
    private readonly string credential;
    private string? coreInstance;
    private bool revoked;
    public Guid SessionId { get; } = Guid.NewGuid();
    public Process Process { get; }
    public bool IsRunning => !revoked && !Process.HasExited;

    private OwnedCoreLaunch(ProcessStartInfo startInfo)
    {
        if (startInfo.UseShellExecute)
            throw new ArgumentException("Managed Core requires an explicit child environment.");
        credential = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
            .TrimEnd('=').Replace('+', '-').Replace('/', '_');
        startInfo.Environment["SORA_DESKTOP_HOST_SESSION"] = SessionId.ToString();
        startInfo.Environment["SORA_DESKTOP_HOST_CONTROL_TOKEN"] = credential;
        Process = new Process { StartInfo = startInfo };
        try
        {
            if (!Process.Start()) throw new IOException("Managed Core process did not start.");
        }
        catch { Process.Dispose(); throw; }
        finally
        {
            // Retained launch arguments/settings and any subsequent launch must
            // not inherit the credential from this mutable StartInfo object.
            startInfo.Environment.Remove("SORA_DESKTOP_HOST_SESSION");
            startInfo.Environment.Remove("SORA_DESKTOP_HOST_CONTROL_TOKEN");
        }
    }

    public static OwnedCoreLaunch Start(ProcessStartInfo startInfo) => new(startInfo);

    internal bool Verify(string instance, Guid? session)
    {
        if (!IsRunning) return false;
        if (session != SessionId || (coreInstance is not null && coreInstance != instance))
        {
            revoked = true; // Never adopt a replacement runtime or launch epoch.
            return false;
        }
        coreInstance ??= instance;
        return true;
    }

    internal void Authorize(HttpRequestMessage request) =>
        request.Headers.Add("X-SORA-Host-Control", credential);

    internal string Redact(string text) => text.Replace(credential, "[launch credential redacted]",
        StringComparison.Ordinal);

    // Disposing a handle is not a kill/stop. Failed shutdown retains the service;
    // the coordinator must report it and must not launch another one blindly.
    public void Dispose() => Process.Dispose();
}

public sealed record CoreLifecycleSnapshot(string InstanceId, Guid? SessionId, string State,
    Guid? ShutdownRequestId, bool Owned);

public sealed class ManagedCoreLifecycleClient : IDisposable
{
    private readonly ShellOptions options;
    private readonly OwnedCoreLaunch? launch;
    private readonly HttpClient client;
    private readonly Guid shutdownRequest = Guid.NewGuid();

    public ManagedCoreLifecycleClient(ShellOptions options, OwnedCoreLaunch? launch = null,
        HttpMessageHandler? handler = null)
    {
        if (!options.Hosted) throw new ArgumentException("Lifecycle requires an explicit profile.");
        // Validate even options created directly rather than through CLI parsing.
        this.options = ShellOptions.Parse(["--core-url", options.CoreUrl.ToString(),
            "--token-file", options.TokenFile, "--state-root", options.StateRoot!, "--show", "none"]);
        this.launch = launch;
        client = handler is null ? new HttpClient() : new HttpClient(handler);
        client.BaseAddress = this.options.CoreUrl;
        client.Timeout = TimeSpan.FromSeconds(5);
    }

    private async Task<JsonElement> RequestAsync(string path, string? instance, object? body,
        bool control, CancellationToken token)
    {
        var info = new FileInfo(options.TokenFile);
        if (!info.Exists || info.Length is < 16 or > 4096
            || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Profile API token is missing or invalid.");
        var apiToken = (await File.ReadAllTextAsync(options.TokenFile, token)).Trim();
        if (apiToken.Length is < 16 or > 4096 || apiToken.Any(char.IsControl))
            throw new IOException("Profile API token is invalid.");
        using var request = new HttpRequestMessage(body is null ? HttpMethod.Get : HttpMethod.Post, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
        if (instance is not null) request.Headers.Add("X-SORA-Core-Instance", instance);
        if (control) launch!.Authorize(request);
        // Core intentionally accepts bounded Content-Length bodies, not HTTP
        // chunked transfer. JsonContent streams chunked on the real transport.
        if (body is not null) request.Content = new StringContent(JsonSerializer.Serialize(body),
            Encoding.UTF8, "application/json");
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        if (response.StatusCode != (body is null ? HttpStatusCode.OK : HttpStatusCode.Accepted))
            // Do not echo server bodies, request headers, credentials or paths.
            throw new IOException($"Core lifecycle request rejected ({(int)response.StatusCode}).");
        await using var stream = await response.Content.ReadAsStreamAsync(token);
        var buffer = new byte[4097]; var total = 0;
        while (total < buffer.Length)
        {
            var count = await stream.ReadAsync(buffer.AsMemory(total), token);
            if (count == 0) break;
            total += count;
        }
        if (total == buffer.Length) throw new IOException("Core lifecycle projection is too large.");
        using var document = JsonDocument.Parse(buffer.AsMemory(0, total), new JsonDocumentOptions { MaxDepth = 8 });
        return document.RootElement.Clone();
    }

    private static CoreLifecycleSnapshot Parse(JsonElement value, string instance, bool owned)
    {
        if (value.GetProperty("version").GetInt32() != 1
            || value.GetProperty("instance_id").GetString() != instance)
            throw new IOException("Core lifecycle instance changed; ownership is not transferable.");
        Guid? ReadGuid(string key) => value.GetProperty(key).ValueKind == JsonValueKind.Null ? null
            : Guid.Parse(value.GetProperty(key).GetString()!);
        var state = value.GetProperty("state").GetString();
        var session = ReadGuid("managed_session_id"); var request = ReadGuid("shutdown_request_id");
        if (state is not ("external" or "managed" or "shutdown_requested")
            || (state == "external") != (session is null)
            || (state == "shutdown_requested") != (request is not null))
            throw new IOException("Unsupported Core lifecycle state.");
        return new(instance, session, state, request, owned);
    }

    public async Task<CoreLifecycleSnapshot> InspectAsync(CancellationToken token)
    {
        var identity = await RequestAsync("/api/v1/runtime/identity", null, null, false, token);
        var epoch = ShellProfile.ValidateIdentity(identity, options.StateRoot!);
        var projection = await RequestAsync("/api/v1/runtime/lifecycle", epoch, null, false, token);
        var snapshot = Parse(projection, epoch, false);
        return snapshot with { Owned = launch?.Verify(epoch, snapshot.SessionId) == true };
    }

    // This returns an acknowledgement, not process/worker shutdown completion.
    // The host must await the exact owned child and verify absence separately.
    public async Task<CoreLifecycleSnapshot> RequestShutdownAsync(CancellationToken token)
    {
        if (launch is null) throw new InvalidOperationException("Attached external Core stays running.");
        var current = await InspectAsync(token);
        if (!current.Owned) throw new InvalidOperationException("Core launch ownership could not be verified.");
        var result = await RequestAsync("/api/v1/runtime/shutdown", current.InstanceId,
            new { version = 1, managed_session_id = launch.SessionId, request_id = shutdownRequest }, true, token);
        var acknowledgement = Parse(result, current.InstanceId, true);
        if (acknowledgement.SessionId != launch.SessionId
            || acknowledgement.State != "shutdown_requested"
            || acknowledgement.ShutdownRequestId != shutdownRequest)
            throw new IOException("Core shutdown acknowledgement does not match this launch/request.");
        return acknowledgement;
    }

    public void Dispose() => client.Dispose();
}
