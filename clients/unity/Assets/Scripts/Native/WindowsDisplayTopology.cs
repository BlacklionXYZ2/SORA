using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Runtime.InteropServices;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Native
{
    /// <summary>Physical Win32 monitor/work-area enumeration; no Unity or desktop capture.</summary>
    public static class WindowsDisplayTopology
    {
        [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct MonitorInfo
        {
            public int Size;
            public Rect Monitor, Work;
            public uint Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Device;
        }
        private delegate bool MonitorCallback(IntPtr monitor, IntPtr dc, ref Rect rect, IntPtr data);
        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool EnumDisplayMonitors(IntPtr dc, IntPtr clip, MonitorCallback callback, IntPtr data);
        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);
        [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
        [DllImport("shcore.dll")] private static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint x, out uint y);

        public static DisplayTopology Read()
        {
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                throw new PlatformNotSupportedException("Windows monitor discovery requires Windows");
            // Restore caller's context even on failure; all positions below are physical pixels.
            var previous = SetThreadDpiAwarenessContext(new IntPtr(-4));
            if (previous == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                var monitors = new List<MonitorDescriptor>();
                int error = 0;
                MonitorCallback callback = (IntPtr handle, IntPtr dc, ref Rect rect, IntPtr data) =>
                {
                    var info = new MonitorInfo { Size = Marshal.SizeOf<MonitorInfo>(), Device = "" };
                    if (!GetMonitorInfo(handle, ref info)) { error = Marshal.GetLastWin32Error(); return false; }
                    var dpiResult = GetDpiForMonitor(handle, 0, out uint dpiX, out _);
                    if (dpiResult != 0) { error = dpiResult; return false; }
                    var bounds = Convert(info.Monitor);
                    monitors.Add(new MonitorDescriptor(info.Device.Replace("\\", "").Replace(".", ""),
                        (info.Flags & 1) != 0, bounds, dpiX / 96f,
                        bounds.Height > bounds.Width ? "portrait" : "landscape", Convert(info.Work)));
                    return true;
                };
                if (!EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, callback, IntPtr.Zero) || error != 0)
                    throw new Win32Exception(error == 0 ? Marshal.GetLastWin32Error() : error);
                if (monitors.Count == 0) throw new InvalidOperationException("No active monitors");
                monitors.Sort((a, b) => string.CompareOrdinal(a.Id, b.Id));
                int x = monitors.Min(m => m.Rect.X), y = monitors.Min(m => m.Rect.Y);
                return new DisplayTopology(new ScreenRect(x, y, monitors.Max(m => m.Rect.Right) - x,
                    monitors.Max(m => m.Rect.Bottom) - y), monitors);
            }
            finally { SetThreadDpiAwarenessContext(previous); }
        }

        private static ScreenRect Convert(Rect r) => new ScreenRect(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);

        public static bool SameLayout(DisplayTopology a, DisplayTopology b) =>
            a.VirtualDesktop.Equals(b.VirtualDesktop) && a.Monitors.Count == b.Monitors.Count &&
            a.Monitors.All(m => b.Monitors.Any(n => m.Id == n.Id && m.Primary == n.Primary &&
                m.Rect.Equals(n.Rect) && m.WorkArea.Equals(n.WorkArea) && m.DpiScale == n.DpiScale &&
                m.Orientation == n.Orientation));
    }
}
