using System.Text.Json;

Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
Application.EnableVisualStyles();
Application.Run(new Fixture(args[0], args.Contains("--read-selection")));

sealed class Fixture : Form
{
    readonly string evidence;
    readonly bool readSelection;
    readonly Button button = new() { Name = "fixture-confirm", AccessibleName = "Confirm fixture", Text = "Confirm fixture", Bounds = new(30, 40, 170, 40) };
    readonly TextBox text = new() { Name = "fixture-text", AccessibleName = "Fixture text", Text = "before", Bounds = new(30, 100, 240, 30) };
    readonly TextBox password = new() { Name = "fixture-password", AccessibleName = "Private field", Text = "never-export-this", UseSystemPasswordChar = true, Bounds = new(30, 150, 240, 30) };
    int pressCount;
    int textChangeCount;
    public Fixture(string evidence, bool readSelection = false)
    {
        this.evidence = Path.GetFullPath(evidence);
        this.readSelection = readSelection;
        Text = "SORA UIA acceptance fixture";
        StartPosition = FormStartPosition.Manual;
        Bounds = new(150, 150, 480, 300);
        Controls.AddRange(new Control[] { button, text, password });
        text.TextChanged += (_, _) => { textChangeCount++; WriteEvidence(); };
        button.Click += (_, _) =>
        {
            pressCount++;
            button.AccessibleName = pressCount == 1 ? "Confirmed once" : $"Confirmed {pressCount} times";
            button.Text = button.AccessibleName;
            WriteEvidence();
        };
    }
    protected override bool ShowWithoutActivation => true;
    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        if (readSelection) text.Select(0, 3);
        WriteEvidence();
        // Test-only signal deliberately hangs this fixture's UI thread, never another app.
        var timer = new System.Windows.Forms.Timer { Interval = 100 };
        timer.Tick += (_, _) => { if (File.Exists(evidence + ".hang")) Thread.Sleep(Timeout.Infinite); };
        timer.Start();
    }
    void WriteEvidence()
    {
        var rect = button.RectangleToScreen(button.ClientRectangle);
        File.WriteAllText(evidence, JsonSerializer.Serialize(new {
            pid = Environment.ProcessId, hwnd = Handle.ToInt64(), press_count = pressCount,
            button_name = button.AccessibleName,
            text_value = text.Text,
            text_change_count = textChangeCount,
            button = new { x=rect.X, y=rect.Y, width=rect.Width, height=rect.Height }
        }));
    }
}
