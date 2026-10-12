namespace Sora.DesktopShell;

// Serves a web panel's own files (HTML, CSS, JS, images) to WebView2 from the shipped panels\
// folder. SoraShell answers every request for https://panels.sora.example/ itself: a WebView2
// folder mapping for that host would swallow the /api/ calls, so the page's fetch to Core failed
// with "Failed to fetch" (found on the owner's machine, 2026-10-06).
public static class PanelFiles
{
    private static readonly Dictionary<string, string> Types = new(StringComparer.OrdinalIgnoreCase)
    {
        [".html"] = "text/html; charset=utf-8",
        [".css"] = "text/css; charset=utf-8",
        [".js"] = "text/javascript; charset=utf-8",
        [".mjs"] = "text/javascript; charset=utf-8",
        [".json"] = "application/json; charset=utf-8",
        [".svg"] = "image/svg+xml",
        [".png"] = "image/png",
        [".jpg"] = "image/jpeg",
        [".jpeg"] = "image/jpeg",
        [".webp"] = "image/webp",
        [".woff2"] = "font/woff2",
    };

    /// <summary>
    /// The file and content type for a GET of a panel URI, or null for anything else: other
    /// hosts or methods, /api/ paths, unknown types, missing files, or paths that would leave
    /// the panels folder.
    /// </summary>
    public static (string Path, string ContentType)? Resolve(string root, string method, string uri)
    {
        if (method != "GET" || !Uri.TryCreate(uri, UriKind.Absolute, out var parsed)
            || parsed.Scheme != Uri.UriSchemeHttps || !parsed.IsDefaultPort
            || !string.Equals(parsed.Host, PanelApiProxy.Host, StringComparison.OrdinalIgnoreCase))
            return null;
        var path = Uri.UnescapeDataString(parsed.AbsolutePath);
        var rawPath = uri.Split('?', 2)[0];
        if (path.StartsWith("/api/", StringComparison.Ordinal) || rawPath.Contains("..", StringComparison.Ordinal)
            || path.Contains('\\') || path.Contains(':')) return null;
        var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var full = Path.GetFullPath(Path.Combine(fullRoot, path.TrimStart('/')));
        if (!full.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase)
            || !Types.TryGetValue(Path.GetExtension(full), out var type) || !File.Exists(full))
            return null;
        return (full, type);
    }
}
