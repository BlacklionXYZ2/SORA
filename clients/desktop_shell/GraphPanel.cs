using System.Drawing.Drawing2D;

namespace Sora.DesktopShell;

internal sealed class GraphPanel : Control
{
    public GraphScene Scene { get; }
    public string? SelectedId { get; private set; }
    public event EventHandler? SelectionChanged;
    private float zoom = 1;
    private PointF pan;

    public GraphPanel(GraphScene scene)
    {
        Scene = scene;
        DoubleBuffered = true;
        Dock = DockStyle.Fill;
        TabStop = true;
        AccessibleName = "Fixture relationship graph";
        AccessibleDescription = "Synthetic layout fixture, not SORA memories. Arrow keys select nodes; list provides the same items.";
        AccessibleRole = AccessibleRole.Graphic;
        SelectedId = Scene.Nodes.FirstOrDefault()?.Node.Id;
    }
    public void SelectId(string? id)
    {
        if (id is null || id == SelectedId || !Scene.Nodes.Any(node => node.Node.Id == id)) return;
        SelectedId = id; Invalidate(); SelectionChanged?.Invoke(this, EventArgs.Empty);
    }
    public void Zoom(float factor) { zoom = Math.Clamp(zoom * factor, 0.5f, 3); Invalidate(); }
    public void Centre() { zoom = 1; pan = PointF.Empty; Invalidate(); }
    private PointF Position(PositionedNode node) => new(
        (node.X - 0.5f) * Math.Max(1, Width - 80 * DeviceDpi / 96f) * zoom + Width / 2f + pan.X,
        (node.Y - 0.5f) * Math.Max(1, Height - 60 * DeviceDpi / 96f) * zoom + Height / 2f + pan.Y);

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var edgePen = new Pen(ShellTheme.Secondary, 1);
        foreach (var edge in Scene.Edges)
            e.Graphics.DrawLine(edgePen, Position(Scene.Nodes.First(node => node.Node.Id == edge.From)),
                Position(Scene.Nodes.First(node => node.Node.Id == edge.To)));
        foreach (var node in Scene.Nodes)
        {
            var p = Position(node);
            var scale = DeviceDpi / 96f;
            var bounds = new RectangleF(p.X - 28 * scale, p.Y - 18 * scale, 56 * scale, 36 * scale);
            using var fill = new SolidBrush(ShellTheme.Raised);
            using var border = new Pen(node.Node.Id == SelectedId ? ShellTheme.Accent : ShellTheme.Secondary, 2);
            e.Graphics.FillEllipse(fill, bounds); e.Graphics.DrawEllipse(border, bounds);
            TextRenderer.DrawText(e.Graphics, node.Node.Label, Font, Rectangle.Round(bounds), ShellTheme.Text,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        }
        if (Focused) ControlPaint.DrawFocusRectangle(e.Graphics, Rectangle.Inflate(ClientRectangle, -3, -3));
    }
    protected override void OnMouseDown(MouseEventArgs e)
    {
        base.OnMouseDown(e); Focus();
        var nearest = Scene.Nodes.FirstOrDefault(node => {
            var p = Position(node); return Math.Abs(p.X - e.X) <= 28 * DeviceDpi / 96f
                && Math.Abs(p.Y - e.Y) <= 18 * DeviceDpi / 96f;
        });
        if (nearest is not null) SelectId(nearest.Node.Id);
    }
    protected override bool IsInputKey(Keys keyData) => (keyData & Keys.KeyCode) is
        Keys.Left or Keys.Right or Keys.Up or Keys.Down || base.IsInputKey(keyData);
    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (Scene.Nodes.Count == 0) return;
        if (e.Control && e.KeyCode is Keys.Left or Keys.Right or Keys.Up or Keys.Down)
        {
            pan.X += e.KeyCode == Keys.Left ? 24 : e.KeyCode == Keys.Right ? -24 : 0;
            pan.Y += e.KeyCode == Keys.Up ? 24 : e.KeyCode == Keys.Down ? -24 : 0;
            Invalidate(); e.Handled = true; return;
        }
        if (e.KeyCode is not (Keys.Left or Keys.Right or Keys.Up or Keys.Down)) return;
        var index = Scene.Nodes.ToList().FindIndex(node => node.Node.Id == SelectedId);
        var next = Math.Clamp(index + (e.KeyCode is Keys.Left or Keys.Up ? -1 : 1), 0, Scene.Nodes.Count - 1);
        SelectId(Scene.Nodes[next].Node.Id); e.Handled = true;
    }
}
