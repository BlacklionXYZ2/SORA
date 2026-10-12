using System.Diagnostics;

namespace Sora.DesktopShell;

// The owner's Quit closes every part of SORA this host launched: Core (sora.exe and its Python),
// the llama.cpp server, Laya, the memory embedder, the avatar (SORA.exe) and the voice worker.
// Core records each helper's process ID in <state root>/private/helpers/<name>.pid
// (sora.helper_processes); the
// process tree alone can't find them, because Store Python and the llama.cpp worker break away
// from their parents. A recorded ID is stopped only when the running program has the expected
// name and started after this host launched Core, so a reused ID never hits another program
// (Hermes runs its own llama-server, for example).
public static class HelperCleanup
{
    internal static readonly IReadOnlyDictionary<string, string[]> ExpectedNames =
        new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
        {
            ["core"] = ["python", "python3.12", "sora"],
            ["llama-server"] = ["llama-server"],
            ["embedder"] = ["llama-server"], // the memory manager's EmbeddingGemma server
            ["laya"] = ["laya"],
            ["avatar"] = ["SORA"],
            ["voice"] = ["python", "python3.12"],
        };

    public static string Folder(string stateRoot) => Path.Combine(stateRoot, "private", "helpers");

    // What a recorded helper resolves to: the process to stop, or null when it already ended
    // or the ID now belongs to something else.
    internal static Process? Match(string name, int pid, DateTime launchedAt)
    {
        if (!ExpectedNames.TryGetValue(name, out var names)) return null;
        Process process;
        try { process = Process.GetProcessById(pid); }
        catch (ArgumentException) { return null; }
        try
        {
            if (process.HasExited
                || !names.Contains(process.ProcessName, StringComparer.OrdinalIgnoreCase)
                || process.StartTime < launchedAt.AddSeconds(-2))
            { process.Dispose(); return null; }
            return process;
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception)
        { process.Dispose(); return null; }
    }

    // Stops the recorded helpers that are still running, and returns their names.
    public static IReadOnlyList<string> StopAll(string stateRoot, DateTime launchedAt)
    {
        var stopped = new List<string>();
        var folder = Folder(stateRoot);
        if (!Directory.Exists(folder)) return stopped;
        foreach (var file in Directory.GetFiles(folder, "*.pid"))
        {
            var name = Path.GetFileNameWithoutExtension(file);
            if (!int.TryParse(File.ReadAllText(file).Trim(), out var pid)) continue;
            using var process = Match(name, pid, launchedAt);
            if (process is null) continue;
            try
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(5000);
                stopped.Add(name);
            }
            catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception) { }
        }
        return stopped;
    }
}
