using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows.Automation;

// Console entry point is MTA; Core owns the wall-clock deadline and kills stalled workers.
Native.SetProcessDpiAwarenessContext(new IntPtr(-4));
object result;
try
{
    var line = Console.ReadLine();
    if (line is null || line.Length > 8192) throw new ArgumentException();
    var request = JsonSerializer.Deserialize<Request>(line) ?? throw new ArgumentException();
    if (request.schema_version != "1.0" || request.max_nodes is < 1 or > 256 ||
        request.max_depth is < 0 or > 12 || request.max_text_chars is < 1 or > 32768 ||
        !new[] { "inventory", "windows", "tree", "text", "selection" }.Contains(request.operation) ||
        (request.operation is "tree" or "text" or "selection") != request.window_handle.HasValue ||
        (request.operation == "inventory" ? request.process_id != 0 : request.process_id < 1))
        throw new ArgumentException();
    if (request.operation == "inventory") result = Observer.Run(request, null);
    else
    {
        Process process;
        try { process = Process.GetProcessById(request.process_id); }
        catch (ArgumentException) { Console.WriteLine(JsonSerializer.Serialize(Reply.Error("unavailable"))); return; }
        using var ownedProcessHandle = process;
        if (Native.IsElevated(request.process_id)) result = Reply.Error("elevated_target");
        else result = Observer.Run(request, process.StartTime.ToUniversalTime().ToString("O"));
    }
}
catch (UnauthorizedAccessException) { result = Reply.Error("access_denied"); }
catch (System.ComponentModel.Win32Exception) { result = Reply.Error("access_denied"); }
catch (ElementNotAvailableException) { result = Reply.Error("unavailable"); }
catch (ArgumentException) { result = Reply.Error("invalid_request"); }
catch (JsonException) { result = Reply.Error("invalid_request"); }
catch (Exception) { result = Reply.Error("unavailable"); }
Console.WriteLine(JsonSerializer.Serialize(result));

record Request(string schema_version, string operation, int process_id, long? window_handle,
    int max_nodes, int max_depth, int max_text_chars = 8192);
record Rect(int x, int y, int width, int height);
record Node(string node_id, string? parent_id, int process_id, long window_handle, string name,
    string automation_id, string control_type, int[] runtime_id, Rect? rect, bool focused,
    bool enabled, bool offscreen, bool password, string text = "", string selected_text = "",
    bool text_truncated = false, string? process_started_at = null,
    bool text_available = false, bool selection_available = false);
record Reply(string status, List<Node> nodes, bool truncated, string? process_started_at)
{
    public static Reply Error(string status) => new(status, new(), false, null);
}
static class Observer
{
    static string Bound(string value) => value.Length > 256 ? value[..256] : value;
    static Rect? Bounds(double x, double y, double width, double height)
    {
        if (!double.IsFinite(x + y + width + height) || width <= 0 || height <= 0 ||
            Math.Abs(x) > 1000000 || Math.Abs(y) > 1000000 || width > 1000000 || height > 1000000) return null;
        int left = (int)Math.Floor(x), top = (int)Math.Floor(y);
        return new(left, top, (int)Math.Ceiling(x + width) - left, (int)Math.Ceiling(y + height) - top);
    }
    public static Reply Run(Request request, string? processStartedAt)
    {
        var nodes = new List<Node>();
        bool truncated = false;
        var foreground = Native.GetForegroundWindow();
        int textRemaining = request.max_text_chars;
        if (request.operation is "windows" or "inventory")
        {
            Native.EnumWindows((hwnd, _) => {
                Native.GetWindowThreadProcessId(hwnd, out uint pid);
                if ((request.operation != "inventory" && pid != request.process_id) ||
                    pid == 0 || !Native.IsWindowVisible(hwnd)) return true;
                if (nodes.Count >= request.max_nodes) { truncated = true; return false; }
                var title = new StringBuilder(257);
                Native.GetWindowText(hwnd, title, title.Capacity);
                Native.GetWindowRect(hwnd, out var rect);
                string? started = processStartedAt;
                if (request.operation == "inventory")
                {
                    try { using var process = Process.GetProcessById((int)pid);
                        started = process.StartTime.ToUniversalTime().ToString("O"); }
                    catch { /* Metadata remains useful; inspection will report inaccessible identity. */ }
                }
                nodes.Add(new($"window-{hwnd.ToInt64()}", null, (int)pid, hwnd.ToInt64(),
                    Bound(title.ToString()), "", "Window", Array.Empty<int>(),
                    Bounds(rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top),
                    hwnd == foreground, Native.IsWindowEnabled(hwnd), Native.IsIconic(hwnd), false,
                    process_started_at: started));
                return true;
            }, IntPtr.Zero);
            return new("ok", nodes, truncated, processStartedAt);
        }
        var target = new IntPtr(request.window_handle!.Value);
        Native.GetWindowThreadProcessId(target, out uint actualPid);
        if (actualPid != request.process_id || !Native.IsWindow(target)) return Reply.Error("unavailable");
        if (Native.SendMessageTimeout(target, 0, IntPtr.Zero, IntPtr.Zero, 2, 200, out _) == IntPtr.Zero)
            return Reply.Error("timeout");
        var root = AutomationElement.FromHandle(target);
        void Visit(AutomationElement element, string? parent, int depth)
        {
            if (nodes.Count >= request.max_nodes) { truncated = true; return; }
            var current = element.Current;
            if (current.ProcessId != request.process_id) return;
            string id = $"node-{nodes.Count}";
            var b = current.BoundingRectangle;
            var runtimeId = element.GetRuntimeId() ?? Array.Empty<int>();
            if (runtimeId.Length > 32) runtimeId = runtimeId[..32];
            string text = "", selected = "";
            bool textClipped = false;
            bool textAvailable = false, selectionAvailable = false;
            string Clip(string value)
            {
                if (value.Length > textRemaining) { textClipped = true; value = value[..textRemaining]; }
                textRemaining -= value.Length;
                return value;
            }
            if (!current.IsPassword && request.operation is "text" or "selection")
            {
                if (textRemaining == 0) textClipped = true;
                else try
                {
                    if (element.TryGetCurrentPattern(TextPattern.Pattern, out var pattern))
                    {
                        var textPattern = (TextPattern)pattern;
                        // A document read also returns its selection. Reserve selection budget first
                        // so a long document cannot erase the short answer to "what is selected?".
                        selectionAvailable = true;
                        var ranges = textPattern.GetSelection();
                        if (ranges.Length > 8) textClipped = true;
                        foreach (var range in ranges.Take(8))
                        {
                            selected += Clip(range.GetText(textRemaining + 1));
                            if (textRemaining == 0) break;
                        }
                        if (request.operation == "text")
                        {
                            text = Clip(textPattern.DocumentRange.GetText(textRemaining + 1));
                            textAvailable = true;
                        }
                    }
                    else if (request.operation == "text" &&
                        element.TryGetCurrentPattern(ValuePattern.Pattern, out var valuePattern))
                    {
                        text = Clip(((ValuePattern)valuePattern).Current.Value);
                        textAvailable = true;
                    }
                }
                catch (InvalidOperationException) { /* This control does not expose this read pattern. */ }
            }
            nodes.Add(new(id, parent, current.ProcessId, current.NativeWindowHandle,
                current.IsPassword ? "" : Bound(current.Name), Bound(current.AutomationId),
                current.ControlType.ProgrammaticName, runtimeId, Bounds(b.X, b.Y, b.Width, b.Height),
                current.HasKeyboardFocus, current.IsEnabled, current.IsOffscreen, current.IsPassword,
                text, selected, textClipped, processStartedAt, textAvailable, selectionAvailable));
            var walker = TreeWalker.ControlViewWalker;
            var firstChild = walker.GetFirstChild(element);
            if (firstChild is not null &&
                (depth >= request.max_depth || nodes.Count >= request.max_nodes))
            { truncated = true; return; }
            for (var child = firstChild; child is not null; child = walker.GetNextSibling(child))
            {
                Visit(child, id, depth + 1);
                if (nodes.Count >= request.max_nodes) { truncated = true; break; }
            }
        }
        Visit(root, null, 0);
        Native.GetWindowThreadProcessId(target, out actualPid);
        return actualPid == request.process_id
            ? new("ok", nodes, truncated, processStartedAt)
            : Reply.Error("unavailable");
    }
}
static class Native
{
    internal delegate bool EnumProc(IntPtr hwnd, IntPtr data);
    [StructLayout(LayoutKind.Sequential)] internal struct WinRect { public int left, top, right, bottom; }
    [DllImport("user32.dll")] internal static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] internal static extern bool EnumWindows(EnumProc callback, IntPtr data);
    [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsWindowEnabled(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] internal static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr hwnd, out WinRect rect);
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
