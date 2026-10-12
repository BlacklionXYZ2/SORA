using System;
using System.Collections.Generic;
using System.Linq;

namespace Sora.Embodiment.Coordinates
{
    /// <summary>Avatar position is the feet anchor. Keep its full rectangular footprint in a work area.</summary>
    public static class OverlayPlacement
    {
        public static (int X, int Y) SafeAnchor(DisplayTopology topology, int x, int y,
            int halfWidth = 90, int height = 300)
        {
            if (halfWidth < 0 || height < 1) throw new ArgumentOutOfRangeException(nameof(height));
            if (topology.Monitors.Count == 0) throw new ArgumentException("Active monitor required");
            if (FootprintCoveredByWorkAreas(topology, x, y, halfWidth, height))
                return (x, y);
            var candidates = topology.Monitors.Select(m =>
            {
                var r = m.WorkArea;
                int marginX = Math.Min(halfWidth, (r.Width - 1) / 2);
                int marginY = Math.Min(height, r.Height - 1);
                int cx = Math.Clamp(x, r.X + marginX, r.Right - 1 - marginX);
                int cy = Math.Clamp(y, r.Y + marginY, r.Bottom - 1);
                double distance = Math.Pow((double)x - cx, 2) + Math.Pow((double)y - cy, 2);
                return (X: cx, Y: cy, Distance: distance);
            }).OrderBy(p => p.Distance).First();
            return (candidates.X, candidates.Y);
        }

        /// <summary>Where she first appears: standing on the primary monitor's work-area floor,
        /// a fifth of the way in from its right edge, clear of the tray icons.</summary>
        public static (int X, int Y) HomeAnchor(DisplayTopology topology)
        {
            if (topology.Monitors.Count == 0) throw new ArgumentException("Active monitor required");
            var work = (topology.Monitors.FirstOrDefault(m => m.Primary) ?? topology.Monitors[0]).WorkArea;
            return SafeAnchor(topology, work.Right - 1 - work.Width / 5, work.Bottom - 1);
        }

        private static bool FootprintCoveredByWorkAreas(DisplayTopology topology, int x, int y,
            int halfWidth, int height)
        {
            int left = x - halfWidth;
            int right = x + halfWidth + 1;
            int top = y - height;
            int bottom = y + 1;
            long required = (long)(right - left) * (bottom - top);
            long covered = 0;
            var edges = new List<int> { left, right };
            foreach (var monitor in topology.Monitors)
            {
                var work = monitor.WorkArea;
                if (work.Right > left && work.X < right)
                {
                    edges.Add(Math.Max(left, work.X));
                    edges.Add(Math.Min(right, work.Right));
                }
            }
            edges = edges.Distinct().OrderBy(value => value).ToList();
            for (int index = 0; index < edges.Count - 1; index++)
            {
                int sliceLeft = edges[index];
                int sliceRight = edges[index + 1];
                var intervals = topology.Monitors
                    .Where(m => m.WorkArea.X < sliceRight && m.WorkArea.Right > sliceLeft)
                    .Select(m => (Top: Math.Max(top, m.WorkArea.Y),
                        Bottom: Math.Min(bottom, m.WorkArea.Bottom)))
                    .Where(interval => interval.Bottom > interval.Top)
                    .OrderBy(interval => interval.Top)
                    .ToList();
                int unionHeight = 0;
                int currentTop = 0;
                int currentBottom = 0;
                foreach (var interval in intervals)
                {
                    if (unionHeight == 0)
                    {
                        currentTop = interval.Top;
                        currentBottom = interval.Bottom;
                        unionHeight = currentBottom - currentTop;
                    }
                    else if (interval.Top > currentBottom)
                    {
                        currentTop = interval.Top;
                        currentBottom = interval.Bottom;
                        unionHeight += currentBottom - currentTop;
                    }
                    else if (interval.Bottom > currentBottom)
                    {
                        unionHeight += interval.Bottom - currentBottom;
                        currentBottom = interval.Bottom;
                    }
                }
                covered += (long)(sliceRight - sliceLeft) * unionHeight;
            }
            return covered >= required;
        }
    }
}
