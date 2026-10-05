using System.Diagnostics;

namespace Sora.DesktopShell;

public sealed record ManagedCoreOptions(string ProjectRoot, string PowerShell, string? Settings,
    string? LlamaConfig, string? Model, string ModelUrl, string? Avatar, string? Workspace,
    string? WriteRepo, int Timeout, bool NoAvatar, bool SetupVoice, string Provider, bool DiscoverEndpoint,
    string? CodexModel = null, string? AntigravityModel = null, string? AntigravityEffort = null,
    bool AntigravitySkipPermissions = false, bool UnifiedSettingsOnly = false)
{
    public static ManagedCoreOptions? Parse(Dictionary<string, string> values, string? stateRoot)
    {
        if (!values.TryGetValue("--managed-project-root", out var project))
        {
            if (values.Keys.Any(key => key.StartsWith("--managed-")))
                throw new ArgumentException("Managed launch options require --managed-project-root.");
            return null;
        }
        if (stateRoot is null) throw new ArgumentException("Managed launch requires an explicit profile.");
        project = ShellProfile.CanonicalRoot(project);
        var shell = values.GetValueOrDefault("--managed-powershell");
        if (string.IsNullOrWhiteSpace(shell))
            throw new ArgumentException("Managed launch requires the explicit trusted PowerShell executable.");
        shell = Path.GetFullPath(shell);
        if (!File.Exists(shell) || !shell.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
            || !File.Exists(Path.Combine(project, "scripts", "start-manual-test.ps1")))
            throw new ArgumentException("Managed launch prerequisites are missing.");
        bool Flag(string name) => values.GetValueOrDefault(name, "false") switch {
            "true" => true, "false" => false, _ => throw new ArgumentException("Invalid managed switch.") };
        string? PathValue(string name) => values.TryGetValue(name, out var path) ? Path.GetFullPath(path) : null;
        var provider = values.GetValueOrDefault("--managed-provider", "auto");
        var discovery = values.GetValueOrDefault("--managed-discovery", "default");
        if (provider is not ("auto" or "deterministic") || discovery is not ("default" or "explicit")
            || !int.TryParse(values.GetValueOrDefault("--managed-timeout", "300"), out var timeout)
            || timeout is < 30 or > 3600)
            throw new ArgumentException("Unsupported managed provider/discovery/timeout.");
        string? ModelValue(string key)
        {
            var value = values.GetValueOrDefault(key);
            if (value is not null && (value.Length is 0 or > 200 || value.Any(char.IsControl)))
                throw new ArgumentException("Invalid managed model identity.");
            return value;
        }
        var model = ModelValue("--managed-model");
        var effort = values.GetValueOrDefault("--managed-antigravity-effort");
        if (effort is not (null or "low" or "medium" or "high"))
            throw new ArgumentException("Unsupported Antigravity effort; Core supports low, medium or high.");
        return new(project, shell, PathValue("--managed-settings"), PathValue("--managed-llama-config"),
            model, values.GetValueOrDefault("--managed-model-url", "http://127.0.0.1:1234/v1"),
            PathValue("--managed-avatar"), PathValue("--managed-workspace"), PathValue("--managed-write-repo"),
            timeout, Flag("--managed-no-avatar"), Flag("--managed-setup-voice"), provider, discovery == "default",
            ModelValue("--managed-codex-model"), ModelValue("--managed-antigravity-model"), effort,
            Flag("--managed-antigravity-skip-permissions"), Flag("--managed-unified-settings-only"));
    }

    public ProcessStartInfo StartInfo(ShellOptions options)
    {
        var start = new ProcessStartInfo(PowerShell) { UseShellExecute = false, CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden, WorkingDirectory = ProjectRoot,
            RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "-NoProfile", "-NonInteractive", "-File",
            Path.Combine(ProjectRoot, "scripts", "start-manual-test.ps1"),
            "-Port", options.CoreUrl.Port.ToString(), "-StateRoot", options.StateRoot!,
            "-TaskTimeout", Timeout.ToString(), "-Provider", Provider }) start.ArgumentList.Add(argument);
        void Add(string key, string? value)
        { if (value is not null) { start.ArgumentList.Add(key); start.ArgumentList.Add(value); } }
        Add("-Settings", Settings); Add("-LlamaConfig", LlamaConfig); Add("-DialogueModel", Model);
        if (Model is not null) Add("-DialogueBaseUrl", ModelUrl);
        Add("-AvatarPath", Avatar); Add("-WorkspaceRoot", Workspace); Add("-WriteRepo", WriteRepo);
        Add("-CodexModel", CodexModel); Add("-AntigravityModel", AntigravityModel);
        Add("-AntigravityEffort", AntigravityEffort);
        if (AntigravitySkipPermissions) start.ArgumentList.Add("-AntigravitySkipPermissions");
        if (UnifiedSettingsOnly) start.ArgumentList.Add("-UnifiedSettingsOnly");
        if (NoAvatar) start.ArgumentList.Add("-NoAvatar");
        if (SetupVoice) start.ArgumentList.Add("-SetupVoice");
        // Do not inherit a stale import path into a profile-owned runtime.
        start.Environment.Remove("PYTHONPATH");
        return start;
    }
}
