using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sora.DesktopShell;

public sealed record CoreDescriptor(int Version, string StateRoot, string CoreUrl, string TokenFile,
    Guid HostId, int HostPid, DateTimeOffset HostStartedUtc, string State, string? CoreInstanceId = null,
    Guid? ManagedSessionId = null, int? LauncherPid = null, DateTimeOffset? LauncherStartedUtc = null);

// A descriptor is an original-preserving discovery hint, never shutdown authority.
public sealed class CoreDescriptorStore
{
    private static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, WriteIndented = true,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, MaxDepth = 8 };
    private readonly string root;
    private readonly string path;
    private byte[]? fingerprint;
    public CoreDescriptor? Current { get; private set; }
    public string Error { get; private set; } = "";

    public CoreDescriptorStore(string stateRoot)
    {
        root = ShellProfile.CanonicalRoot(stateRoot);
        path = Path.Combine(root, "desktop-shell", "runtime.json");
        try
        {
            Guard();
            if (!File.Exists(path)) return;
            var bytes = ReadBounded();
            using var document = JsonDocument.Parse(bytes);
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || document.RootElement.EnumerateObject().Select(item => item.Name).Distinct().Count()
                    != document.RootElement.EnumerateObject().Count())
                throw new IOException("Ambiguous runtime descriptor.");
            Current = document.RootElement.Deserialize<CoreDescriptor>(Json)
                ?? throw new IOException("Missing runtime descriptor.");
            Validate(Current); fingerprint = bytes;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException
            or ArgumentException or InvalidOperationException)
        { Current = null; Error = "Runtime descriptor invalid/inaccessible; original preserved. No managed launch. " + error.GetType().Name; }
    }

    private void Guard()
    {
        ShellProfile.CanonicalRoot(Path.GetDirectoryName(path)!);
        if (File.Exists(path) && (new FileInfo(path).Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Linked runtime descriptor is not supported.");
    }
    private byte[] ReadBounded()
    {
        using var input = File.OpenRead(path); if (input.Length > 16384) throw new IOException("Runtime descriptor oversized.");
        var bytes = new byte[checked((int)input.Length)]; input.ReadExactly(bytes); return bytes;
    }
    private void Validate(CoreDescriptor value)
    {
        if (value.Version != 1 || value.HostId == Guid.Empty || value.HostPid <= 0
            || !string.Equals(ShellProfile.CanonicalRoot(value.StateRoot), root, StringComparison.OrdinalIgnoreCase)
            || value.State is not ("starting" or "owned" or "attached" or "failed" or "stopping" or "stopped")
            || value.CoreInstanceId is not null && !Guid.TryParse(value.CoreInstanceId, out _)
            || (value.LauncherPid is null) != (value.LauncherStartedUtc is null)
            || value.LauncherPid is <= 0)
            throw new IOException("Unsupported runtime descriptor.");
        ShellOptions.Parse(["--core-url", value.CoreUrl, "--token-file", value.TokenFile, "--state-root", root]);
    }
    public void Save(CoreDescriptor value)
    {
        if (Error.Length > 0) throw new IOException(Error);
        Validate(value); Guard();
        Directory.CreateDirectory(Path.GetDirectoryName(path)!); Guard();
        var lockPath = path + ".lock";
        if (File.Exists(lockPath) && (File.GetAttributes(lockPath) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Linked descriptor lock is not supported.");
        // Serialize cooperating writers across fingerprint validation and atomic
        // replacement. A contender fails visibly rather than overwriting hints.
        using var fileLock = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        if (File.Exists(path) ? fingerprint is null || !ReadBounded().AsSpan().SequenceEqual(fingerprint)
            : fingerprint is not null)
            throw new IOException("Runtime descriptor changed outside this host; no overwrite.");
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        var temporary = path + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { output.Write(bytes); output.Flush(true); }
            Guard(); File.Move(temporary, path, true); fingerprint = bytes; Current = value;
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    // null means the OS denied verification; it must not be treated as absence.
    public static bool? ProcessMatches(int pid, DateTimeOffset startedUtc)
    {
        try { using var process = Process.GetProcessById(pid);
            return !process.HasExited && process.StartTime.ToUniversalTime() == startedUtc.UtcDateTime; }
        catch (ArgumentException) { return false; }
        catch (InvalidOperationException) { return false; }
        catch (System.ComponentModel.Win32Exception) { return null; }
    }
}
