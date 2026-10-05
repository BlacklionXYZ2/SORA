using System.Drawing;
using System.Text;
using System.Text.Json;
using Sora.DesktopShell;

public sealed class ShellPreferencesTests
{
    private sealed class Profile : IDisposable
    {
        public string Root { get; } = Path.Combine(Path.GetTempPath(), "sora-ui-preferences-test-" + Guid.NewGuid().ToString("N"));
        public Profile() => Directory.CreateDirectory(Root);
        public string Write(string relative, string text, bool bom = false)
        {
            var path = Path.GetFullPath(Path.Combine(Root, relative)); Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, text, new UTF8Encoding(bom)); return path;
        }
        public void Dispose() => Directory.Delete(Root, true); // Only this newly generated private test directory.
    }
    [Fact]
    public void DefaultsAreVersionedUiOnlyAndRoundTrip()
    {
        using var profile = new Profile(); var store = new ShellPreferencesStore(profile.Root);
        Assert.False(store.ReadOnly); Assert.True(store.Current.ImportAttempted); Assert.Equal(1, store.Current.Revision);
        Assert.False(store.Current.ChatPinned); Assert.Equal(ShellShortcut.CtrlAltSpace, store.Current.Shortcut);
        var draft = store.Current with { Theme = ShellPalette.System, TextScale = 1.5, Shortcut = ShellShortcut.None,
            ShowTechnicalDetail = true, ChatPinned = true, ChatCompact = true };
        Assert.True(store.TrySave(draft, draft.Revision, out _));
        var restored = new ShellPreferencesStore(profile.Root);
        Assert.Equal(ShellPalette.System, restored.Current.Theme); Assert.Equal(1.5, restored.Current.TextScale);
        Assert.True(restored.Current.ChatPinned); Assert.Equal(ShellShortcut.None, restored.Current.Shortcut);
        using var document = JsonDocument.Parse(File.ReadAllBytes(store.FilePath));
        Assert.Equal(1, document.RootElement.GetProperty("version").GetInt32());
        foreach (var name in new[] { "token", "model", "voice", "agents", "local_companion", "messages", "draft" })
            Assert.False(document.RootElement.TryGetProperty(name, out _));
    }
    [Fact]
    public void ImportPreservesOriginalBytesAndNeverSilentlyPinsOrReimports()
    {
        using var profile = new Profile();
        var widget = profile.Write("widget/settings.json", "{\"Anchor\":3,\"Monitor\":\"old-monitor\",\"Expanded\":false,"
            + "\"Quiet\":true,\"AlwaysOnTop\":true,\"ShowTechnicalDetail\":false,\"SavedX\":-2200,\"SavedY\":60}");
        var desktop = profile.Write("desktop/settings.json", "{\"ShowTechnicalDetail\":true,\"SelectedTab\":4}");
        var originalWidget = File.ReadAllBytes(widget); var originalDesktop = File.ReadAllBytes(desktop);
        var store = new ShellPreferencesStore(profile.Root);
        Assert.True(store.Current.ChatCompact); Assert.True(store.Current.ShowTechnicalDetail);
        Assert.False(store.Current.ChatPinned); Assert.Empty(store.Current.Panels);
        Assert.Equal(-2200, store.Current.LegacyChat!.X); Assert.Equal(3, store.Current.LegacyChat.Anchor);
        var imports = store.Current.Imports;
        Assert.Equal(2, imports.Length); Assert.All(imports, item => Assert.Equal("imported", item.Status));
        Assert.True(imports[0].Quiet); Assert.True(imports[0].AlwaysOnTop); Assert.Equal(4, imports[1].SelectedTab);
        Assert.Equal(originalWidget, File.ReadAllBytes(imports[0].Backup!));
        Assert.Equal(originalDesktop, File.ReadAllBytes(imports[1].Backup!));
        Assert.Equal(originalWidget, File.ReadAllBytes(widget)); Assert.Equal(originalDesktop, File.ReadAllBytes(desktop));
        var draft = store.Current with { ChatCompact = false, ShowTechnicalDetail = false };
        Assert.True(store.TrySave(draft, draft.Revision, out _));
        profile.Write("widget/settings.json", "{\"Expanded\":false,\"ShowTechnicalDetail\":true}");
        var reopened = new ShellPreferencesStore(profile.Root);
        Assert.False(reopened.Current.ChatCompact); Assert.False(reopened.Current.ShowTechnicalDetail);
        Assert.Equal(2, Directory.GetFiles(Path.Combine(profile.Root, "desktop-shell", "backups")).Length);
    }
    [Theory]
    [InlineData("{bad json")]
    [InlineData("{\"version\":2,\"revision\":7}")]
    [InlineData("{\"version\":1,\"revision\":7,\"model_path\":\"do-not-copy\"}")]
    [InlineData("{\"version\":1,\"version\":1,\"revision\":7}")]
    [InlineData("{\"version\":1,\"revision\":7,\"panels\":null}")]
    [InlineData("{\"revision\":7}")]
    [InlineData("[]")]
    [InlineData("null")]
    [InlineData("\"not an object\"")]
    [InlineData("{\"version\":\"one\",\"revision\":7}")]
    public void InvalidFilesAreReadOnlyAndExplicitRecoveryPreservesBytes(string raw)
    {
        using var profile = new Profile(); var path = profile.Write("desktop-shell/preferences.json", raw);
        var original = File.ReadAllBytes(path); var store = new ShellPreferencesStore(profile.Root);
        Assert.True(store.ReadOnly); Assert.False(store.TrySave(store.Current, 0, out _));
        Assert.Equal(original, File.ReadAllBytes(path)); Assert.Contains("untouched", store.Diagnostic);
        Assert.True(store.TryRecoverDefaults(out var error), error); Assert.False(store.ReadOnly);
        Assert.Equal(original, File.ReadAllBytes(Assert.Single(Directory.GetFiles(Path.Combine(profile.Root, "desktop-shell", "backups")))));
        Assert.False(new ShellPreferencesStore(profile.Root).ReadOnly);
    }
    [Fact]
    public void UnknownLegacyCanonicalFieldsAreNotImportedOrCopied()
    {
        using var profile = new Profile();
        var legacy = profile.Write("widget/settings.json", "{\"Expanded\":true,\"api_token\":\"private-sentinel\"}");
        var original = File.ReadAllBytes(legacy); var store = new ShellPreferencesStore(profile.Root);
        Assert.Equal("invalid", store.Current.Imports[0].Status); Assert.Null(store.Current.Imports[0].Backup);
        Assert.DoesNotContain("private-sentinel", File.ReadAllText(store.FilePath));
        Assert.Equal(original, File.ReadAllBytes(legacy)); Assert.False(store.Current.ChatPinned);
    }
    [Fact]
    public void LegacyUtf8BomFromExistingWriterImportsAndBacksUpByteForByte()
    {
        using var profile = new Profile();
        var path = profile.Write("widget/settings.json", "{\"Expanded\":false,\"ShowTechnicalDetail\":true}", bom: true);
        var original = File.ReadAllBytes(path); Assert.Equal(new byte[] { 0xEF, 0xBB, 0xBF }, original[..3]);
        var store = new ShellPreferencesStore(profile.Root);
        Assert.Equal("imported", store.Current.Imports[0].Status); Assert.True(store.Current.ChatCompact);
        Assert.True(store.Current.ShowTechnicalDetail);
        Assert.Equal(original, File.ReadAllBytes(store.Current.Imports[0].Backup!));
        Assert.Equal(original, File.ReadAllBytes(path));
    }
    [Fact]
    public void ValidUtf8BomUiFileReadsWithoutRecoveryOrSilentReplacement()
    {
        using var profile = new Profile();
        var path = profile.Write("desktop-shell/preferences.json", "{\"version\":1,\"revision\":4,\"text_scale\":1.25}", bom: true);
        var original = File.ReadAllBytes(path); var store = new ShellPreferencesStore(profile.Root);
        Assert.False(store.ReadOnly); Assert.Equal(4, store.Current.Revision); Assert.Equal(1.25, store.Current.TextScale);
        Assert.Equal(original, File.ReadAllBytes(path)); Assert.False(Directory.Exists(Path.Combine(profile.Root, "desktop-shell", "backups")));
    }
    [Fact]
    public void ConcurrentRevisionAndExternalFileChangesRetainDraftAndNewerFile()
    {
        using var profile = new Profile(); var first = new ShellPreferencesStore(profile.Root);
        var second = new ShellPreferencesStore(profile.Root);
        var draft = first.Current with { TextScale = 1.5 };
        var newer = second.Current with { TextScale = 1.25 };
        Assert.True(second.TrySave(newer, newer.Revision, out _)); var bytes = File.ReadAllBytes(first.FilePath);
        Assert.False(first.TrySave(draft, draft.Revision, out var error)); Assert.Contains("changed", error);
        Assert.Equal(1.5, draft.TextScale); Assert.Equal(bytes, File.ReadAllBytes(first.FilePath));
        first.Reload(); Assert.Equal(1.25, first.Current.TextScale);
        Assert.False(first.TrySaveAppearance(draft, draft with { TextScale = 1 }, out _));
    }
    [Fact]
    public void AppearanceDraftMergesUnrelatedPlacementWithoutLosingIt()
    {
        using var profile = new Profile(); var store = new ShellPreferencesStore(profile.Root);
        var baseline = store.Current; var draft = baseline with { TextScale = 1.5 };
        var layout = store.Current; layout.Panels["chat"] = new("monitor", 20, 30, 500, 600, 144);
        Assert.True(store.TrySave(layout, layout.Revision, out _));
        Assert.True(store.TrySaveAppearance(draft, baseline, out var error), error);
        Assert.Equal(layout.Panels["chat"], store.Current.Panels["chat"]); Assert.Equal(1.5, store.Current.TextScale);
        var isolated = store.Current; isolated.Panels.Clear(); Assert.Single(store.Current.Panels);
    }
    [Theory]
    [InlineData(96)] [InlineData(144)] [InlineData(192)]
    public void LogicalPlacementRoundTripsAtDifferentDpiAndNegativeOrigins(int dpi)
    {
        var area = new Rectangle(-3000, -100, 2200, 1500);
        var placement = new PanelPlacement("monitor", 30, 40, 460, 560, 96);
        var restored = PanelGeometry.Restore(placement, area, dpi);
        Assert.Equal(area.Left + 30 * dpi / 96, restored.Left); Assert.Equal(460 * dpi / 96, restored.Width);
        var captured = PanelGeometry.Capture(restored, area, "monitor", dpi);
        Assert.Equal(placement.X, captured.X); Assert.Equal(placement.Y, captured.Y);
        Assert.Equal(placement.Width, captured.Width); Assert.Equal(placement.Height, captured.Height);
    }
    [Fact]
    public void MissingMonitorAndTinyWorkAreaProduceReachablePlacement()
    {
        var area = new Rectangle(0, 40, 320, 240);
        var bounds = PanelGeometry.Restore(new("gone", -9000, 6000, 820, 700, 192), area, 96);
        Assert.Equal(area, bounds); Assert.Equal(area, PanelGeometry.Clamp(new(-999, -999, 500, 500), area));
        var tiny = PanelGeometry.Capture(new Rectangle(0, 0, 80, 60), new Rectangle(0, 0, 80, 60), "tiny", 192);
        new ShellPreferences { Panels = new() { ["chat"] = tiny } }.Validate();
    }
    [Fact]
    public void InvalidNumericBoundsEnumAndRevisionAreRejectedWithoutReplacingFile()
    {
        using var profile = new Profile(); var store = new ShellPreferencesStore(profile.Root);
        var original = File.ReadAllBytes(store.FilePath);
        foreach (var candidate in new[] { store.Current with { TextScale = double.NaN },
            store.Current with { TextScale = 2 }, store.Current with { Theme = (ShellPalette)5 },
            store.Current with { Revision = long.MaxValue }, store.Current with { Panels = new() {
                ["execute"] = new("x", 0, 0, 400, 500, 96) } } })
            Assert.False(store.TrySave(candidate, store.Current.Revision, out _));
        Assert.Equal(original, File.ReadAllBytes(store.FilePath));
    }
    [Fact]
    public void ExplicitLegacyPathsAndAppearanceCommandsStayBoundedToHostMode()
    {
        using var profile = new Profile(); var legacy = profile.Write("old/custom.json", "{\"Expanded\":false}");
        var args = new[] { "--core-url", "http://127.0.0.1:18799", "--token-file", Path.Combine(profile.Root, "token"),
            "--state-root", profile.Root, "--show", "appearance", "--legacy-widget-file", legacy };
        var options = ShellOptions.Parse(args); Assert.Equal(legacy, options.LegacyWidgetFile);
        Assert.True(new HostCommand(1, "p", options.Panel).Valid("p"));
        Assert.Throws<ArgumentException>(() => ShellOptions.Parse(["--core-url", "http://127.0.0.1:18799",
            "--token-file", Path.Combine(profile.Root, "token"), "--legacy-widget-file", legacy]));
        var store = new ShellPreferencesStore(profile.Root, options.LegacyWidgetFile);
        Assert.True(store.Current.ChatCompact); Assert.Equal("imported", store.Current.Imports[0].Status);
    }
    [Fact]
    public void BoardModeAndRetainedPanelBoundsSurviveUiOnlyRestartWithoutCoreData()
    {
        using var profile = new Profile(); var store = new ShellPreferencesStore(profile.Root);
        var values = store.Current with { BoardExpanded = true };
        foreach (var panel in new[] { "board", "content", "integrations" }) values.Panels[panel] = new("fixture", 20, 30, 840, 680, 144);
        Assert.True(store.TrySave(values, values.Revision, out var error), error);
        var restarted = new ShellPreferencesStore(profile.Root);
        Assert.False(restarted.ReadOnly); Assert.True(restarted.Current.BoardExpanded); Assert.Equal(3, restarted.Current.Panels.Count);
        var saved = File.ReadAllText(store.FilePath);
        Assert.DoesNotContain("intent", saved); Assert.DoesNotContain("token", saved); Assert.DoesNotContain("model_path", saved);
    }
    [Fact]
    public void OlderUiStoreWithoutBoardModeRemainsValidAndUnchangedOnRead()
    {
        using var profile = new Profile(); var path = profile.Write("desktop-shell/preferences.json", "{\"version\":1,\"revision\":4,\"import_attempted\":true}");
        var original = File.ReadAllBytes(path); var store = new ShellPreferencesStore(profile.Root);
        Assert.False(store.ReadOnly); Assert.False(store.Current.BoardExpanded); Assert.Equal(4, store.Current.Revision);
        Assert.Equal(original, File.ReadAllBytes(path));
    }
}
