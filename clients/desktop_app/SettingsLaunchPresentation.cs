using System.Globalization;
using System.Text.Json;

namespace Sora.DesktopApp;

// Read-only, inert text; never a command executor or a local effective-settings store.
public static class SettingsLaunchPresentation
{
    public static string Format(JsonElement settings, bool current)
    {
        string availability = current ? "Current Core projection" : "Last-known / unconfirmed Core projection (not current)";
        if (settings.ValueKind != JsonValueKind.Object || !settings.TryGetProperty("launch_details", out var details)
            || details.ValueKind != JsonValueKind.Object || !details.TryGetProperty("version", out var version)
            || !version.TryGetInt32(out int value) || value != 1)
            return availability + "\r\nLaunch-argument details are not supplied by this Core. Saved preferences are not evidence of a running model.";
        var sections = new List<string> { availability + "\r\nRead-only argument arrays. Previews are not validated or loaded; environment, authentication and logs are excluded." };
        foreach (var (key, title) in new[] { ("active", "Core-captured submitted managed-worker arguments"),
            ("next_reload", "Preview · next model reload (current boot settings)"),
            ("next_start", "Preview · next Core start (saved boot settings)") }) {
            if (!details.TryGetProperty(key, out var entry) || entry.ValueKind != JsonValueKind.Object
                || !entry.TryGetProperty("note", out var note) || note.ValueKind != JsonValueKind.String
                || !Readable(note.GetString()!, 700) || !entry.TryGetProperty("argv", out var argv)) {
                sections.Add(title + "\r\nUnavailable: incomplete/unsupported launch metadata."); continue;
            }
            if (argv.ValueKind == JsonValueKind.Null) {
                sections.Add(title + "\r\n" + note.GetString() + "\r\nArguments unavailable."); continue;
            }
            if (!ArgumentsSafe(argv)) {
                sections.Add(title + "\r\nUnavailable: launch argument metadata failed display validation."); continue;
            }
            sections.Add(title + "\r\n" + note.GetString() + "\r\n" +
                JsonSerializer.Serialize(argv, new JsonSerializerOptions { WriteIndented = true }));
        }
        return string.Join("\r\n\r\n", sections);
    }
    private static bool Readable(string text, int bound) => text.Length <= bound && !text.Any(c =>
        char.IsControl(c) || char.GetUnicodeCategory(c) is UnicodeCategory.Format or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator);
    private static bool ArgumentsSafe(JsonElement argv)
    {
        if (argv.ValueKind != JsonValueKind.Array || argv.GetArrayLength() is < 1 or > 128) return false;
        var arguments = new List<string>(); int total = 0;
        foreach (var item in argv.EnumerateArray()) {
            if (item.ValueKind != JsonValueKind.String || item.GetString() is not { Length: > 0 } text
                || !Readable(text, 32768) || (total += text.Length) > 32768) return false;
            arguments.Add(text);
        }
        var pairs = new HashSet<string> { "--model", "--mmproj", "--host", "--port", "--alias", "--ctx-size", "--parallel",
            "--gpu-layers", "--flash-attn", "--cache-type-k", "--cache-type-v", "--batch-size", "--ubatch-size", "--split-mode",
            "--main-gpu", "--load-mode", "--tensor-split", "--n-cpu-moe", "--spec-type", "--spec-draft-model", "--spec-draft-ngl",
            "--spec-draft-type-k", "--spec-draft-type-v", "--spec-draft-n-min", "--spec-draft-n-max" };
        var singles = new HashSet<string> { "--no-webui", "--cpu-moe", "--swa-full" };
        var seen = new HashSet<string>(); int index = 1;
        while (index < arguments.Count) {
            string flag = arguments[index]; if (!seen.Add(flag)) return false;
            if (singles.Contains(flag)) index++;
            else if (pairs.Contains(flag) && index + 1 < arguments.Count && !arguments[index + 1].StartsWith("--")) index += 2;
            else return false;
        }
        return new[] { "--model", "--mmproj", "--host", "--alias", "--no-webui" }.All(seen.Contains)
            && arguments[arguments.IndexOf("--host") + 1] == "127.0.0.1"
            && arguments[arguments.IndexOf("--alias") + 1] == "sora-local";
    }
}
