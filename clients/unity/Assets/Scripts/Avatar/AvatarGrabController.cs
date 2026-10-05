using System;
using Sora.Embodiment.Coordinates;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Local presentation-only avatar manipulation. It never injects desktop input or
    /// grants authority to an embodied semantic action.
    /// </summary>
    public sealed class AvatarGrabController : MonoBehaviour
    {
        [SerializeField] private float springPerSecondSquared = 85f;
        [SerializeField] private float dampingPerSecond = 18f;
        [SerializeField] private float maximumDragSpeedPxPerSecond = 4000f;
        [SerializeField] private float maximumReleaseSpeedPxPerSecond = 1400f;
        [SerializeField] private float releaseDampingPerSecond = 7f;
        [SerializeField] private float releaseStopSpeedPxPerSecond = 8f;
        [SerializeField] private float clickTravelThresholdPx = 6f;

        private AvatarLocomotion _motion = null!;
        private Func<bool> _canBegin = () => true;
        private Vector2 _bodyAnchorOffset;
        private Vector2 _velocity;
        private Vector2 _pointerStart;
        private float _maximumPointerTravel;

        public bool IsGrabbed { get; private set; }
        public bool HasReleaseInertia { get; private set; }
        public Vector2 VelocityPixelsPerSecond => _velocity;
        public event Action? Grabbed;
        public event Action<Vector2>? Released;
        public event Action? Clicked;
        public event Action? Poked;

        public void Configure(AvatarLocomotion motion, Func<bool>? canBegin = null)
        {
            _motion = motion ?? throw new ArgumentNullException(nameof(motion));
            _canBegin = canBegin ?? (() => true);
        }

        public bool BeginGrab(int pointerGlobalX, int pointerGlobalY, Vector3 bodyHitWorld)
        {
            if (_motion == null || !_canBegin() ||
                !_motion.Topology.IsPointOnDisplay(pointerGlobalX, pointerGlobalY))
                return false;
            var transformer = new CoordinateTransformer(_motion.PixelsPerMeter);
            var hit = transformer.WorldToGlobal(
                new UnityWorldPoint(bodyHitWorld.x, bodyHitWorld.y, bodyHitWorld.z),
                _motion.Topology);
            var current = _motion.GetCurrentGlobalPixelPosition();
            _bodyAnchorOffset = new Vector2(current.GlobalX - hit.GlobalX,
                current.GlobalY - hit.GlobalY);
            _motion.TeleportTo(current.GlobalX, current.GlobalY);
            _velocity = Vector2.zero;
            HasReleaseInertia = false;
            IsGrabbed = true;
            _pointerStart = new Vector2(pointerGlobalX, pointerGlobalY);
            _maximumPointerTravel = 0;
            Poked?.Invoke();
            Grabbed?.Invoke();
            return true;
        }

        public void DragTo(int pointerGlobalX, int pointerGlobalY, float deltaSeconds)
        {
            if (!IsGrabbed || deltaSeconds <= 0 || float.IsNaN(deltaSeconds) ||
                float.IsInfinity(deltaSeconds)) return;
            _maximumPointerTravel = Mathf.Max(_maximumPointerTravel,
                Vector2.Distance(_pointerStart, new Vector2(pointerGlobalX, pointerGlobalY)));
            var desired = OverlayPlacement.SafeAnchor(_motion.Topology,
                (int)Math.Round(pointerGlobalX + _bodyAnchorOffset.x),
                (int)Math.Round(pointerGlobalY + _bodyAnchorOffset.y));
            var current = _motion.GetCurrentGlobalPixelPosition();
            var error = new Vector2(desired.X - current.GlobalX, desired.Y - current.GlobalY);
            _velocity += (error * springPerSecondSquared - _velocity * dampingPerSecond) *
                deltaSeconds;
            _velocity = Vector2.ClampMagnitude(_velocity, maximumDragSpeedPxPerSecond);
            MoveByVelocity(current, deltaSeconds);
        }

        public void EndGrab()
        {
            if (!IsGrabbed) return;
            IsGrabbed = false;
            _velocity = Vector2.ClampMagnitude(_velocity, maximumReleaseSpeedPxPerSecond);
            HasReleaseInertia = _velocity.magnitude >= releaseStopSpeedPxPerSecond;
            if (!HasReleaseInertia) _velocity = Vector2.zero;
            Released?.Invoke(_velocity);
            if (_maximumPointerTravel <= clickTravelThresholdPx) Clicked?.Invoke();
        }

        /// <summary>Transfers the already bounded release velocity to the P12.2 physics owner.</summary>
        public Vector2 TakeReleaseVelocity()
        {
            if (IsGrabbed) return Vector2.zero;
            var velocity = _velocity;
            _velocity = Vector2.zero;
            HasReleaseInertia = false;
            return velocity;
        }

        public void CancelForCaptureLoss()
        {
            bool wasGrabbed = IsGrabbed;
            IsGrabbed = false;
            HasReleaseInertia = false;
            _velocity = Vector2.zero;
            if (_motion != null)
            {
                var current = _motion.GetCurrentGlobalPixelPosition();
                _motion.TeleportTo(current.GlobalX, current.GlobalY);
            }
            if (wasGrabbed) Released?.Invoke(Vector2.zero);
        }

        public void TickRelease(float deltaSeconds)
        {
            if (!HasReleaseInertia || deltaSeconds <= 0 || float.IsNaN(deltaSeconds) ||
                float.IsInfinity(deltaSeconds)) return;
            _velocity *= Mathf.Exp(-releaseDampingPerSecond * deltaSeconds);
            if (_velocity.magnitude < releaseStopSpeedPxPerSecond)
            {
                _velocity = Vector2.zero;
                HasReleaseInertia = false;
                return;
            }
            MoveByVelocity(_motion.GetCurrentGlobalPixelPosition(), deltaSeconds);
        }

        private void MoveByVelocity((int GlobalX, int GlobalY) current, float deltaSeconds)
        {
            int proposedX = (int)Math.Round(current.GlobalX + _velocity.x * deltaSeconds);
            int proposedY = (int)Math.Round(current.GlobalY + _velocity.y * deltaSeconds);
            var safe = OverlayPlacement.SafeAnchor(_motion.Topology, proposedX, proposedY);
            if (safe.X != proposedX) _velocity.x = 0;
            if (safe.Y != proposedY) _velocity.y = 0;
            _motion.TeleportTo(safe.X, safe.Y);
            if (_velocity == Vector2.zero) HasReleaseInertia = false;
        }

        private void OnDisable() => CancelForCaptureLoss();
    }
}
