using System.Text.Json;

Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
Application.EnableVisualStyles();
Application.Run(new InputFixture(args));

sealed class InputFixture : Form
{
    private readonly string evidence;
    private int clicks;
    public InputFixture(string[] args)
    {
        evidence = Path.GetFullPath(args[0]);
        Text = "SORA isolated input acceptance fixture";
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = new Rectangle(int.Parse(args[1]), int.Parse(args[2]), 1200, 800);
        BackColor = Color.White;
        TopMost = true;
        ShowInTaskbar = false;
    }
    protected override bool ShowWithoutActivation => true;
    protected override CreateParams CreateParams
    {
        get { var value = base.CreateParams; value.ExStyle |= 0x08000000; return value; }
    }
    protected override void OnShown(EventArgs e) { base.OnShown(e); Record(); }
    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x0201) { clicks++; Record(); }
        base.WndProc(ref m);
    }
    private void Record() => File.WriteAllText(evidence, JsonSerializer.Serialize(new {
        pid = Environment.ProcessId, hwnd = Handle.ToInt64(), clicks,
        x = Left, y = Top, width = Width, height = Height
    }));
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.DrawString("SORA input test — closes automatically", Font, Brushes.DarkBlue, 12, 12);
    }
}
