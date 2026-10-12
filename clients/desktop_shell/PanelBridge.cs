using System.Text.Json;

namespace Sora.DesktopShell;

public enum PanelCommandKind { Close, Hide, Minimize, Maximize, Drag, Resize, OpenPanel, Ready, PickFile, Dirty }

public sealed record PanelCommand(PanelCommandKind Kind, string? Panel = null, string? Edge = null,
    string? PickKind = null, string? RequestId = null, string? Select = null, bool Dirty = false,
    string? StartFolder = null);

// Messages from web panel pages (clients/panels/shared/bridge.js). Every message is checked
// here; anything unknown or malformed is dropped. Keep the lists in step with bridge.js.
public static class PanelBridge
{
    public static readonly IReadOnlySet<string> OpenablePanels = new HashSet<string>(StringComparer.Ordinal)
        { "chat", "settings", "voice", "memory", "activity", "agents", "paths", "appearance" };
    public static readonly IReadOnlySet<string> PickKinds = new HashSet<string>(StringComparer.Ordinal)
        { "gguf", "exe", "dir", "file", "attachment" };
    public static readonly IReadOnlySet<string> ResizeEdges = new HashSet<string>(StringComparer.Ordinal)
        { "n", "s", "e", "w", "ne", "nw", "se", "sw" };

    public static PanelCommand? Parse(string json)
    {
        if (json.Length > 4096) return null;
        try
        {
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("type", out var type)
                || type.ValueKind != JsonValueKind.String) return null;
            string? Text(string name) => root.TryGetProperty(name, out var value)
                && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            return type.GetString() switch
            {
                "window.close" => new(PanelCommandKind.Close),
                "window.hide" => new(PanelCommandKind.Hide),
                "window.minimize" => new(PanelCommandKind.Minimize),
                "window.maximize" => new(PanelCommandKind.Maximize),
                "window.drag" => new(PanelCommandKind.Drag),
                "window.resize" when Text("edge") is { } edge && ResizeEdges.Contains(edge)
                    => new(PanelCommandKind.Resize, Edge: edge),
                "panel.open" when Text("panel") is { } panel && OpenablePanels.Contains(panel)
                    && (Text("select") is not { } chosen || ValidItemId(chosen))
                    && (!root.TryGetProperty("select", out var raw) || raw.ValueKind == JsonValueKind.String)
                    => new(PanelCommandKind.OpenPanel, Panel: panel, Select: Text("select")),
                "panel.ready" => new(PanelCommandKind.Ready),
                "panel.dirty" when root.TryGetProperty("dirty", out var dirty)
                    && dirty.ValueKind is JsonValueKind.True or JsonValueKind.False
                    => new(PanelCommandKind.Dirty, Dirty: dirty.GetBoolean()),
                "file.pick" when Text("kind") is { } kind && PickKinds.Contains(kind)
                    && Text("requestId") is { } id && ValidRequestId(id)
                    && (!root.TryGetProperty("start", out var start) || start.ValueKind == JsonValueKind.String)
                    => new(PanelCommandKind.PickFile, PickKind: kind, RequestId: id,
                        StartFolder: StartFolder(Text("start"))),
                _ => null,
            };
        }
        catch (JsonException) { return null; }
    }

    /// <summary>An exact Core identifier, such as a task ID, to select in an opened panel.</summary>
    public static bool ValidItemId(string id) =>
        System.Text.RegularExpressions.Regex.IsMatch(id, "\\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\z");

    private static bool ValidRequestId(string id) =>
        id.Length is > 0 and <= 64 && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-');

    /// <summary>
    /// Where a file dialog opens: an existing absolute local folder the page suggested, or null
    /// for Windows' own default. Network paths and anything that is not a folder are ignored.
    /// </summary>
    public static string? StartFolder(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || path.Length > 260 || path.StartsWith(@"\\", StringComparison.Ordinal)
            || path.StartsWith("//", StringComparison.Ordinal) || !Path.IsPathFullyQualified(path)) return null;
        try { return Directory.Exists(path) ? Path.GetFullPath(path) : null; }
        catch (Exception error) when (error is ArgumentException or NotSupportedException or IOException) { return null; }
    }

    /// <summary>Open-dialog filter for a pick kind; null for a folder.</summary>
    public static string? Filter(string kind) => kind switch
    {
        "gguf" => "GGUF model (*.gguf)|*.gguf",
        "exe" => "Programs (*.exe)|*.exe",
        "dir" => null,
        _ => "All files (*.*)|*.*",
    };

    /// <summary>The Win32 hit-test code a resize edge maps to (WM_NCLBUTTONDOWN).</summary>
    public static int HitTest(string edge) => edge switch
    {
        "w" => 10, "e" => 11, "n" => 12, "nw" => 13, "ne" => 14, "s" => 15, "sw" => 16, "se" => 17,
        _ => throw new ArgumentOutOfRangeException(nameof(edge)),
    };
}
