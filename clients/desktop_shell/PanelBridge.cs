using System.Text.Json;

namespace Sora.DesktopShell;

public enum PanelCommandKind
{
    Close, Hide, Minimize, Maximize, Drag, Resize, OpenPanel, Ready, PickFile, Dirty, Busy,
    PreferencesSave, PreferencesReload, PreferencesRecover, PlacementReset, MemoryPresented, MemoryHighlightCleared,
}

public sealed record PanelCommand(PanelCommandKind Kind, string? Panel = null, string? Edge = null,
    string? PickKind = null, string? RequestId = null, string? Select = null, bool Dirty = false,
    string? StartFolder = null, bool Busy = false, PanelAppearance? Values = null, PanelAppearance? Baseline = null,
    string? Status = null, PanelRect? Anchor = null);

/// <summary>The UI preferences the web Appearance page edits; text scale is a whole percentage.</summary>
public sealed record PanelAppearance(string Theme, int TextScale, string Shortcut, bool ChatCompact,
    bool ChatPinned, bool ShowTechnicalDetail, bool ReducedMotion)
{
    public static PanelAppearance From(ShellPreferences values) => new(values.Theme.ToString(),
        (int)Math.Round(values.TextScale * 100), values.Shortcut.ToString(), values.ChatCompact, values.ChatPinned,
        values.ShowTechnicalDetail, values.ReducedMotion);

    /// <summary>These seven fields over <paramref name="values"/>; everything else (placement, imports) is kept.</summary>
    public ShellPreferences ApplyTo(ShellPreferences values) => values with {
        Theme = Enum.Parse<ShellPalette>(Theme), TextScale = TextScale / 100d, Shortcut = Enum.Parse<ShellShortcut>(Shortcut),
        ChatCompact = ChatCompact, ChatPinned = ChatPinned, ShowTechnicalDetail = ShowTechnicalDetail,
        ReducedMotion = ReducedMotion };
}

/// <summary>A rectangle the page measured, in CSS pixels from the top-left of the page.</summary>
public sealed record PanelRect(double X, double Y, double Width, double Height);

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
                "panel.busy" when root.TryGetProperty("busy", out var busy)
                    && busy.ValueKind is JsonValueKind.True or JsonValueKind.False
                    => new(PanelCommandKind.Busy, Busy: busy.GetBoolean()),
                "prefs.save" when Text("requestId") is { } id && ValidRequestId(id)
                    && Appearance(root, "values") is { } values && Appearance(root, "baseline") is { } baseline
                    => new(PanelCommandKind.PreferencesSave, RequestId: id, Values: values, Baseline: baseline),
                "prefs.reload" when Text("requestId") is { } id && ValidRequestId(id)
                    => new(PanelCommandKind.PreferencesReload, RequestId: id),
                "prefs.recover" when Text("requestId") is { } id && ValidRequestId(id)
                    => new(PanelCommandKind.PreferencesRecover, RequestId: id),
                "placement.reset" when Text("requestId") is { } id && ValidRequestId(id)
                    => new(PanelCommandKind.PlacementReset, RequestId: id),
                // The page's answer to host.present-memory: what it now shows, and where (CSS pixels).
                "memory.presented" when Text("requestId") is { } id && Guid.TryParseExact(id, "D", out _)
                    && Text("status") is { } status && PresentationStatuses.Contains(status)
                    && Rect(root, "anchor") is var anchor
                    && (status == "unavailable" ? Absent(root, "anchor") : anchor is not null)
                    => new(PanelCommandKind.MemoryPresented, RequestId: id.ToLowerInvariant(), Status: status, Anchor: anchor),
                "memory.highlight-cleared" => new(PanelCommandKind.MemoryHighlightCleared),
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

    private static readonly IReadOnlySet<string> PresentationStatuses = new HashSet<string>(StringComparer.Ordinal)
        { "selected", "already-visible", "unavailable" };
    private static readonly string[] AppearanceFields =
        ["theme", "textScale", "shortcut", "chatCompact", "chatPinned", "showTechnicalDetail", "reducedMotion"];

    // Exactly the seven appearance fields, each a known value; anything else drops the message.
    private static PanelAppearance? Appearance(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Object
            || value.EnumerateObject().Count() != AppearanceFields.Length
            || AppearanceFields.Any(field => !value.TryGetProperty(field, out _))) return null;
        bool? Flag(string field) => value.GetProperty(field).ValueKind switch
            { JsonValueKind.True => true, JsonValueKind.False => false, _ => null };
        var theme = value.GetProperty("theme"); var shortcut = value.GetProperty("shortcut"); var scale = value.GetProperty("textScale");
        if (theme.ValueKind != JsonValueKind.String || !Enum.TryParse<ShellPalette>(theme.GetString(), false, out var palette)
            || !Enum.IsDefined(palette) || palette.ToString() != theme.GetString()
            || shortcut.ValueKind != JsonValueKind.String || !Enum.TryParse<ShellShortcut>(shortcut.GetString(), false, out var key)
            || !Enum.IsDefined(key) || key.ToString() != shortcut.GetString()
            || scale.ValueKind != JsonValueKind.Number || !scale.TryGetInt32(out var percent) || percent is < 85 or > 175
            || Flag("chatCompact") is not { } compact || Flag("chatPinned") is not { } pinned
            || Flag("showTechnicalDetail") is not { } technical || Flag("reducedMotion") is not { } reduced) return null;
        return new(palette.ToString(), percent, key.ToString(), compact, pinned, technical, reduced);
    }

    private static bool Absent(JsonElement root, string name) =>
        !root.TryGetProperty(name, out var value) || value.ValueKind == JsonValueKind.Null;

    // A finite, non-empty rectangle of sensible size, or null when absent or malformed.
    private static PanelRect? Rect(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Object) return null;
        double? Number(string field) => value.TryGetProperty(field, out var item) && item.ValueKind == JsonValueKind.Number
            && item.TryGetDouble(out var number) && double.IsFinite(number) && Math.Abs(number) <= 100_000 ? number : null;
        return Number("x") is { } x && Number("y") is { } y && Number("width") is { } width && Number("height") is { } height
            && width > 0 && height > 0 ? new(x, y, width, height) : null;
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
