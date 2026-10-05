namespace Sora.DesktopShell;

internal static class ShellTheme
{
    public static ShellPalette Palette { get; set; } = ShellPalette.Dark;
    private static bool SystemPalette => SystemInformation.HighContrast || Palette == ShellPalette.System;
    public static Color Surface => SystemPalette ? SystemColors.Window : Color.FromArgb(0x11, 0x1B, 0x2B);
    public static Color Raised => SystemPalette ? SystemColors.Control : Color.FromArgb(0x1A, 0x28, 0x3B);
    public static Color Text => SystemPalette ? SystemColors.WindowText : Color.FromArgb(0xED, 0xF3, 0xFB);
    public static Color Secondary => SystemPalette ? SystemColors.WindowText : Color.FromArgb(0xAA, 0xB9, 0xCC);
    public static Color Accent => SystemPalette ? SystemColors.Highlight : Color.FromArgb(0x48, 0xC7, 0xF0);

    public static Button Button(string text, string name)
    {
        var button = new ShellButton { Text = text, AccessibleName = name, AutoSize = true,
            MinimumSize = new Size(36, 36), Padding = new Padding(8, 3, 8, 3),
            BackColor = Raised, ForeColor = Text, FlatStyle = FlatStyle.Flat };
        button.FlatAppearance.BorderColor = Accent;
        return button;
    }
    public static void Apply(Control control)
    {
        control.BackColor = control is TextBoxBase or ListBox ? Raised : Surface;
        control.ForeColor = Text;
        if (control is Button button) button.FlatAppearance.BorderColor = Accent;
        if (control is DataGridView grid)
        {
            grid.EnableHeadersVisualStyles = false;
            grid.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.DisplayedCells;
            grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            grid.BackgroundColor = Surface;
            grid.DefaultCellStyle.BackColor = Raised; grid.DefaultCellStyle.ForeColor = Text;
            grid.DefaultCellStyle.SelectionBackColor = SystemPalette ? SystemColors.Highlight : Accent;
            grid.DefaultCellStyle.SelectionForeColor = SystemPalette ? SystemColors.HighlightText : Surface;
            grid.ColumnHeadersDefaultCellStyle.BackColor = Surface; grid.ColumnHeadersDefaultCellStyle.ForeColor = Text;
        }
        foreach (Control child in control.Controls) Apply(child);
        control.Invalidate();
    }
}

// Retain native Button semantics/accessibility, but keep disabled text legible on dark surfaces.
internal sealed class ShellButton : Button
{
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.Clear(ShellTheme.Raised);
        using var border = new Pen(Enabled ? ShellTheme.Accent : ShellTheme.Secondary, DeviceDpi / 96f);
        e.Graphics.DrawRectangle(border, 0, 0, Math.Max(0, Width - 1), Math.Max(0, Height - 1));
        TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle,
            Enabled ? ShellTheme.Text : ShellTheme.Secondary,
            TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine
                | (AutoEllipsis ? TextFormatFlags.EndEllipsis : TextFormatFlags.Default));
        if (Focused && ShowFocusCues)
            ControlPaint.DrawFocusRectangle(e.Graphics, Rectangle.Inflate(ClientRectangle, -4, -4), ShellTheme.Text, ShellTheme.Raised);
    }
}
