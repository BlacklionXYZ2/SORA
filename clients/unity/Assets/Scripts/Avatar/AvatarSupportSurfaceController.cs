using System;
using System.Collections.Generic;
using Sora.Embodiment.Coordinates;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public enum AvatarSupportSurfaceState
    {
        Active,
        Moving,
        Minimized,
        Closed,
        Occluded,
    }

    public sealed class AvatarSupportSurface
    {
        public string SurfaceId { get; }
        public ScreenRect Rect { get; }
        public AvatarSupportSurfaceState State { get; }
        public DateTime ExpiresAtUtc { get; }

        public AvatarSupportSurface(string surfaceId, ScreenRect rect,
            AvatarSupportSurfaceState state, DateTime expiresAtUtc)
        {
            if (string.IsNullOrWhiteSpace(surfaceId))
                throw new ArgumentException("Surface ID is required", nameof(surfaceId));
            if (expiresAtUtc.Kind != DateTimeKind.Utc)
                throw new ArgumentException("Surface expiry must be UTC", nameof(expiresAtUtc));
            SurfaceId = surfaceId;
            Rect = rect;
            State = state;
            ExpiresAtUtc = expiresAtUtc;
        }
    }

    public readonly struct AvatarSupportHit
    {
        public string SurfaceId { get; }
        public string Kind { get; }
        public int AnchorY { get; }

        public AvatarSupportHit(string surfaceId, string kind, int anchorY)
        {
            SurfaceId = surfaceId;
            Kind = kind;
            AnchorY = anchorY;
        }
    }

    /// <summary>
    /// Bounded screen-space support resolver. Monitor/taskbar surfaces come from the
    /// accepted topology; only explicitly selected, short-lived window tops are added.
    /// </summary>
    public sealed class AvatarSupportSurfaceController : MonoBehaviour
    {
        private const int MaximumWindowSurfaces = 32;
        private const int MinimumHalfFootprint = 30;
        private readonly Dictionary<string, AvatarSupportSurface> _windows =
            new Dictionary<string, AvatarSupportSurface>(StringComparer.Ordinal);
        private AvatarLocomotion _motion = null!;
        private AvatarSimplePhysicsController _physics = null!;
        private string? _currentSurfaceId;
        private string? _currentSurfaceKind;

        public string? CurrentSurfaceId => _currentSurfaceId;
        public string? CurrentSurfaceKind => _currentSurfaceKind;
        public int SelectedWindowCount => _windows.Count;
        public event Action<string, string>? SupportRemoved;

        public void Configure(AvatarLocomotion motion, AvatarSimplePhysicsController physics)
        {
            _motion = motion ?? throw new ArgumentNullException(nameof(motion));
            _physics = physics ?? throw new ArgumentNullException(nameof(physics));
            _physics.ConfigureSupportResolver(ResolveSupport);
            _physics.LandedOnSupport += OnLanded;
        }

        public bool ApplySnapshot(IReadOnlyList<AvatarSupportSurface> surfaces,
            int topologyRevision, DateTime utcNow)
        {
            if (_motion == null || surfaces == null || surfaces.Count > MaximumWindowSurfaces ||
                topologyRevision != _motion.Topology.Revision || utcNow.Kind != DateTimeKind.Utc)
                return false;
            var next = new Dictionary<string, AvatarSupportSurface>(StringComparer.Ordinal);
            foreach (var surface in surfaces)
            {
                if (surface == null || next.ContainsKey(surface.SurfaceId)) return false;
                var monitor = _motion.Topology.FindMonitor(surface.Rect.X, surface.Rect.Y);
                if (monitor == null ||
                    !monitor.Rect.Contains(surface.Rect.Right - 1, surface.Rect.Bottom - 1))
                    return false;
                next.Add(surface.SurfaceId, surface);
            }
            _windows.Clear();
            foreach (var pair in next) _windows.Add(pair.Key, pair.Value);
            ReconcileCurrentSupport(utcNow);
            return true;
        }

        public AvatarSupportHit? ResolveSupport(int currentX, int currentY,
            int proposedX, int proposedY)
        {
            if (_motion == null || proposedY < currentY) return null;
            AvatarSupportHit? closest = null;
            foreach (var surface in _windows.Values)
            {
                if (!Available(surface, DateTime.UtcNow) ||
                    proposedX < surface.Rect.X + MinimumHalfFootprint ||
                    proposedX >= surface.Rect.Right - MinimumHalfFootprint)
                    continue;
                int anchor = surface.Rect.Y - 1;
                if (anchor < currentY || anchor > proposedY || !SafeAnchor(proposedX, anchor))
                    continue;
                if (!closest.HasValue || anchor < closest.Value.AnchorY)
                    closest = new AvatarSupportHit(surface.SurfaceId, "window_top", anchor);
            }
            if (closest.HasValue) return closest;

            var monitor = _motion.Topology.FindMonitor(proposedX, currentY) ??
                _motion.Topology.FindMonitor(proposedX, proposedY);
            if (monitor == null) return null;
            int implicitY = monitor.WorkArea.Bottom - 1;
            if (implicitY < currentY || implicitY > proposedY) return null;
            string kind = monitor.WorkArea.Bottom < monitor.Rect.Bottom ?
                "taskbar" : "monitor_bottom";
            return new AvatarSupportHit(kind + ":" + monitor.Id, kind, implicitY);
        }

        public void Tick(DateTime utcNow)
        {
            if (_motion == null || utcNow.Kind != DateTimeKind.Utc) return;
            ReconcileCurrentSupport(utcNow);
        }

        private void OnLanded(Vector2 velocity, AvatarSupportHit hit)
        {
            _currentSurfaceId = hit.SurfaceId;
            _currentSurfaceKind = hit.Kind;
        }

        private void ReconcileCurrentSupport(DateTime utcNow)
        {
            if (string.IsNullOrEmpty(_currentSurfaceId) || _currentSurfaceKind != "window_top")
                return;
            if (!_windows.TryGetValue(_currentSurfaceId!, out var surface) ||
                !Available(surface, utcNow))
            {
                RemoveCurrent(surface?.State.ToString().ToLowerInvariant() ?? "removed");
                return;
            }
            var current = _motion.GetCurrentGlobalPixelPosition();
            int anchor = surface.Rect.Y - 1;
            if (current.GlobalX < surface.Rect.X + MinimumHalfFootprint ||
                current.GlobalX >= surface.Rect.Right - MinimumHalfFootprint ||
                !SafeAnchor(current.GlobalX, anchor))
            {
                RemoveCurrent("moved_out_from_under_avatar");
                return;
            }
            if (current.GlobalY != anchor)
                _motion.TeleportTo(current.GlobalX, anchor);
        }

        private void RemoveCurrent(string reason)
        {
            string removed = _currentSurfaceId!;
            _currentSurfaceId = null;
            _currentSurfaceKind = null;
            SupportRemoved?.Invoke(removed, reason);
            _physics.LoseSupport();
        }

        private bool SafeAnchor(int x, int y)
        {
            var safe = OverlayPlacement.SafeAnchor(_motion.Topology, x, y);
            return safe.X == x && safe.Y == y;
        }

        private static bool Available(AvatarSupportSurface surface, DateTime utcNow) =>
            (surface.State == AvatarSupportSurfaceState.Active ||
                surface.State == AvatarSupportSurfaceState.Moving) &&
            surface.ExpiresAtUtc > utcNow;

        private void Update() => Tick(DateTime.UtcNow);
    }
}
