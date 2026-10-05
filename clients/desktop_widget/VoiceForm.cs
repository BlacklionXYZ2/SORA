using System.Text.Json;

namespace Sora.DesktopWidget;

/// <summary>Shared Windows press-to-talk surface. PCM never enters this GUI or Core HTTP.</summary>
public sealed class VoiceForm : Form
{
    private readonly WidgetSync sync;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 700 };
    private readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = false };
    private readonly TextBox devices = new() { Dock = DockStyle.Fill, Multiline = true,
        ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false };
    private readonly Button start = new() { Text = "Start voice", AutoSize = true };
    private readonly Button talk = new() { Text = "Hold to talk", AutoSize = true, Enabled = false,
        AccessibleName = "Hold to record speech, release to send" };
    private readonly Button stop = new() { Text = "Stop response", AutoSize = true };
    private readonly Button disconnect = new() { Text = "Close audio", AutoSize = true };
    private bool polling, pressed, beginning, closing, mayClose;

    public VoiceForm(WidgetSync sync)
    {
        this.sync = sync;
        Text = "SORA · Local voice";
        Font = new Font("Segoe UI", 10);
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96, 96);
        Size = new Size(760, 420);
        MinimumSize = new Size(590, 400);
        StartPosition = FormStartPosition.CenterParent;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14),
            ColumnCount = 1, RowCount = 4 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 76));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 52));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 96));
        layout.Controls.Add(status, 0, 0);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill };
        buttons.Controls.AddRange([start, talk, stop, disconnect]);
        layout.Controls.Add(buttons, 0, 1);
        layout.Controls.Add(devices, 0, 2);
        layout.Controls.Add(new Label { Dock = DockStyle.Fill, AutoSize = false,
            Text = "Microphone opens only while held (or until the recording limit). Release sends speech. " +
                "Hold again to interrupt. Local models and device keys are editable in Settings → Voice. " +
                "Closing this window stops local audio for all SORA windows." }, 0, 3);
        Controls.Add(layout);
        start.Click += async (_, _) => await Act("start");
        stop.Click += async (_, _) => { pressed = false; await Act("stop"); };
        disconnect.Click += async (_, _) => { pressed = false; await Act("close"); };
        talk.MouseDown += async (_, e) => { if (e.Button == MouseButtons.Left) await Begin(); };
        talk.MouseUp += async (_, e) => { if (e.Button == MouseButtons.Left) await End(); };
        talk.MouseCaptureChanged += async (_, _) => { if (pressed && !talk.Capture) await End(); };
        talk.KeyDown += async (_, e) => {
            if (e.KeyCode == Keys.Space) { e.Handled = true; if (!pressed) await Begin(); }
        };
        talk.KeyUp += async (_, e) => {
            if (e.KeyCode == Keys.Space) { e.Handled = true; await End(); }
        };
        talk.KeyPress += (_, e) => { if (e.KeyChar == ' ') e.Handled = true; };
        talk.LostFocus += async (_, _) => { if (pressed) await End(); };
        Deactivate += async (_, _) => { if (pressed) await End(); };
        timer.Tick += async (_, _) => await RefreshStatus();
        Shown += async (_, _) => { timer.Start(); await RefreshStatus(); };
        FormClosing += async (_, e) => {
            if (mayClose) return;
            e.Cancel = true;
            if (closing) return;
            closing = true; pressed = false; timer.Stop();
            await Act("close");
            mayClose = true; Close();
        };
        FormClosed += (_, _) => timer.Dispose();
    }

    private async Task Begin()
    {
        if (pressed || beginning) return;
        pressed = true; beginning = true;
        try
        {
            if (!await Act("begin")) pressed = false;
            else if (!pressed) await Act("end"); // Release can overtake the begin HTTP response.
        }
        finally { beginning = false; }
    }

    private async Task End()
    {
        if (!pressed) return;
        pressed = false;
        if (!beginning) await Act("end");
    }

    private async Task<bool> Act(string action)
    {
        try { Render(await sync.VoiceActionAsync(action)); return true; }
        catch (Exception error) { status.Text = error.Message; return false; }
    }

    private async Task RefreshStatus()
    {
        if (polling || closing) return;
        polling = true;
        try { Render(await sync.VoiceStatusAsync()); }
        catch (Exception error) { status.Text = "Voice connection unavailable: " + error.Message; talk.Enabled = false; }
        finally { polling = false; }
    }

    private void Render(JsonElement data)
    {
        if (IsDisposed) return;
        var state = data.GetProperty("state").GetString() ?? "stopped";
        bool enabled = !data.TryGetProperty("enabled", out var flag) || flag.GetBoolean();
        status.Text = enabled ? $"{state}: {data.GetProperty("message").GetString()}"
            : "Voice is disabled in Settings. Microphone is closed.";
        talk.Enabled = enabled && state is "ready" or "recording" or "thinking" or "speaking" or "transcribing";
        talk.Text = state == "recording" ? "Release to send" : "Hold to talk";
        start.Enabled = enabled && state is "stopped" or "error";
        stop.Enabled = enabled && data.GetProperty("running").GetBoolean();
        var lines = data.GetProperty("devices").EnumerateArray().Select(d =>
            $"{d.GetProperty("key").GetString()}  · input {d.GetProperty("input_channels").GetInt32()} / output {d.GetProperty("output_channels").GetInt32()}");
        string inventory = "Device keys — copy the desired key into Settings → Voice:\r\n" + string.Join("\r\n", lines);
        if (devices.Text != inventory) devices.Text = inventory;
    }
}
