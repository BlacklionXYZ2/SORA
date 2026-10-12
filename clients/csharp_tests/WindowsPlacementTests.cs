using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Native;
using Sora.Embodiment.Network;
using Newtonsoft.Json;

public class WindowsPlacementTests
{
    [Theory]
    [InlineData(0, 40, 1920, 1040)]
    [InlineData(0, 0, 1920, 1040)]
    [InlineData(40, 0, 1880, 1080)]
    [InlineData(0, 0, 1880, 1080)]
    public void SafeAnchorKeepsFootprintOutsideAnyTaskbar(int x, int y, int width, int height)
    {
        var rect = new ScreenRect(0, 0, 1920, 1080);
        var work = new ScreenRect(x, y, width, height);
        var topology = new DisplayTopology(rect, new[] { new MonitorDescriptor("primary", true, rect, 1.5f, workArea: work) });
        foreach (var point in new[] { (-1000, -1000), (0, 0), (1919, 1079), (4000, 2000) })
        {
            var safe = OverlayPlacement.SafeAnchor(topology, point.Item1, point.Item2);
            Assert.True(work.Contains(safe.X - 90, safe.Y - 300));
            Assert.True(work.Contains(safe.X + 90, safe.Y));
        }
        var roundtrip = DisplayTopologyDto.FromTopology(topology).Monitors[0].ToDescriptor();
        Assert.Equal(work, roundtrip.WorkArea);
    }

    [Fact]
    public void FirstAppearanceStandsOnThePrimaryTaskbarNotTheTopLeft()
    {
        // The owner's layout: a 4K primary with a bottom taskbar, and a smaller monitor to its left.
        var primary = new MonitorDescriptor("DISPLAY1", true, new ScreenRect(0, 0, 3840, 2160), 1.5f,
            workArea: new ScreenRect(0, 0, 3840, 2088));
        var side = new MonitorDescriptor("DISPLAY6", false, new ScreenRect(-1280, 813, 1280, 1024), 1f,
            workArea: new ScreenRect(-1280, 813, 1280, 976));
        var topology = new DisplayTopology(new ScreenRect(-1280, 0, 5120, 2160), new[] { side, primary });
        var home = OverlayPlacement.HomeAnchor(topology);
        Assert.Equal((3840 - 1 - 3840 / 5, 2087), home);
        Assert.True(primary.WorkArea.Contains(home.X - 90, home.Y - 300));
        // Before the fix, clamping the default origin gave (90, 300): high on the top-left.
        Assert.Equal((90, 300), OverlayPlacement.SafeAnchor(topology, 0, 0));
    }

    [Fact]
    public void HotUnplugAndTinyDisplayRemainBounded()
    {
        var rect = new ScreenRect(-200, -100, 100, 80);
        var topology = new DisplayTopology(rect, new[] { new MonitorDescriptor("tiny", true, rect) });
        var safe = OverlayPlacement.SafeAnchor(topology, 3000, 1000);
        Assert.True(rect.Contains(safe.X, safe.Y));
        Assert.Throws<ArgumentException>(() => new MonitorDescriptor("invalid", true, rect,
            workArea: new ScreenRect(-200, -100, 101, 80)));
    }

    [Fact]
    public void ActualWindowsEnumerationHasConsistentPhysicalBounds()
    {
        if (!OperatingSystem.IsWindows()) return;
        var layout = WindowsDisplayTopology.Read();
        Assert.NotEmpty(layout.Monitors);
        Assert.Single(layout.Monitors, m => m.Primary);
        Assert.True(WindowsDisplayTopology.SameLayout(layout, WindowsDisplayTopology.Read()));
        foreach (var monitor in layout.Monitors)
            Assert.True(monitor.Rect.Contains(monitor.WorkArea.Right - 1, monitor.WorkArea.Bottom - 1));
    }

    [Theory]
    [InlineData("show_marker")]
    [InlineData("hide_marker")]
    [InlineData("presentation_phase")]
    public void PresentationHooksUseLiveTransportAndDeduplicate(string verb)
    {
        using var client = new SoraCoreClient();
        client.ProcessIncomingMessage("{\"type\":\"embodiment.snapshot\",\"projection\":{\"revision\":4}}");
        int count = 0;
        client.OnCommandReceived += _ => count++;
        var message = JsonConvert.SerializeObject(new { type = "embodiment.command", command = new {
            command_id = "marker", verb, topology_revision = 4, created_at = DateTime.UtcNow,
            target_point = new { x = -200, y = 500 }, semantic_action_id = "action", semantic_phase = "reach" } });
        client.ProcessIncomingMessage(message);
        client.ProcessIncomingMessage(message);
        Assert.Equal(1, count);
    }
}
