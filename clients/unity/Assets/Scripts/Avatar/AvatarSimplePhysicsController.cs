using System;
using Sora.Embodiment.Coordinates;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public enum SimplePhysicsState
    {
        Inactive,
        Held,
        Falling,
        Settling,
    }

    /// <summary>
    /// Bounded presentation physics for a released avatar. Monitor work-area bottoms are
    /// the only supports in P12.2; window surfaces remain P12.4.
    /// </summary>
    public sealed class AvatarSimplePhysicsController : MonoBehaviour
    {
        [SerializeField] private float gravityPxPerSecondSquared = 2400f;
        [SerializeField] private float maximumHorizontalSpeedPxPerSecond = 1400f;
        [SerializeField] private float maximumFallSpeedPxPerSecond = 2600f;
        [SerializeField] private float airDragPerSecond = 1.5f;
        [SerializeField] private float groundDragPerSecond = 9f;
        [SerializeField] private float settleSpeedPxPerSecond = 8f;
        [SerializeField] private float maximumSimulatedFrameSeconds = 0.1f;
        [SerializeField] private float maximumSubstepSeconds = 1f / 120f;

        private AvatarLocomotion _motion = null!;
        private Func<bool> _canSimulate = () => true;
        private Action? _resetSecondaryMotion;
        private Func<int, int, int, int, AvatarSupportHit?>? _resolveSupport;
        private Vector2 _velocity;

        public SimplePhysicsState State { get; private set; } = SimplePhysicsState.Inactive;
        public Vector2 VelocityPixelsPerSecond => _velocity;
        public bool IsActive => State == SimplePhysicsState.Falling ||
            State == SimplePhysicsState.Settling;
        public string? LastSafetyResetReason { get; private set; }
        public event Action<Vector2>? Landed;
        public event Action<Vector2, AvatarSupportHit>? LandedOnSupport;
        public event Action<Vector2>? Fell;

        public void Configure(AvatarLocomotion motion, Func<bool>? canSimulate = null,
            Action? resetSecondaryMotion = null)
        {
            _motion = motion ?? throw new ArgumentNullException(nameof(motion));
            _canSimulate = canSimulate ?? (() => true);
            _resetSecondaryMotion = resetSecondaryMotion;
        }

        /// <summary>Gravity in pixels a second squared (2400 by default). Her physics body sets
        /// real gravity at her on-screen size, so drops fall as fast as her body would.</summary>
        public float GravityPxPerSecondSquared
        {
            get => gravityPxPerSecondSquared;
            set => gravityPxPerSecondSquared = float.IsFinite(value) && value > 0 ? value
                : throw new ArgumentOutOfRangeException(nameof(value));
        }

        public void ConfigureSecondaryMotionReset(Action resetSecondaryMotion)
        {
            _resetSecondaryMotion = resetSecondaryMotion ??
                throw new ArgumentNullException(nameof(resetSecondaryMotion));
        }

        public void ConfigureSupportResolver(
            Func<int, int, int, int, AvatarSupportHit?> resolveSupport)
        {
            _resolveSupport = resolveSupport ?? throw new ArgumentNullException(nameof(resolveSupport));
        }

        public void SuspendForGrab()
        {
            _velocity = Vector2.zero;
            State = SimplePhysicsState.Held;
            LastSafetyResetReason = null;
        }

        public bool Release(Vector2 releaseVelocity)
        {
            if (_motion == null || !_canSimulate())
            {
                StopSimulation();
                return false;
            }
            if (!IsFinite(releaseVelocity))
            {
                SafetyReset("non_finite_release_velocity");
                return false;
            }
            _velocity = new Vector2(
                Mathf.Clamp(releaseVelocity.x, -maximumHorizontalSpeedPxPerSecond,
                    maximumHorizontalSpeedPxPerSecond),
                Mathf.Clamp(releaseVelocity.y, -maximumFallSpeedPxPerSecond,
                    maximumFallSpeedPxPerSecond));
            State = SimplePhysicsState.Falling;
            LastSafetyResetReason = null;
            Fell?.Invoke(_velocity);
            return true;
        }

        public bool LoseSupport()
        {
            if (_motion == null || !_canSimulate() || IsActive) return false;
            _velocity = Vector2.zero;
            State = SimplePhysicsState.Falling;
            LastSafetyResetReason = null;
            Fell?.Invoke(_velocity);
            return true;
        }

        public void Tick(float deltaSeconds)
        {
            if (!IsActive) return;
            if (!_canSimulate())
            {
                StopSimulation();
                return;
            }
            if (!IsFinite(deltaSeconds) || deltaSeconds <= 0) return;
            if (!IsFinite(_velocity) || !TransformIsFinite())
            {
                SafetyReset("non_finite_simulation_state");
                return;
            }
            float remaining = Mathf.Min(deltaSeconds, maximumSimulatedFrameSeconds);
            while (remaining > 0 && IsActive)
            {
                float step = Mathf.Min(remaining, maximumSubstepSeconds);
                Step(step);
                remaining -= step;
            }
        }

        public void CancelToSafeSupport()
        {
            if (_motion == null) return;
            MoveToSupport();
            StopSimulation();
        }

        public void StopSimulation()
        {
            _velocity = Vector2.zero;
            State = SimplePhysicsState.Inactive;
        }

        private void Step(float deltaSeconds)
        {
            float horizontalDrag = State == SimplePhysicsState.Settling ?
                groundDragPerSecond : airDragPerSecond;
            _velocity.x *= Mathf.Exp(-horizontalDrag * deltaSeconds);
            _velocity.x = Mathf.Clamp(_velocity.x, -maximumHorizontalSpeedPxPerSecond,
                maximumHorizontalSpeedPxPerSecond);
            _velocity.y = Mathf.Min(_velocity.y + gravityPxPerSecondSquared * deltaSeconds,
                maximumFallSpeedPxPerSecond);

            var current = _motion.GetCurrentGlobalPixelPosition();
            int proposedX = (int)Math.Round(current.GlobalX + _velocity.x * deltaSeconds);
            int proposedY = (int)Math.Round(current.GlobalY + _velocity.y * deltaSeconds);
            AvatarSupportHit? support = _velocity.y >= 0 ?
                _resolveSupport?.Invoke(current.GlobalX, current.GlobalY, proposedX, proposedY) : null;
            var safe = support.HasValue ?
                OverlayPlacement.SafeAnchor(_motion.Topology, proposedX, support.Value.AnchorY) :
                OverlayPlacement.SafeAnchor(_motion.Topology, proposedX, proposedY);
            bool landed = support.HasValue || (_velocity.y >= 0 && safe.Y < proposedY);
            if (safe.X != proposedX) _velocity.x = 0;
            _motion.TeleportTo(safe.X, safe.Y);
            if (landed)
            {
                var impactVelocity = _velocity;
                _velocity.y = 0;
                State = SimplePhysicsState.Settling;
                Landed?.Invoke(impactVelocity);
                if (support.HasValue) LandedOnSupport?.Invoke(impactVelocity, support.Value);
            }
            if (State == SimplePhysicsState.Settling &&
                Mathf.Abs(_velocity.x) < settleSpeedPxPerSecond)
                StopSimulation();

            if (!IsFinite(_velocity) || !TransformIsFinite())
                SafetyReset("non_finite_simulation_state");
        }

        private void SafetyReset(string reason)
        {
            LastSafetyResetReason = reason;
            if (_motion != null) MoveToSupport();
            StopSimulation();
            _resetSecondaryMotion?.Invoke();
        }

        private void MoveToSupport()
        {
            var current = _motion.GetCurrentGlobalPixelPosition();
            var safe = OverlayPlacement.SafeAnchor(_motion.Topology,
                current.GlobalX, int.MaxValue / 4);
            _motion.TeleportTo(safe.X, safe.Y);
        }

        private bool TransformIsFinite()
        {
            var position = _motion.transform.position;
            return IsFinite(position.x) && IsFinite(position.y) && IsFinite(position.z);
        }

        private static bool IsFinite(Vector2 value) => IsFinite(value.x) && IsFinite(value.y);
        private static bool IsFinite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        private void OnDisable() => StopSimulation();
    }
}
