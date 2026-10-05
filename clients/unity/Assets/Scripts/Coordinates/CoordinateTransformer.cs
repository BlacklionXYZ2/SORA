using System;
using System.Collections.Generic;
using System.Linq;

namespace Sora.Embodiment.Coordinates
{
    public readonly struct ScreenRect : IEquatable<ScreenRect>
    {
        public int X { get; }
        public int Y { get; }
        public int Width { get; }
        public int Height { get; }

        public int Right => X + Width;
        public int Bottom => Y + Height;

        public ScreenRect(int x, int y, int width, int height)
        {
            if (width < 1 || height < 1)
                throw new ArgumentException("Width and Height must be positive");
            X = x;
            Y = y;
            Width = width;
            Height = height;
        }

        public bool Contains(int px, int py) => px >= X && px < Right && py >= Y && py < Bottom;

        public bool Equals(ScreenRect other) =>
            X == other.X && Y == other.Y && Width == other.Width && Height == other.Height;

        public override bool Equals(object? obj) => obj is ScreenRect other && Equals(other);

        public override int GetHashCode() => HashCode.Combine(X, Y, Width, Height);
    }

    public sealed class MonitorDescriptor
    {
        public string Id { get; }
        public bool Primary { get; }
        public ScreenRect Rect { get; }
        public ScreenRect WorkArea { get; }
        public float DpiScale { get; }
        public string Orientation { get; }

        public MonitorDescriptor(string id, bool primary, ScreenRect rect, float dpiScale = 1.0f, string orientation = "landscape", ScreenRect? workArea = null)
        {
            Id = id ?? throw new ArgumentNullException(nameof(id));
            Primary = primary;
            Rect = rect;
            WorkArea = workArea ?? rect;
            if (!rect.Contains(WorkArea.X, WorkArea.Y) || !rect.Contains(WorkArea.Right - 1, WorkArea.Bottom - 1))
                throw new ArgumentException("Work area must fit within monitor bounds");
            if (float.IsNaN(dpiScale) || float.IsInfinity(dpiScale) || dpiScale <= 0)
                throw new ArgumentException("DPI scale must be finite and positive");
            DpiScale = dpiScale;
            Orientation = orientation;
        }
    }

    public sealed class DisplayTopology
    {
        public ScreenRect VirtualDesktop { get; }
        public IReadOnlyList<MonitorDescriptor> Monitors { get; }
        public int Revision { get; }

        public DisplayTopology(ScreenRect virtualDesktop, IEnumerable<MonitorDescriptor> monitors, int revision = 1)
        {
            VirtualDesktop = virtualDesktop;
            Monitors = monitors?.ToList() ?? new List<MonitorDescriptor>();
            if (revision < 1) throw new ArgumentException("Revision must be positive");
            Revision = revision;

            if (Monitors.Count > 0)
            {
                var primaries = Monitors.Count(m => m.Primary);
                if (primaries != 1)
                    throw new ArgumentException($"Topology must contain exactly 1 primary monitor, found {primaries}");

                var uniqueIds = new HashSet<string>(Monitors.Select(m => m.Id));
                if (uniqueIds.Count != Monitors.Count)
                    throw new ArgumentException("Monitor IDs must be unique within topology");
                foreach (var monitor in Monitors)
                    if (!VirtualDesktop.Contains(monitor.Rect.X, monitor.Rect.Y) ||
                        !VirtualDesktop.Contains(monitor.Rect.Right - 1, monitor.Rect.Bottom - 1))
                        throw new ArgumentException("Monitor bounds must fit within virtual desktop");
            }
        }

        public MonitorDescriptor? FindMonitor(int x, int y)
        {
            foreach (var m in Monitors)
            {
                if (m.Rect.Contains(x, y))
                    return m;
            }
            return null;
        }

        public bool IsPointOnDisplay(int x, int y) => FindMonitor(x, y) != null;
    }

    public readonly struct UnityWorldPoint
    {
        public float X { get; }
        public float Y { get; }
        public float Z { get; }

        public UnityWorldPoint(float x, float y, float z = 0f)
        {
            if (float.IsNaN(x) || float.IsInfinity(x) || float.IsNaN(y) ||
                float.IsInfinity(y) || float.IsNaN(z) || float.IsInfinity(z))
                throw new ArgumentException("World coordinates must be finite");
            X = x;
            Y = y;
            Z = z;
        }
    }

    public sealed class CoordinateTransformer
    {
        public float BasePixelsPerMeter { get; }

        public CoordinateTransformer(float basePixelsPerMeter = 500.0f)
        {
            if (float.IsNaN(basePixelsPerMeter) || float.IsInfinity(basePixelsPerMeter) || basePixelsPerMeter <= 0)
                throw new ArgumentException("BasePixelsPerMeter must be positive", nameof(basePixelsPerMeter));
            BasePixelsPerMeter = basePixelsPerMeter;
        }

        public (MonitorDescriptor Monitor, int LocalX, int LocalY)? GlobalToMonitorLocal(int globalX, int globalY, DisplayTopology topology)
        {
            var monitor = topology.FindMonitor(globalX, globalY);
            if (monitor == null)
                return null;

            int localX = globalX - monitor.Rect.X;
            int localY = globalY - monitor.Rect.Y;
            return (monitor, localX, localY);
        }

        public (int GlobalX, int GlobalY) MonitorLocalToGlobal(string monitorId, int localX, int localY, DisplayTopology topology)
        {
            var monitor = topology.Monitors.FirstOrDefault(m => m.Id == monitorId)
                ?? throw new KeyNotFoundException($"Monitor {monitorId} not found in topology");

            return (monitor.Rect.X + localX, monitor.Rect.Y + localY);
        }

        public UnityWorldPoint GlobalToWorld(int globalX, int globalY, DisplayTopology topology)
        {
            var primary = topology.Monitors.FirstOrDefault(m => m.Primary)
                ?? throw new InvalidOperationException("Topology has no active monitors");
            return new UnityWorldPoint((globalX - primary.Rect.X) / BasePixelsPerMeter,
                -(globalY - primary.Rect.Y) / BasePixelsPerMeter, 0f);
        }

        public (int GlobalX, int GlobalY) WorldToGlobal(UnityWorldPoint worldPt, DisplayTopology topology, string? targetMonitorId = null)
        {
            var primary = topology.Monitors.FirstOrDefault(m => m.Primary)
                ?? throw new InvalidOperationException("Topology has no active monitors");
            if (targetMonitorId != null && !topology.Monitors.Any(m => m.Id == targetMonitorId))
                throw new KeyNotFoundException($"Monitor {targetMonitorId} not found in topology");
            return ((int)Math.Round(worldPt.X * BasePixelsPerMeter + primary.Rect.X),
                (int)Math.Round(-worldPt.Y * BasePixelsPerMeter + primary.Rect.Y));
        }
    }

    public sealed class DisplayTopologyManager
    {
        public DisplayTopology Topology { get; private set; }
        public int Revision => Topology.Revision;

        public DisplayTopologyManager(DisplayTopology? initialTopology = null)
        {
            Topology = initialTopology ?? new DisplayTopology(
                new ScreenRect(0, 0, 1920, 1080),
                new[] { new MonitorDescriptor("PRIMARY", true, new ScreenRect(0, 0, 1920, 1080)) },
                1
            );
        }

        public (int ClampedX, int ClampedY) ClampToNearestDisplay(int x, int y)
        {
            if (Topology.IsPointOnDisplay(x, y))
                return (x, y);

            int bestX = x;
            int bestY = y;
            float bestDist = float.MaxValue;

            foreach (var m in Topology.Monitors)
            {
                int cx = Math.Clamp(x, m.Rect.X, m.Rect.Right - 1);
                int cy = Math.Clamp(y, m.Rect.Y, m.Rect.Bottom - 1);
                float dist = MathF.Sqrt(MathF.Pow(x - cx, 2) + MathF.Pow(y - cy, 2));
                if (dist < bestDist)
                {
                    bestDist = dist;
                    bestX = cx;
                    bestY = cy;
                }
            }

            return (bestX, bestY);
        }
    }
}
