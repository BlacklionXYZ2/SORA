using System.Drawing;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sora.DesktopShell;

public enum ShellPalette { Dark, System }
public enum ShellShortcut { None, CtrlAltSpace, CtrlAltS }
public sealed record PanelPlacement(string Monitor, double X, double Y, double Width, double Height, int Dpi);
public sealed record LegacyChatPlacement(string Monitor, int Anchor, int? X, int? Y);
public sealed record LegacyImport(string Source, string Status, string? Sha256 = null, string? Backup = null,
    bool? Quiet = null, bool? AlwaysOnTop = null, int? SelectedTab = null);

// UI-only. Never store tokens, model/access/voice/agent settings, transcript or composer drafts here.
public sealed record ShellPreferences
{
    public int Version { get; init; } = 1;
    public long Revision { get; init; }
    public ShellPalette Theme { get; init; } = ShellPalette.Dark;
    public double TextScale { get; init; } = 1;
    public bool ReducedMotion { get; init; } = true;
    public bool ChatCompact { get; init; }
    public bool ChatPinned { get; init; }
    public bool BoardExpanded { get; init; }
    public bool ShowTechnicalDetail { get; init; }
    public ShellShortcut Shortcut { get; init; } = ShellShortcut.CtrlAltSpace;
    public Dictionary<string, PanelPlacement> Panels { get; init; } = [];
    public bool ImportAttempted { get; init; }
    public LegacyChatPlacement? LegacyChat { get; init; }
    public LegacyImport[] Imports { get; init; } = [];

    public void Validate()
    {
        if (Version != 1 || Revision < 0 || Revision == long.MaxValue || !Enum.IsDefined(Theme)
            || !Enum.IsDefined(Shortcut) || !double.IsFinite(TextScale) || TextScale is < 0.85 or > 1.75
            || Panels is null || Panels.Count > 12 || Imports is null || Imports.Length > 2)
            throw new InvalidDataException("Unsupported UI preferences version or values.");
        foreach (var (key, placement) in Panels)
        {
            if (key is not ("chat" or "voice" or "memory" or "activity" or "agents" or "paths" or "board" or "content" or "integrations" or "settings" or "appearance" or "motion" or "menu") || placement is null
                || placement.Monitor is null || placement.Monitor.Length > 256
                || placement.Dpi is < 48 or > 768 || !double.IsFinite(placement.X)
                || !double.IsFinite(placement.Y) || !double.IsFinite(placement.Width)
                || !double.IsFinite(placement.Height) || Math.Abs(placement.X) > 65536
                || Math.Abs(placement.Y) > 65536 || placement.Width is < 1 or > 8192
                || placement.Height is < 1 or > 8192)
                throw new InvalidDataException("Invalid panel placement.");
        }
        if (LegacyChat is { } hint && (hint.Monitor is null || hint.Monitor.Length > 256
            || hint.Anchor is < 0 or > 3 || hint.X.HasValue != hint.Y.HasValue))
            throw new InvalidDataException("Invalid legacy placement.");
        foreach (var import in Imports)
            if (import is null || string.IsNullOrEmpty(import.Source) || import.Source.Length > 2048
                || import.Status is not ("imported" or "missing" or "invalid")
                || (import.Sha256 is { } hash && (hash.Length != 64 || !hash.All(Uri.IsHexDigit)))
                || import.Backup?.Length > 2048 || import.SelectedTab is < 0 or > 5)
                throw new InvalidDataException("Invalid import provenance.");
    }
}

public static class PanelGeometry
{
    // Position is logical pixels relative to this monitor's work area, not global physical pixels.
    public static Rectangle Restore(PanelPlacement placement, Rectangle area, int dpi)
    {
        var scale = Math.Clamp(dpi, 48, 768) / 96d;
        return Clamp(new Rectangle(area.Left + (int)Math.Round(placement.X * scale),
            area.Top + (int)Math.Round(placement.Y * scale), (int)Math.Round(placement.Width * scale),
            (int)Math.Round(placement.Height * scale)), area);
    }
    public static Rectangle Clamp(Rectangle bounds, Rectangle area)
    {
        var width = Math.Clamp(bounds.Width, 1, Math.Max(1, area.Width));
        var height = Math.Clamp(bounds.Height, 1, Math.Max(1, area.Height));
        return new Rectangle(Math.Clamp(bounds.X, area.Left, Math.Max(area.Left, area.Right - width)),
            Math.Clamp(bounds.Y, area.Top, Math.Max(area.Top, area.Bottom - height)), width, height);
    }
    public static PanelPlacement Capture(Rectangle bounds, Rectangle area, string monitor, int dpi)
    {
        var scale = Math.Clamp(dpi, 48, 768) / 96d;
        return new(monitor, (bounds.Left - area.Left) / scale, (bounds.Top - area.Top) / scale,
            bounds.Width / scale, bounds.Height / scale, dpi);
    }
}

public sealed class ShellPreferencesStore
{
    private const int MaxBytes = 256 * 1024;
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, WriteIndented = true, MaxDepth = 16,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter(allowIntegerValues: false) }
    };
    private ShellPreferences current = new();
    private string? fingerprint;
    public string FilePath { get; }
    public bool ReadOnly { get; private set; }
    public string Diagnostic { get; private set; } = "";
    public ShellPreferences Current => current with { Panels = new(current.Panels), Imports = [.. current.Imports] };
    public event EventHandler? Changed;

    public ShellPreferencesStore(string root, string? legacyWidget = null, string? legacyDesktop = null)
    {
        root = ShellProfile.CanonicalRoot(root);
        FilePath = Path.Combine(root, "desktop-shell", "preferences.json");
        Reload();
        if (!ReadOnly && fingerprint is null)
        {
            var candidate = ImportLegacy(root, legacyWidget, legacyDesktop);
            if (!TrySave(candidate, 0, out var error)) Diagnostic = error;
        }
    }
    private void CheckPaths()
    {
        ShellProfile.CanonicalRoot(Path.GetDirectoryName(FilePath)!);
        foreach (var path in new[] { FilePath, FilePath + ".lock" })
            if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("UI preference links are ambiguous; original left untouched.");
    }
    private static byte[] ReadBounded(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaxBytes) throw new InvalidDataException("UI preference file is too large.");
        var bytes = new byte[checked((int)stream.Length)]; stream.ReadExactly(bytes); return bytes;
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));
    private static ReadOnlyMemory<byte> JsonBytes(byte[] bytes) => bytes.AsSpan().StartsWith(new byte[] { 0xEF, 0xBB, 0xBF })
        ? bytes.AsMemory(3) : bytes;
    private static void NoDuplicateKeys(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            { if (!keys.Add(property.Name)) throw new InvalidDataException("Duplicate preference key."); NoDuplicateKeys(property.Value); }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var child in value.EnumerateArray()) NoDuplicateKeys(child);
    }
    public void Reload()
    {
        current = new(); fingerprint = null; ReadOnly = false; Diagnostic = "";
        try
        {
            CheckPaths();
            if (!File.Exists(FilePath)) return;
            var bytes = ReadBounded(FilePath); fingerprint = Hash(bytes);
            using var document = JsonDocument.Parse(JsonBytes(bytes), new JsonDocumentOptions { MaxDepth = 16 });
            NoDuplicateKeys(document.RootElement);
            // Required identity fields prevent a partial/unrelated JSON object becoming UI defaults.
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || !document.RootElement.TryGetProperty("version", out var version)
                || !document.RootElement.TryGetProperty("revision", out _))
                throw new InvalidDataException("UI preference version/revision is missing.");
            if (version.ValueKind != JsonValueKind.Number || !version.TryGetInt32(out var versionNumber) || versionNumber != 1)
                throw new InvalidDataException("Unsupported UI preferences version.");
            var loaded = document.RootElement.Deserialize<ShellPreferences>(Json)
                ?? throw new InvalidDataException("UI preferences are empty.");
            loaded.Validate(); current = loaded;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException
            or InvalidDataException or ArgumentException)
        {
            ReadOnly = true;
            Diagnostic = "UI preferences unavailable; safe UI-only defaults in memory. Original is untouched. " + error.Message;
        }
        finally { Changed?.Invoke(this, EventArgs.Empty); }
    }
    public bool TrySave(ShellPreferences candidate, long expectedRevision, out string error)
        => Write(candidate, expectedRevision, false, out error);

    public bool TrySaveAppearance(ShellPreferences draft, ShellPreferences baseline, out string error)
    {
        var latest = Current;
        // Moving a panel while editing appearance is not a competing appearance edit.
        if (!SameAppearance(latest, baseline))
        { error = "Appearance changed. Keep your draft; explicitly reload/reconcile before saving."; Diagnostic = error; return false; }
        return TrySave(latest with { Theme = draft.Theme, TextScale = draft.TextScale,
            ReducedMotion = draft.ReducedMotion, ChatCompact = draft.ChatCompact, ChatPinned = draft.ChatPinned,
            ShowTechnicalDetail = draft.ShowTechnicalDetail, Shortcut = draft.Shortcut }, latest.Revision, out error);
    }
    private static bool SameAppearance(ShellPreferences left, ShellPreferences right) =>
        left.Theme == right.Theme && left.TextScale == right.TextScale && left.ReducedMotion == right.ReducedMotion
        && left.ChatCompact == right.ChatCompact && left.ChatPinned == right.ChatPinned
        && left.ShowTechnicalDetail == right.ShowTechnicalDetail && left.Shortcut == right.Shortcut;

    // Owner-invoked recovery only. UI must confirm replacement; backup is byte-identical, never deleted.
    public bool TryRecoverDefaults(out string error)
        => Write(new ShellPreferences { ImportAttempted = true }, current.Revision, true, out error);

    private bool Write(ShellPreferences candidate, long expectedRevision, bool recover, out string error)
    {
        error = ""; string? temporary = null;
        try
        {
            if (ReadOnly && !recover) throw new InvalidOperationException(Diagnostic +
                " Preserve/recover the invalid UI file before saving.");
            candidate.Validate(); CheckPaths();
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            using var fileLock = new FileStream(FilePath + ".lock", FileMode.OpenOrCreate,
                FileAccess.ReadWrite, FileShare.None);
            var bytes = File.Exists(FilePath) ? ReadBounded(FilePath) : null;
            if ((bytes is null ? null : Hash(bytes)) != fingerprint || expectedRevision != current.Revision)
                throw new InvalidOperationException("UI preferences changed. Keep your draft; explicitly reload/reconcile before saving.");
            if (recover && bytes is not null) Backup(bytes, "recovery");
            var updated = candidate with { Revision = checked(current.Revision + 1) };
            var payload = JsonSerializer.SerializeToUtf8Bytes(updated, Json);
            if (payload.Length > MaxBytes) throw new InvalidDataException("UI preferences are too large.");
            temporary = FilePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { output.Write(payload); output.Flush(true); }
            File.Move(temporary, FilePath, true); temporary = null;
            current = updated with { Panels = new(updated.Panels), Imports = [.. updated.Imports] };
            fingerprint = Hash(payload); ReadOnly = false; Diagnostic = "";
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException
            or InvalidDataException or InvalidOperationException or ArgumentException or OverflowException)
        { error = exception.Message; Diagnostic = error; return false; }
        finally
        {
            try { if (temporary is not null && File.Exists(temporary)) File.Delete(temporary); }
            catch (Exception cleanup) when (cleanup is IOException or UnauthorizedAccessException) { /* Original/backup remain intact. */ }
        }
        Changed?.Invoke(this, EventArgs.Empty); return true;
    }
    private string Backup(byte[] bytes, string kind)
    {
        var directory = ShellProfile.CanonicalRoot(Path.Combine(Path.GetDirectoryName(FilePath)!, "backups"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, kind + "-" + DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffffffZ")
            + "-" + Guid.NewGuid().ToString("N") + ".json");
        using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        output.Write(bytes); output.Flush(true); return path;
    }
    private ShellPreferences ImportLegacy(string root, string? widget, string? desktop)
    {
        var candidate = new ShellPreferences { ImportAttempted = true };
        var imports = new List<LegacyImport>();
        foreach (var (kind, path) in new[] { ("widget", widget ?? Path.Combine(root, "widget", "settings.json")),
            ("desktop", desktop ?? Path.Combine(root, "desktop", "settings.json")) })
        {
            var fullPath = Path.GetFullPath(path);
            if (!File.Exists(fullPath)) { imports.Add(new(fullPath, "missing")); continue; }
            try
            {
                ShellProfile.CanonicalRoot(Path.GetDirectoryName(fullPath)!);
                if ((File.GetAttributes(fullPath) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Legacy links are ambiguous.");
                var bytes = ReadBounded(fullPath);
                using var document = JsonDocument.Parse(JsonBytes(bytes), new JsonDocumentOptions { MaxDepth = 8 });
                var value = document.RootElement; NoDuplicateKeys(value);
                var allowed = kind == "widget" ? new[] { "Anchor", "Monitor", "Expanded", "Quiet", "AlwaysOnTop",
                    "ShowTechnicalDetail", "SavedX", "SavedY" } : ["ShowTechnicalDetail", "SelectedTab"];
                if (value.ValueKind != JsonValueKind.Object || !value.EnumerateObject().Any()
                    || value.EnumerateObject().Any(property => !allowed.Contains(property.Name)))
                    throw new InvalidDataException("Not a recognized legacy UI preference file.");
                bool Flag(string name, bool fallback = false) => value.TryGetProperty(name, out var item) ? item.GetBoolean() : fallback;
                int? Number(string name) => value.TryGetProperty(name, out var item) && item.ValueKind != JsonValueKind.Null ? item.GetInt32() : null;
                var technical = Flag("ShowTechnicalDetail");
                if (kind == "widget")
                {
                    var monitor = value.TryGetProperty("Monitor", out var m) ? m.GetString() ?? "" : "";
                    var anchor = 0;
                    if (value.TryGetProperty("Anchor", out var a))
                        anchor = a.ValueKind == JsonValueKind.String ? a.GetString() switch {
                            "BottomRight" => 0, "BottomLeft" => 1, "TopRight" => 2, "TopLeft" => 3,
                            _ => throw new InvalidDataException("Unknown legacy anchor.") } : a.GetInt32();
                    var imported = candidate with { ChatCompact = !Flag("Expanded"), ShowTechnicalDetail = technical,
                        LegacyChat = new(monitor, anchor, Number("SavedX"), Number("SavedY")) };
                    imported.Validate();
                    var record = new LegacyImport(fullPath, "imported", Hash(bytes), Backup(bytes, kind),
                        Flag("Quiet"), Flag("AlwaysOnTop", true));
                    candidate = imported; imports.Add(record);
                }
                else
                {
                    var selected = Number("SelectedTab") ?? 0;
                    if (selected is < 0 or > 5) throw new InvalidDataException("Invalid legacy selected tab.");
                    imports.Add(new(fullPath, "imported", Hash(bytes), Backup(bytes, kind), SelectedTab: selected));
                    if (value.TryGetProperty("ShowTechnicalDetail", out _)) candidate = candidate with { ShowTechnicalDetail = technical };
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException
                or InvalidDataException or InvalidOperationException or ArgumentException or FormatException or OverflowException)
            { imports.Add(new(fullPath, "invalid")); }
        }
        return candidate with { Imports = [.. imports] };
    }
}
