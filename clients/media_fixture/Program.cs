using System.Diagnostics;
using System.Text.Json;

if (args.Length is not (1 or 3))
    throw new ArgumentException("An evidence path and optional x/y coordinates are required.");
int? left = args.Length == 3 ? int.Parse(args[1]) : null;
int? top = args.Length == 3 ? int.Parse(args[2]) : null;
Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
Application.EnableVisualStyles();
Application.Run(new MediaFixture(args[0], left, top));

sealed class MediaFixture : Form
{
    readonly string evidencePath;
    readonly Button toggle = new()
    {
        Name = "media-pause",
        AccessibleName = "Pause deterministic media",
        Text = "Pause",
        Bounds = new(30, 70, 220, 48),
    };
    readonly Label state = new()
    {
        Name = "media-state",
        AccessibleName = "Playback state: Playing",
        Text = "Playing",
        Bounds = new(30, 25, 220, 30),
    };
    readonly Stopwatch activeSegment = Stopwatch.StartNew();
    readonly System.Windows.Forms.Timer sampleTimer = new() { Interval = 50 };
    long accumulatedMilliseconds;
    int pressCount;
    bool playing = true;

    public MediaFixture(string evidence, int? left, int? top)
    {
        evidencePath = Path.GetFullPath(evidence);
        Text = "SORA deterministic media fixture";
        StartPosition = FormStartPosition.Manual;
        Bounds = new Rectangle(left ?? 220, top ?? 180, 360, 220);
        Controls.AddRange(new Control[] { state, toggle });
        toggle.Click += (_, _) => TogglePlayback();
        sampleTimer.Tick += (_, _) => WriteEvidence();
    }

    protected override bool ShowWithoutActivation => true;

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        WriteEvidence();
        sampleTimer.Start();
    }

    long PositionMilliseconds => accumulatedMilliseconds +
        (playing ? activeSegment.ElapsedMilliseconds : 0);

    void TogglePlayback()
    {
        pressCount++;
        if (playing)
        {
            accumulatedMilliseconds += activeSegment.ElapsedMilliseconds;
            activeSegment.Reset();
            playing = false;
        }
        else
        {
            activeSegment.Restart();
            playing = true;
        }
        state.Text = playing ? "Playing" : "Paused";
        state.AccessibleName = "Playback state: " + state.Text;
        toggle.Text = playing ? "Pause" : "Resume";
        toggle.AccessibleName = playing ? "Pause deterministic media" :
            "Resume deterministic media";
        WriteEvidence();
    }

    void WriteEvidence()
    {
        var rect = toggle.RectangleToScreen(toggle.ClientRectangle);
        var payload = JsonSerializer.Serialize(new
        {
            pid = Environment.ProcessId,
            hwnd = Handle.ToInt64(),
            playback_state = playing ? "playing" : "paused",
            position_ms = PositionMilliseconds,
            press_count = pressCount,
            button_name = toggle.AccessibleName,
            state_name = state.AccessibleName,
            button = new { x = rect.X, y = rect.Y, width = rect.Width, height = rect.Height },
        });
        Directory.CreateDirectory(Path.GetDirectoryName(evidencePath)!);
        File.WriteAllText(evidencePath, payload);
    }
}
