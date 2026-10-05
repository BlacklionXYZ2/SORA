using System.Buffers.Binary;
using System.IO.Pipes;
using System.Text.Json;

namespace Sora.DesktopShell;

public sealed record HostCommand(int Version, string Profile, string Panel)
{
    public bool Valid(string expected) => Version == 1 && Profile == expected
        && Panel is "chat" or "voice" or "memory" or "activity" or "agents" or "paths" or "board" or "content" or "integrations" or "settings" or "appearance" or "menu" or "none" or "quit";
}

// Current-user pipe + profile mutex. No executable arguments, URLs, credentials or arbitrary effects.
public sealed class ShellInstance : IDisposable
{
    private readonly Mutex mutex;
    private readonly string pipeName;
    private bool disposed;
    public string ProfileKey { get; }
    public bool Primary { get; }
    public ShellInstance(string key)
    {
        if (key.Length != 64 || !key.All(Uri.IsHexDigit)) throw new ArgumentException("Invalid profile key.");
        ProfileKey = key; pipeName = "sora-shell-v1-" + key;
        mutex = new Mutex(false, "Local\\" + pipeName);
        try { Primary = mutex.WaitOne(0); }
        catch (AbandonedMutexException) { Primary = true; }
    }
    public async Task<bool> SummonAsync(string panel, CancellationToken cancellationToken)
    {
        var command = new HostCommand(1, ProfileKey, panel);
        if (!command.Valid(ProfileKey)) throw new ArgumentException("Unsupported host command.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(4));
        await using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut,
            PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        await pipe.ConnectAsync(deadline.Token);
        await WriteAsync(pipe, JsonSerializer.SerializeToUtf8Bytes(command), deadline.Token);
        return JsonSerializer.Deserialize<bool>(await ReadAsync(pipe, deadline.Token));
    }
    public async Task ServeAsync(Func<HostCommand, Task<bool>> dispatch, CancellationToken cancellationToken)
    {
        if (!Primary) throw new InvalidOperationException("Only the primary host can serve.");
        while (!cancellationToken.IsCancellationRequested)
        {
            await using var pipe = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
            try
            {
                await pipe.WaitForConnectionAsync(cancellationToken);
                using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                deadline.CancelAfter(TimeSpan.FromSeconds(3));
                var command = JsonSerializer.Deserialize<HostCommand>(await ReadAsync(pipe, deadline.Token));
                var accepted = command is not null && command.Valid(ProfileKey) && await dispatch(command);
                await WriteAsync(pipe, JsonSerializer.SerializeToUtf8Bytes(accepted), deadline.Token);
            }
            catch (Exception error) when (error is IOException or JsonException or OperationCanceledException or InvalidDataException)
            { if (cancellationToken.IsCancellationRequested) break; }
        }
    }
    private static async Task<byte[]> ReadAsync(Stream pipe, CancellationToken token)
    {
        var header = new byte[4]; await pipe.ReadExactlyAsync(header, token);
        var length = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (length is < 1 or > 2048) throw new InvalidDataException("Host command too large.");
        var payload = new byte[length]; await pipe.ReadExactlyAsync(payload, token); return payload;
    }
    private static async Task WriteAsync(Stream pipe, byte[] payload, CancellationToken token)
    {
        var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, payload.Length);
        await pipe.WriteAsync(header, token); await pipe.WriteAsync(payload, token); await pipe.FlushAsync(token);
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        if (Primary) mutex.ReleaseMutex(); // Always dispose on the constructing UI thread.
        mutex.Dispose();
    }
}
