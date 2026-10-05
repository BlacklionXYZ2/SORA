using System.Text.Json;
using Sora.DesktopApp;

public sealed class SettingsLaunchTests
{
    private static string[] Args => ["C:\\models with spaces\\llama-server.exe", "--model", "C:\\models\\a.gguf", "--mmproj", "C:\\models\\mmproj.gguf",
        "--host", "127.0.0.1", "--alias", "sora-local", "--ctx-size", "8192", "--no-webui"];
    private static JsonElement Projection(object? active, int version = 1, string note = "Core capture, not OS attestation") => JsonSerializer.SerializeToElement(new {
        launch_details = new { version, active = new { argv = active, note },
            next_reload = new { argv = Args, note = "Saved model values, current boot settings; not loaded" },
            next_start = new { argv = Args, note = "Saved boot settings; not loaded" },
            environment = new { LLAMA_API_KEY = "must-not-appear" }, raw_log = "private prompt must-not-appear" }
    });
    [Fact]
    public void LaunchDetailsAreLabelledReadOnlyAndExcludeUnknownPrivatePayloads()
    {
        string text = SettingsLaunchPresentation.Format(Projection(Args), true);
        Assert.Contains("Current Core projection", text); Assert.Contains("Read-only argument arrays", text);
        Assert.Contains("Core-captured submitted", text); Assert.Contains("next model reload", text); Assert.Contains("next Core start", text);
        Assert.Contains("llama-server.exe", text); Assert.Contains("not loaded", text); Assert.DoesNotContain("must-not-appear", text);
    }
    [Theory]
    [InlineData("credential")] [InlineData("duplicate")] [InlineData("missing-value")] [InlineData("bad-bind")]
    [InlineData("control")] [InlineData("non-string")] [InlineData("oversized")] [InlineData("unknown-flag")]
    public void UnsafeOrMalformedArgumentsAreNotDisplayed(string reason)
    {
        var args = Args.ToList(); object value = args;
        if (reason == "credential") args.AddRange(["--api-key", "must-not-appear"]);
        if (reason == "duplicate") args.AddRange(["--ctx-size", "16384"]);
        if (reason == "missing-value") args.Add("--ctx-size");
        if (reason == "bad-bind") args[args.IndexOf("--host") + 1] = "0.0.0.0";
        if (reason == "control") args[0] = "C:\\model\nmust-not-appear";
        if (reason == "non-string") value = new object[] { 3, "must-not-appear" };
        if (reason == "oversized") args[0] = new string('x', 32769);
        if (reason == "unknown-flag") args.AddRange(["--unknown", "must-not-appear"]);
        string text = SettingsLaunchPresentation.Format(Projection(value), true);
        Assert.Contains("failed display validation", text); Assert.DoesNotContain("must-not-appear", text);
    }
    [Fact]
    public void MissingOldStoppedAndStaleDetailsNeverInventARunningCommand()
    {
        Assert.Contains("not supplied", SettingsLaunchPresentation.Format(JsonSerializer.SerializeToElement(new { }), true));
        Assert.Contains("not supplied", SettingsLaunchPresentation.Format(Projection(Args, version: 2), true));
        Assert.Contains("Arguments unavailable", SettingsLaunchPresentation.Format(Projection(null), true));
        Assert.Contains("Last-known / unconfirmed", SettingsLaunchPresentation.Format(Projection(Args), false));
        Assert.Contains("incomplete/unsupported", SettingsLaunchPresentation.Format(Projection(Args, note: "bad\nmetadata"), true));
    }
    [Fact]
    public void SaveChecksRetainedDraftEpochBeforeAdmissionNotOnlyAfterAcknowledgement()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "old"); draft.Edit();
        // A modal editor could otherwise defer observation of an equal-revision replacement Core.
        Assert.Throws<InvalidOperationException>(() => draft.BeginSave("new"));
        Assert.True(draft.Dirty); Assert.False(draft.Busy); Assert.Equal("old", draft.Epoch);
        var submitted = draft.BeginSave("old"); Assert.Equal("old", submitted.Epoch);
    }
}
