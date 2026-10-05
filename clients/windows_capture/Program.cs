using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Sora.Embodiment.Native;

Native.SetProcessDpiAwarenessContext(new IntPtr(-4));
if (args.Length == 1 && args[0] == "--list-monitors")
{
    // Use exactly the same physical IDs, DPI, ordering and bounds as the avatar.
    // Otherwise each capture invalidates Unity's topology and races its report.
    var topology = WindowsDisplayTopology.Read();
    var monitors = topology.Monitors.Select(screen => new
    {
        id = screen.Id,
        primary = screen.Primary,
        rect = new Rect(screen.Rect.X, screen.Rect.Y, screen.Rect.Width, screen.Rect.Height),
        work_area = new Rect(screen.WorkArea.X, screen.WorkArea.Y,
            screen.WorkArea.Width, screen.WorkArea.Height),
        dpi_scale = screen.DpiScale,
        orientation = screen.Orientation,
    });
    var cursor = System.Windows.Forms.Cursor.Position;
    var cursorScreen = topology.FindMonitor(cursor.X, cursor.Y)
        ?? throw new InvalidOperationException("Cursor is not on an active display.");
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        monitors,
        cursor_monitor_id = cursorScreen.Id,
        cursor_x = cursor.X,
        cursor_y = cursor.Y,
    }));
    return;
}
Reply reply;
try
{
    var line = Console.ReadLine();
    if (line is null || line.Length > 8192) throw new ArgumentException();
    var request = JsonSerializer.Deserialize<Request>(line) ?? throw new ArgumentException();
    request.Validate();
    reply = Capture.Run(request);
}
catch (UnauthorizedAccessException) { reply = Reply.Error("access_denied"); }
catch (System.ComponentModel.Win32Exception) { reply = Reply.Error("access_denied"); }
catch (ArgumentException) { reply = Reply.Error("invalid_request"); }
catch (JsonException) { reply = Reply.Error("invalid_request"); }
catch (OutOfMemoryException) { reply = Reply.Error("too_large"); }
catch (Exception) { reply = Reply.Error("unavailable"); }
Console.WriteLine(JsonSerializer.Serialize(reply));

record Rect(int x, int y, int width, int height);
record Request(
    string schema_version,
    string capture_id,
    string source,
    Rect? region,
    int? process_id,
    long? window_handle,
    string? process_started_at,
    int max_pixels,
    int max_bytes)
{
    public void Validate()
    {
        if (schema_version != "1.0" || capture_id.Length is < 1 or > 128 ||
            source is not ("window" or "region") || max_pixels is < 1 or > 8_294_400 ||
            max_bytes is < 1 or > 16_777_216) throw new ArgumentException();
        if (source == "region")
        {
            if (region is null || process_id.HasValue || window_handle.HasValue ||
                process_started_at is not null) throw new ArgumentException();
            ValidateRect(region);
        }
        else if (region is not null || process_id is null or < 1 || window_handle is null or < 1 ||
                 process_started_at is null) throw new ArgumentException();
    }

    public void ValidateRect(Rect rect)
    {
        if (rect.width < 1 || rect.height < 1 ||
            (long)rect.width * rect.height > max_pixels ||
            Math.Abs((long)rect.x) > 1_000_000 || Math.Abs((long)rect.y) > 1_000_000)
            throw new ArgumentException();
    }
}

record Reply(
    string status,
    string? captured_at,
    Rect? region,
    int? process_id,
    long? window_handle,
    string? process_started_at,
    string png_base64)
{
    public static Reply Error(string status) => new(status, null, null, null, null, null, "");
}

static class Capture
{
    public static Reply Run(Request request)
    {
        if (request.source == "region") return CaptureRegion(request, request.region!);
        var process = GetProcess(request.process_id!.Value);
        using (process)
        {
            var started = process.StartTime.ToUniversalTime();
            var expected = DateTimeOffset.Parse(
                request.process_started_at!, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal).UtcDateTime;
            if (Math.Abs((started - expected).TotalMilliseconds) > 1)
                return Reply.Error("unavailable");
            if (Native.IsElevated(request.process_id.Value)) return Reply.Error("elevated_target");
            var hwnd = new IntPtr(request.window_handle!.Value);
            Native.GetWindowThreadProcessId(hwnd, out uint actualPid);
            if (actualPid != request.process_id.Value || !Native.IsWindow(hwnd) ||
                !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd) ||
                !Native.GetWindowRect(hwnd, out var nativeRect)) return Reply.Error("unavailable");
            var rect = new Rect(nativeRect.left, nativeRect.top,
                nativeRect.right - nativeRect.left, nativeRect.bottom - nativeRect.top);
            request.ValidateRect(rect);
            using var bitmap = NewBitmap(rect);
            using (var graphics = Graphics.FromImage(bitmap))
            {
                var hdc = graphics.GetHdc();
                try
                {
                    if (!Native.PrintWindow(hwnd, hdc, 2)) return Reply.Error("unavailable");
                }
                finally { graphics.ReleaseHdc(hdc); }
            }
            return Encode(request, bitmap, rect, request.process_id, request.window_handle,
                started.ToString("O"));
        }
    }

    static Reply CaptureRegion(Request request, Rect rect)
    {
        using var bitmap = NewBitmap(rect);
        using (var graphics = Graphics.FromImage(bitmap))
            graphics.CopyFromScreen(rect.x, rect.y, 0, 0, bitmap.Size, CopyPixelOperation.SourceCopy);
        return Encode(request, bitmap, rect, null, null, null);
    }

    static Bitmap NewBitmap(Rect rect) =>
        new(rect.width, rect.height, PixelFormat.Format32bppArgb);

    static Reply Encode(
        Request request,
        Bitmap bitmap,
        Rect rect,
        int? processId,
        long? windowHandle,
        string? processStartedAt)
    {
        using var stream = new MemoryStream();
        bitmap.Save(stream, ImageFormat.Png);
        if (stream.Length < 1 || stream.Length > request.max_bytes) return Reply.Error("too_large");
        return new Reply(
            "ok",
            DateTimeOffset.UtcNow.ToString("O"),
            rect,
            processId,
            windowHandle,
            processStartedAt,
            Convert.ToBase64String(stream.GetBuffer(), 0, checked((int)stream.Length)));
    }

    static Process GetProcess(int processId)
    {
        try { return Process.GetProcessById(processId); }
        catch (ArgumentException) { throw new InvalidOperationException(); }
    }
}

static class Native
{
    [StructLayout(LayoutKind.Sequential)] internal struct WinRect { public int left, top, right, bottom; }
    [DllImport("user32.dll")] internal static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr hwnd, out WinRect rect);
    [DllImport("user32.dll")] internal static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr token, int info, out int value, int length, out int returned);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    internal static bool IsElevated(int processId)
    {
        const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        const uint TOKEN_QUERY = 0x0008;
        var process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, processId);
        if (process == IntPtr.Zero) throw new UnauthorizedAccessException();
        try
        {
            if (!OpenProcessToken(process, TOKEN_QUERY, out var token)) throw new UnauthorizedAccessException();
            try
            {
                if (!GetTokenInformation(token, 20, out int value, 4, out _))
                    throw new UnauthorizedAccessException();
                return value != 0;
            }
            finally { CloseHandle(token); }
        }
        finally { CloseHandle(process); }
    }
}
