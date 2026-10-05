namespace Sora.DesktopShell;

// A panel owns only its transient controls. Durable UI state belongs to the profile host/store.
internal sealed class PanelPreferencesBinding : IDisposable
{
    private readonly Form form;
    private readonly string panel;
    private readonly ShellPreferencesStore store;
    private Font? regular;
    private Font? bold;
    private bool restoring;
    private bool shown;
    private double appliedScale;
    private readonly Action? appearance;
    public PanelPreferencesBinding(Form form, string panel, ShellPreferencesStore store, Action? appearance = null)
    {
        this.form = form; this.panel = panel; this.store = store; this.appearance = appearance;
        ApplyAppearance();
        form.Shown += FirstShown;
        form.ResizeEnd += Capture;
        form.FormClosing += Capture;
        form.VisibleChanged += Hidden;
        form.DpiChanged += DpiChanged;
        form.Disposed += FormDisposed;
        store.Changed += Changed;
    }
    private void FirstShown(object? sender, EventArgs args) { shown = true; Restore(); }
    private void Changed(object? sender, EventArgs args) { if (!form.IsDisposed) ApplyAppearance(); }
    public void RefreshAppearance() { if (!form.IsDisposed) ApplyAppearance(); }
    private void ApplyAppearance()
    {
        var preferences = store.Current;
        ShellTheme.Palette = preferences.Theme;
        if (regular is null || appliedScale != preferences.TextScale)
        {
            var oldRegular = regular; var oldBold = bold;
            regular = new Font("Segoe UI", (float)(10.5 * preferences.TextScale));
            bold = new Font(regular, FontStyle.Bold); appliedScale = preferences.TextScale;
            void SetFont(Control control)
            {
                control.Font = control.Font.Bold ? bold : regular;
                foreach (Control child in control.Controls) SetFont(child);
            }
            SetFont(form); oldRegular?.Dispose(); oldBold?.Dispose();
        }
        // WinForms may change z-order even when assigning the same TopMost value. Passive saves
        // and placement capture must not activate/reorder Chat over the panel the user is editing.
        if (panel == "chat" && form.TopMost != preferences.ChatPinned) form.TopMost = preferences.ChatPinned;
        if (appearance is null) ShellTheme.Apply(form); else appearance();
    }
    public void Restore(bool defaults = false)
    {
        if (!shown || form.IsDisposed) return;
        restoring = true;
        try
        {
            var preferences = store.Current;
            preferences.Panels.TryGetValue(panel, out var placement);
            var hint = panel == "chat" ? preferences.LegacyChat : null;
            var monitor = defaults ? null : placement?.Monitor ?? hint?.Monitor;
            var screen = Screen.AllScreens.FirstOrDefault(item => item.DeviceName == monitor)
                ?? Screen.FromControl(form);
            var area = screen.WorkingArea;
            // Move to the selected monitor first so PerMonitorV2 supplies that window's actual DPI.
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(area.Left, area.Top);
            var scale = form.DeviceDpi / 96d;
            var size = panel switch {
                "chat" when preferences.ChatCompact => new Size(460, 560),
                "chat" => new Size(820, 700), "activity" => new Size(920, 700), "agents" => new Size(820, 740),
                "paths" => new Size(1000, 670), "settings" => new Size(1020, 720),
                "board" => preferences.BoardExpanded ? new Size(1120, 700) : new Size(360, 300),
                "content" or "integrations" => new Size(840, 680),
                "voice" => new Size(840, 530),
                "memory" => new Size(1060, 740),
                "appearance" => new Size(600, 640), _ => new Size(460, 350)
            };
            var bounds = new Rectangle(area.Left + (int)(24 * scale), area.Top + (int)(24 * scale),
                (int)(size.Width * scale), (int)(size.Height * scale));
            if (!defaults && placement is not null) bounds = PanelGeometry.Restore(placement, area, form.DeviceDpi);
            else if (!defaults && hint is not null)
            {
                // Legacy physical coordinates have no recorded DPI. Best effort only, then capture logical bounds.
                bounds.Location = hint.X.HasValue ? new Point(hint.X.Value, hint.Y!.Value) : new Point(
                    hint.Anchor is 0 or 2 ? area.Right - bounds.Width - 16 : area.Left + 16,
                    hint.Anchor is 0 or 1 ? area.Bottom - bounds.Height - 16 : area.Top + 16);
            }
            form.MinimumSize = new Size(Math.Min((int)((panel == "board" ? 320 : panel == "settings" ? 720 : panel == "memory" ? 620 : 360) * scale), area.Width), Math.Min((int)((panel == "board" ? 260 : panel == "memory" ? 520 : 350) * scale), area.Height));
            form.Bounds = PanelGeometry.Clamp(bounds, area);
        }
        finally { restoring = false; }
    }
    public void ClampToWorkArea()
    {
        if (!shown || form.IsDisposed || form.WindowState != FormWindowState.Normal) return;
        restoring = true;
        try
        {
            var area = Screen.FromControl(form).WorkingArea;
            form.MinimumSize = new Size(Math.Min(form.MinimumSize.Width, area.Width), Math.Min(form.MinimumSize.Height, area.Height));
            form.Bounds = PanelGeometry.Clamp(form.Bounds, area);
        }
        finally { restoring = false; }
        Capture(null, EventArgs.Empty);
    }
    private void DpiChanged(object? sender, DpiChangedEventArgs args)
    {
        // Apply WinForms' suggested bounds before checking the new monitor/work area.
        if (!form.IsDisposed && form.IsHandleCreated) form.BeginInvoke(ClampToWorkArea);
    }
    private void Hidden(object? sender, EventArgs args) { if (!form.Visible) Capture(sender, args); }
    public void CaptureNow() => Capture(null, EventArgs.Empty);
    private void Capture(object? sender, EventArgs args)
    {
        if (restoring || !shown || form.IsDisposed || form.WindowState != FormWindowState.Normal || store.ReadOnly) return;
        var preferences = store.Current;
        var screen = Screen.FromControl(form);
        var placement = PanelGeometry.Capture(form.Bounds, screen.WorkingArea, screen.DeviceName, form.DeviceDpi);
        if (preferences.Panels.GetValueOrDefault(panel) == placement) return;
        preferences.Panels[panel] = placement;
        store.TrySave(preferences, preferences.Revision, out _); // Error is surfaced by host/preferences, never reset.
    }
    private void FormDisposed(object? sender, EventArgs args) => Dispose();
    public void Dispose()
    {
        store.Changed -= Changed;
        form.Shown -= FirstShown; form.ResizeEnd -= Capture; form.FormClosing -= Capture;
        form.VisibleChanged -= Hidden; form.DpiChanged -= DpiChanged; form.Disposed -= FormDisposed;
        regular?.Dispose(); bold?.Dispose(); regular = null; bold = null;
    }
}
