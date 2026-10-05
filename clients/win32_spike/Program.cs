using System;
using System.Collections.Generic;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Sora.Embodiment.Spike
{
    public static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDpiAwarenessContext(IntPtr dpiContext);

        private static readonly IntPtr DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = new IntPtr(-4);

        [STAThread]
        public static int Main(string[] args)
        {
            // Enforce Per-Monitor DPI Awareness V2 for true unscaled physical pixels
            try
            {
                SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
            }
            catch
            {
                // Fallback on older OS versions
            }

            var monitors = NativeMethods.EnumerateMonitors();
            Console.WriteLine($"[SORA SPIKE] Discovered {monitors.Count} active monitor(s) via Win32 EnumDisplayMonitors:");
            for (int i = 0; i < monitors.Count; i++)
            {
                var m = monitors[i];
                Console.WriteLine($"  Monitor {i}: ID={m.DeviceName}, Primary={m.IsPrimary}, Bounds={m.Bounds.X},{m.Bounds.Y} {m.Bounds.Width}x{m.Bounds.Height}");
            }

            int vX = NativeMethods.GetSystemMetrics(NativeMethods.SM_XVIRTUALSCREEN);
            int vY = NativeMethods.GetSystemMetrics(NativeMethods.SM_YVIRTUALSCREEN);
            int vW = NativeMethods.GetSystemMetrics(NativeMethods.SM_CXVIRTUALSCREEN);
            int vH = NativeMethods.GetSystemMetrics(NativeMethods.SM_CYVIRTUALSCREEN);
            Console.WriteLine($"[SORA SPIKE] Virtual Desktop Bounding Box: {vX},{vY} {vW}x{vH}");

            bool headless = args.Length > 0 && args[0] == "--verify";
            string strategy = args.Length > 1 ? args[1].ToLowerInvariant() : "a";

            if (headless)
            {
                Console.WriteLine("[SORA SPIKE] Running automated verification of window hit-testing and coordinate metrics...");
                bool verified = VerifyMetricsAndHitTest(monitors, vX, vY, vW, vH);
                Console.WriteLine($"[SORA SPIKE] Verification result: {(verified ? "PASS" : "FAIL")}");
                return verified ? 0 : 1;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            if (strategy == "b")
            {
                Console.WriteLine("[SORA SPIKE] Launching Strategy B: Single Virtual Desktop Overlay Window");
                var form = new OverlayForm(new Rectangle(vX, vY, vW, vH), "Strategy B (Single Virtual Desktop)");
                Application.Run(form);
            }
            else
            {
                Console.WriteLine("[SORA SPIKE] Launching Strategy A: Per-Monitor Presentation Surfaces");
                var context = new MultiSurfaceApplicationContext(monitors);
                Application.Run(context);
            }

            return 0;
        }

        private static bool VerifyMetricsAndHitTest(List<NativeMethods.MonitorInfo> monitors, int vX, int vY, int vW, int vH)
        {
            if (monitors.Count == 0)
            {
                Console.WriteLine("Error: No monitors detected");
                return false;
            }

            int minX = int.MaxValue, minY = int.MaxValue, maxX = int.MinValue, maxY = int.MinValue;
            bool foundPrimary = false;

            foreach (var m in monitors)
            {
                minX = Math.Min(minX, m.Bounds.X);
                minY = Math.Min(minY, m.Bounds.Y);
                maxX = Math.Max(maxX, m.Bounds.Right);
                maxY = Math.Max(maxY, m.Bounds.Bottom);
                if (m.IsPrimary) foundPrimary = true;
            }

            if (!foundPrimary)
            {
                Console.WriteLine("Error: No primary monitor detected");
                return false;
            }

            // Virtual desktop bounding box check
            if (vX != minX || vY != minY || vW != (maxX - minX) || vH != (maxY - minY))
            {
                Console.WriteLine($"Mismatch between EnumDisplayMonitors bounding box [{minX},{minY} {maxX-minX}x{maxY-minY}] and GetSystemMetrics [{vX},{vY} {vW}x{vH}]");
                return false;
            }

            // Verify WM_NCHITTEST candidate behavior
            var testRect = new Rectangle(minX + 100, minY + 100, 200, 300);
            int hitInside = OverlayForm.SimulateHitTest(testRect, minX + 150, minY + 150);
            int hitOutside = OverlayForm.SimulateHitTest(testRect, minX + 50, minY + 50);

            if (hitInside != NativeMethods.HTCLIENT)
            {
                Console.WriteLine($"Hit test inside visual element failed: expected HTCLIENT (1), got {hitInside}");
                return false;
            }

            if (hitOutside != NativeMethods.HTTRANSPARENT)
            {
                Console.WriteLine($"Hit test outside visual element failed: expected HTTRANSPARENT (-1), got {hitOutside}");
                return false;
            }

            return true;
        }
    }

    public sealed class MultiSurfaceApplicationContext : ApplicationContext
    {
        private readonly List<OverlayForm> _forms = new List<OverlayForm>();

        public MultiSurfaceApplicationContext(List<NativeMethods.MonitorInfo> monitors)
        {
            for (int i = 0; i < monitors.Count; i++)
            {
                var m = monitors[i];
                var form = new OverlayForm(m.Bounds, $"Surface {i} ({m.DeviceName})");
                _forms.Add(form);
                form.FormClosed += (s, e) =>
                {
                    _forms.Remove((OverlayForm)s!);
                    if (_forms.Count == 0) ExitThread();
                };
                form.Show();
            }
        }
    }

    public class OverlayForm : Form
    {
        private readonly Rectangle _surfaceBounds;
        private readonly string _label;
        private Rectangle _avatarVisualRect;
        private int _clickCount = 0;

        public OverlayForm(Rectangle bounds, string label)
        {
            _surfaceBounds = bounds;
            _label = label;

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            Location = bounds.Location;
            Size = bounds.Size;
            TopMost = true;
            ShowInTaskbar = false;
            BackColor = Color.Black;

            // Place test visual representation of SORA in center bottom of this display surface
            int avatarW = 180;
            int avatarH = 320;
            int avatarX = bounds.X + (bounds.Width - avatarW) / 2;
            int avatarY = bounds.Y + bounds.Height - avatarH - 40; // 40px above taskbar
            _avatarVisualRect = new Rectangle(avatarX, avatarY, avatarW, avatarH);

            DoubleBuffered = true;
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);

            // Configure DWM transparency and layered extended style
            int exStyle = NativeMethods.GetWindowLong(Handle, NativeMethods.GWL_EXSTYLE);
            NativeMethods.SetWindowLong(Handle, NativeMethods.GWL_EXSTYLE, exStyle | NativeMethods.WS_EX_LAYERED | NativeMethods.WS_EX_TOPMOST | NativeMethods.WS_EX_TOOLWINDOW);

            // Extend frame into client area for transparency
            var margins = new NativeMethods.MARGINS { cxLeftWidth = -1, cxRightWidth = -1, cyTopHeight = -1, cyBottomHeight = -1 };
            NativeMethods.DwmExtendFrameIntoClientArea(Handle, ref margins);
        }

        public static int SimulateHitTest(Rectangle visualRect, int cursorX, int cursorY)
        {
            return visualRect.Contains(cursorX, cursorY) ? NativeMethods.HTCLIENT : NativeMethods.HTTRANSPARENT;
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == NativeMethods.WM_NCHITTEST)
            {
                // lParam contains screen coordinates (X low-word, Y high-word)
                int screenX = (short)(m.LParam.ToInt64() & 0xFFFF);
                int screenY = (short)((m.LParam.ToInt64() >> 16) & 0xFFFF);

                if (_avatarVisualRect.Contains(screenX, screenY))
                {
                    m.Result = (IntPtr)NativeMethods.HTCLIENT;
                    return;
                }
                else
                {
                    m.Result = (IntPtr)NativeMethods.HTTRANSPARENT;
                    return;
                }
            }

            base.WndProc(ref m);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            _clickCount++;
            Console.WriteLine($"[SORA SPIKE] Click received on avatar! Total clicks: {_clickCount}");
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);

            // Screen to form-local coordinates
            var localAvatar = new Rectangle(
                _avatarVisualRect.X - Location.X,
                _avatarVisualRect.Y - Location.Y,
                _avatarVisualRect.Width,
                _avatarVisualRect.Height
            );

            // Draw avatar visual placeholder
            using var brush = new SolidBrush(Color.FromArgb(230, 80, 140, 240));
            e.Graphics.FillRectangle(brush, localAvatar);

            using var pen = new Pen(Color.White, 2f);
            e.Graphics.DrawRectangle(pen, localAvatar);

            using var font = new Font("Segoe UI", 10f, FontStyle.Bold);
            using var textBrush = new SolidBrush(Color.White);
            e.Graphics.DrawString($"SORA Avatar\nClicks: {_clickCount}\n{_label}", font, textBrush, localAvatar.X + 10, localAvatar.Y + 20);
        }
    }

    public static class NativeMethods
    {
        public const int GWL_EXSTYLE = -20;
        public const int WS_EX_LAYERED = 0x00080000;
        public const int WS_EX_TRANSPARENT = 0x00000020;
        public const int WS_EX_TOPMOST = 0x00000008;
        public const int WS_EX_TOOLWINDOW = 0x00000080;

        public const int WM_NCHITTEST = 0x0084;
        public const int HTTRANSPARENT = -1;
        public const int HTCLIENT = 1;

        public const int SM_XVIRTUALSCREEN = 76;
        public const int SM_YVIRTUALSCREEN = 77;
        public const int SM_CXVIRTUALSCREEN = 78;
        public const int SM_CYVIRTUALSCREEN = 79;

        [DllImport("user32.dll")]
        public static extern int GetSystemMetrics(int nIndex);

        [DllImport("user32.dll")]
        public static extern int GetWindowLong(IntPtr hWnd, int nIndex);

        [DllImport("user32.dll")]
        public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

        [StructLayout(LayoutKind.Sequential)]
        public struct MARGINS
        {
            public int cxLeftWidth;
            public int cxRightWidth;
            public int cyTopHeight;
            public int cyBottomHeight;
        }

        [DllImport("dwmapi.dll")]
        public static extern int DwmExtendFrameIntoClientArea(IntPtr hWnd, ref MARGINS pMarInset);

        public sealed class MonitorInfo
        {
            public string DeviceName { get; set; } = "";
            public Rectangle Bounds { get; set; }
            public Rectangle WorkArea { get; set; }
            public bool IsPrimary { get; set; }
        }

        private delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdcMonitor, ref RECT lprcMonitor, IntPtr dwData);

        [StructLayout(LayoutKind.Sequential)]
        private struct RECT
        {
            public int left;
            public int top;
            public int right;
            public int bottom;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
        private struct MONITORINFOEX
        {
            public int cbSize;
            public RECT rcMonitor;
            public RECT rcWork;
            public int dwFlags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
            public string szDevice;
        }

        [DllImport("user32.dll")]
        private static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr lprcClip, MonitorEnumProc lpfnEnum, IntPtr dwData);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        private static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFOEX lpmi);

        public static List<MonitorInfo> EnumerateMonitors()
        {
            var list = new List<MonitorInfo>();
            EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, (IntPtr hMon, IntPtr hdc, ref RECT rc, IntPtr data) =>
            {
                var mi = new MONITORINFOEX();
                mi.cbSize = Marshal.SizeOf(typeof(MONITORINFOEX));
                if (GetMonitorInfo(hMon, ref mi))
                {
                    list.Add(new MonitorInfo
                    {
                        DeviceName = mi.szDevice,
                        Bounds = new Rectangle(mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right - mi.rcMonitor.left, mi.rcMonitor.bottom - mi.rcMonitor.top),
                        WorkArea = new Rectangle(mi.rcWork.left, mi.rcWork.top, mi.rcWork.right - mi.rcWork.left, mi.rcWork.bottom - mi.rcWork.top),
                        IsPrimary = (mi.dwFlags & 1) != 0,
                    });
                }
                return true;
            }, IntPtr.Zero);
            return list;
        }
    }
}