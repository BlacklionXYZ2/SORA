using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows.Automation;

Native.SetProcessDpiAwarenessContext(new IntPtr(-4));
bool effectAttempted = false;
object result;
try
{
    var line = Console.ReadLine();
    if (line is null || line.Length > 16384) throw new ArgumentException();
    var request = JsonSerializer.Deserialize<Request>(line) ?? throw new ArgumentException();
    if (!request.Valid()) throw new ArgumentException();
    Process process;
    try { process = Process.GetProcessById(request.process_id); }
    catch (ArgumentException) { Console.WriteLine(JsonSerializer.Serialize(Reply.Error("unavailable"))); return; }
    using var ownedProcessHandle = process;
    var expectedStart = DateTimeOffset.Parse(request.process_started_at).UtcDateTime;
    if (Math.Abs((process.StartTime.ToUniversalTime() - expectedStart).TotalMilliseconds) >= 1)
        result = Reply.Error("unavailable");
    else if (Native.IsElevated(request.process_id)) result = Reply.Error("elevated_target");
    else result = Actor.Type(request, ref effectAttempted);
}
catch (UnauthorizedAccessException) { result = Reply.Error("access_denied", effectAttempted); }
catch (System.ComponentModel.Win32Exception) { result = Reply.Error("access_denied", effectAttempted); }
catch (ElementNotAvailableException) { result = Reply.Error(effectAttempted ? "unknown_outcome" : "unavailable", effectAttempted); }
catch (ArgumentException) { result = Reply.Error(effectAttempted ? "unknown_outcome" : "invalid_request", effectAttempted); }
catch (JsonException) { result = Reply.Error("invalid_request"); }
catch (Exception) { result = Reply.Error(effectAttempted ? "unknown_outcome" : "unavailable", effectAttempted); }
Console.WriteLine(JsonSerializer.Serialize(result));

record Request(string schema_version, string operation, int process_id, string process_started_at,
    long root_window_handle, long native_window_handle, int[] runtime_id, string automation_id,
    string control_type, int expected_x, int expected_y, int expected_width, int expected_height,
    string expected_name_before, string text)
{
    public bool Valid() => schema_version == "1.0" && operation == "type" && process_id > 0 &&
        root_window_handle > 0 && native_window_handle >= 0 && runtime_id is { Length: <= 32 } &&
        runtime_id.All(value => value >= 0) && automation_id is { Length: <= 256 } &&
        control_type is { Length: > 0 and <= 128 } && expected_width > 0 && expected_height > 0 &&
        expected_name_before is { Length: <= 256 } && text is { Length: > 0 and <= 4096 } &&
        (runtime_id.Length > 0 || native_window_handle > 0 || automation_id.Length > 0) &&
        DateTimeOffset.TryParse(process_started_at, out _);
}
record Reply(string status, bool effect_attempted, bool verified)
{
    public static Reply Error(string status, bool attempted = false) => new(status, attempted, false);
}

static class Actor
{
    public static Reply Type(Request request, ref bool effectAttempted)
    {
        var rootHandle = new IntPtr(request.root_window_handle);
        Native.GetWindowThreadProcessId(rootHandle, out uint actualPid);
        if (actualPid != request.process_id || !Native.IsWindow(rootHandle))
            return Reply.Error("unavailable");
        if (Native.SendMessageTimeout(rootHandle, 0, IntPtr.Zero, IntPtr.Zero, 2, 200, out _) == IntPtr.Zero)
            return Reply.Error("timeout");
        var root = AutomationElement.FromHandle(rootHandle);
        var matches = new List<AutomationElement>();
        var walker = TreeWalker.ControlViewWalker;
        int visited = 0;
        bool truncated = false;
        void Visit(AutomationElement element, int depth)
        {
            if (matches.Count > 1 || depth > 12) return;
            if (++visited > 512) { truncated = true; return; }
            var current = element.Current;
            if (current.ProcessId != request.process_id) return;
            if (Matches(element, current, request)) matches.Add(element);
            if (depth == 12) return;
            for (var child = walker.GetFirstChild(element); child is not null; child = walker.GetNextSibling(child))
            {
                Visit(child, depth + 1);
                if (matches.Count > 1 || truncated) return;
            }
        }
        Visit(root, 0);
        if (truncated || matches.Count == 0) return Reply.Error("unavailable");
        if (matches.Count != 1) return Reply.Error("ambiguous");
        var target = matches[0];
        var before = target.Current;
        if (!before.IsEnabled || before.IsOffscreen || before.IsPassword ||
            before.Name != request.expected_name_before) return Reply.Error("unavailable");
        var bounds = before.BoundingRectangle;
        if (!double.IsFinite(bounds.X + bounds.Y + bounds.Width + bounds.Height) ||
            bounds.Width <= 0 || bounds.Height <= 0) return Reply.Error("unavailable");
        int left = (int)Math.Floor(bounds.X), top = (int)Math.Floor(bounds.Y);
        int width = (int)Math.Ceiling(bounds.X + bounds.Width) - left;
        int height = (int)Math.Ceiling(bounds.Y + bounds.Height) - top;
        if (Math.Abs(left - request.expected_x) > 1 || Math.Abs(top - request.expected_y) > 1 ||
            Math.Abs(width - request.expected_width) > 1 || Math.Abs(height - request.expected_height) > 1)
            return Reply.Error("unavailable");
        if (!target.TryGetCurrentPattern(ValuePattern.Pattern, out var rawPattern) ||
            rawPattern is not ValuePattern pattern || pattern.Current.IsReadOnly)
            return Reply.Error("unsupported");
        if (pattern.Current.Value == request.text) return Reply.Error("unavailable");
        effectAttempted = true;
        pattern.SetValue(request.text);
        var deadline = Stopwatch.StartNew();
        while (deadline.ElapsedMilliseconds < 1500)
        {
            Thread.Sleep(25);
            if (pattern.Current.Value == request.text)
                return new Reply("verified", true, true);
        }
        return Reply.Error("unknown_outcome", true);
    }

    static bool Matches(AutomationElement element, AutomationElement.AutomationElementInformation current,
        Request request)
    {
        if (request.runtime_id.Length > 0)
        {
            var runtimeId = element.GetRuntimeId() ?? Array.Empty<int>();
            if (!runtimeId.SequenceEqual(request.runtime_id)) return false;
        }
        if (request.native_window_handle > 0 && current.NativeWindowHandle != request.native_window_handle)
            return false;
        if (request.automation_id.Length > 0 && current.AutomationId != request.automation_id)
            return false;
        return current.ControlType.ProgrammaticName == request.control_type;
    }
}

static class Native
{
    [DllImport("user32.dll")] internal static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wp, IntPtr lp, uint flags, uint timeout, out IntPtr result);
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
        try {
            if (!OpenProcessToken(process, TOKEN_QUERY, out var token)) throw new UnauthorizedAccessException();
            try {
                if (!GetTokenInformation(token, 20, out int value, 4, out _)) throw new UnauthorizedAccessException();
                return value != 0;
            }
            finally { CloseHandle(token); }
        }
        finally { CloseHandle(process); }
    }
}
