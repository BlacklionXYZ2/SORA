using System.Diagnostics;
using Sora.DesktopShell;

public sealed class HelperCleanupTests
{
    private static Process StartIdle() => Process.Start(new ProcessStartInfo("cmd.exe", "/c ping -n 30 127.0.0.1 >nul")
        { CreateNoWindow = true, UseShellExecute = false })!;

    [Fact]
    public void A_recorded_id_now_held_by_another_program_is_left_running()
    {
        var root = Directory.CreateTempSubdirectory("sora-helpers-").FullName;
        using var other = StartIdle();
        try
        {
            Directory.CreateDirectory(HelperCleanup.Folder(root));
            // Recorded as SORA's llama-server, but the ID belongs to cmd.exe (e.g. reused).
            File.WriteAllText(Path.Combine(HelperCleanup.Folder(root), "llama-server.pid"), other.Id.ToString());
            Assert.Empty(HelperCleanup.StopAll(root, DateTime.Now.AddMinutes(-1)));
            Assert.False(other.HasExited);
        }
        finally { other.Kill(entireProcessTree: true); Directory.Delete(root, true); }
    }

    [Fact]
    public void Only_helpers_started_after_the_launch_match()
    {
        using var self = Process.GetCurrentProcess();
        Assert.Null(HelperCleanup.Match("unknown", self.Id, DateTime.Now.AddDays(-1)));
        Assert.Null(HelperCleanup.Match("laya", self.Id, DateTime.Now.AddDays(-1))); // wrong name
        Assert.Null(HelperCleanup.Match("laya", int.MaxValue - 7, DateTime.Now)); // gone
        Assert.Contains("llama-server", HelperCleanup.ExpectedNames["llama-server"]);
        Assert.Contains("SORA", HelperCleanup.ExpectedNames["avatar"]);
    }
}
