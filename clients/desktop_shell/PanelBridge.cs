using System.Text.Json;

namespace Sora.DesktopShell;

public enum PanelCommandKind { Close, Hide, Minimize, Maximize, Drag, Resize, OpenPanel, Ready }

public sealed record PanelCommand(PanelCommandKind Kind, string? Panel = null, string? Edge = null);

// Messages from web panel pages (clients/panels/shared/bridge.js). Every message is checked
// here; anything unknown or malformed is dropped. Keep the lists in step with bridge.js.
public static class PanelBridge
{
    public static readonly IReadOnlySet<string> OpenablePanels = new HashSet<string>(StringComparer.Ordinal)
        { "chat", "settings", "voice", "memory", "activity", "agents", "paths", "appearance" };
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
                    => new(PanelCommandKind.OpenPanel, Panel: panel),
                "panel.ready" => new(PanelCommandKind.Ready),
                _ => null,
            };
        }
        catch (JsonException) { return null; }
    }

    /// <summary>The Win32 hit-test code a resize edge maps to (WM_NCLBUTTONDOWN).</summary>
    public static int HitTest(string edge) => edge switch
    {
        "w" => 10, "e" => 11, "n" => 12, "nw" => 13, "ne" => 14, "s" => 15, "sw" => 16, "se" => 17,
        _ => throw new ArgumentOutOfRangeException(nameof(edge)),
    };
}
