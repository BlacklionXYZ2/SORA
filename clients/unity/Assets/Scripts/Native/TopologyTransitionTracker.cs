using System;
using System.Collections.Generic;
using System.Linq;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Native
{
    [Flags]
    public enum TopologyChangeKind
    {
        None = 0,
        Initial = 1,
        Resolution = 2,
        Dpi = 4,
        Hotplug = 8,
        Orientation = 16,
        WorkArea = 32,
        Resume = 64,
    }

    /// <summary>
    /// Classifies native display transitions without inventing hardware evidence.
    /// The previous usable layout is retained while display discovery is unavailable so
    /// resume can safely relocate the avatar from its last physical-pixel anchor.
    /// </summary>
    public sealed class TopologyTransitionTracker
    {
        private DisplayTopology? _current;
        private bool _unavailable;

        public DisplayTopology? Current => _current;
        public bool IsUnavailable => _unavailable;

        public bool MarkUnavailable()
        {
            if (_unavailable) return false;
            _unavailable = true;
            return true;
        }

        public TopologyChangeKind Observe(DisplayTopology next)
        {
            if (next == null) throw new ArgumentNullException(nameof(next));
            TopologyChangeKind change = TopologyChangeKind.None;
            if (_current == null)
            {
                change = TopologyChangeKind.Initial;
            }
            else
            {
                var previousById = _current.Monitors.ToDictionary(m => m.Id);
                var nextById = next.Monitors.ToDictionary(m => m.Id);
                if (!previousById.Keys.OrderBy(id => id).SequenceEqual(
                    nextById.Keys.OrderBy(id => id)))
                    change |= TopologyChangeKind.Hotplug;

                if (!_current.VirtualDesktop.Equals(next.VirtualDesktop) ||
                    previousById.Keys.Intersect(nextById.Keys).Any(id =>
                        !previousById[id].Rect.Equals(nextById[id].Rect)))
                    change |= TopologyChangeKind.Resolution;

                foreach (var id in previousById.Keys.Intersect(nextById.Keys))
                {
                    var previous = previousById[id];
                    var current = nextById[id];
                    if (previous.DpiScale != current.DpiScale)
                        change |= TopologyChangeKind.Dpi;
                    if (!string.Equals(previous.Orientation, current.Orientation,
                        StringComparison.Ordinal))
                        change |= TopologyChangeKind.Orientation;
                    if (!previous.WorkArea.Equals(current.WorkArea))
                        change |= TopologyChangeKind.WorkArea;
                }
            }

            if (_unavailable)
                change |= TopologyChangeKind.Resume;
            _unavailable = false;
            if (change != TopologyChangeKind.None)
                _current = next;
            return change;
        }
    }
}
