using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Sora.DesktopShell;

public sealed record ShellOptions(Uri CoreUrl, string TokenFile, string? StateRoot, string Panel,
    string? LegacyWidgetFile = null, string? LegacyDesktopFile = null, ManagedCoreOptions? Managed = null)
{
    public bool Hosted => StateRoot is not null;
    public static ShellOptions Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || args[index] is not
                ("--core-url" or "--token-file" or "--state-root" or "--show" or "--legacy-widget-file" or "--legacy-desktop-file"
                or "--managed-project-root" or "--managed-powershell" or "--managed-settings" or "--managed-llama-config"
                or "--managed-model" or "--managed-model-url" or "--managed-avatar" or "--managed-workspace"
                or "--managed-write-repo" or "--managed-timeout" or "--managed-no-avatar" or "--managed-setup-voice"
                or "--managed-provider" or "--managed-discovery" or "--managed-codex-model"
                or "--managed-antigravity-model" or "--managed-antigravity-effort" or "--managed-antigravity-skip-permissions"
                or "--managed-unified-settings-only"))
                throw new ArgumentException("Use --core-url URL --token-file PATH [--state-root PATH --show chat|voice|memory|activity|agents|paths|board|content|integrations|settings|appearance|menu|none|quit] " +
                    "[--legacy-widget-file PATH --legacy-desktop-file PATH].");
            if (!values.TryAdd(args[index], args[index + 1])) throw new ArgumentException("Duplicate option.");
        }
        if (!values.TryGetValue("--core-url", out var address) || !values.TryGetValue("--token-file", out var token)
            || !Uri.TryCreate(address, UriKind.Absolute, out var url) || url.Scheme != "http"
            || url.Host is not ("127.0.0.1" or "::1") || url.UserInfo.Length > 0
            || url.Query.Length > 0 || url.Fragment.Length > 0 || url.AbsolutePath != "/")
            throw new ArgumentException("An explicit loopback Core URL and private token file are required.");
        var state = values.TryGetValue("--state-root", out var root) ? ShellProfile.CanonicalRoot(root) : null;
        var panel = values.GetValueOrDefault("--show", state is null ? "chat" : "none");
        if (panel is not ("chat" or "voice" or "memory" or "activity" or "agents" or "paths" or "board" or "content" or "integrations" or "settings" or "appearance" or "menu" or "none" or "quit") || (state is null && panel != "chat"))
            throw new ArgumentException("Use a supported panel; --show requires a host profile.");
        token = Path.GetFullPath(token);
        if (state is not null && (Path.GetRelativePath(state, token) is var relative
            && (Path.IsPathRooted(relative) || relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar))))
            throw new ArgumentException("Host token file must belong to the explicit profile.");
        var widget = values.GetValueOrDefault("--legacy-widget-file");
        var desktop = values.GetValueOrDefault("--legacy-desktop-file");
        if (state is null && (widget is not null || desktop is not null))
            throw new ArgumentException("Legacy UI import requires an explicit host profile.");
        var managed = ManagedCoreOptions.Parse(values, state);
        return new(url, token, state, panel, widget is null ? null : Path.GetFullPath(widget),
            desktop is null ? null : Path.GetFullPath(desktop), managed);
    }
}

public static class ShellProfile
{
    public static string CanonicalRoot(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("Select an explicit profile.");
        var full = Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
        // Do not silently alias a profile through a junction/symlink. Native resolution/import can
        // support aliases later, but identity must not fork because of a different path spelling.
        for (var directory = new DirectoryInfo(full); directory is not null; directory = directory.Parent)
            if (directory.Exists && (directory.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new ArgumentException("Profile aliases are ambiguous; use a resolved non-link state root.");
        return full;
    }
    public static string Key(string root, string principal) => Convert.ToHexString(SHA256.HashData(
        Encoding.UTF8.GetBytes("sora-shell-profile-v1\n" + principal + "\n" + CanonicalRoot(root).ToUpperInvariant())));

    public static string ValidateIdentity(JsonElement identity, string expectedRoot)
    {
        if (identity.GetProperty("version").GetInt32() != 1 || !string.Equals(
            CanonicalRoot(identity.GetProperty("state_root").GetString() ?? ""), CanonicalRoot(expectedRoot),
            StringComparison.OrdinalIgnoreCase) || !Guid.TryParse(identity.GetProperty("instance_id").GetString(), out _))
            throw new InvalidOperationException("Core belongs to a different or unsupported profile. No effects were sent.");
        return identity.GetProperty("instance_id").GetString()!;
    }
}
