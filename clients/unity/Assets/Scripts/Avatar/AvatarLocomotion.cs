using System;
using UnityEngine;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Deterministic locomotion controller for the SORA avatar.
    /// Translates avatar along desktop coordinates using the CoordinateTransformer
    /// without invoking any model inference in the 60 FPS update loop.
    /// </summary>
    public class AvatarLocomotion : MonoBehaviour
    {
        [Header("Locomotion Settings")]
        [SerializeField]
        private float basePixelsPerMeter = 500.0f;

        [SerializeField]
        private float defaultSpeedPxPerSec = 200.0f;

        [SerializeField]
        private float arrivalThresholdMeters = 0.02f;

        [SerializeField]
        private bool orientTowardsMovement = true;

        [SerializeField]
        private float rotationSlerpSpeed = 10.0f;

        private CoordinateTransformer _transformer = null!;
        private DisplayTopology _topology = null!;

        private Vector3 _targetWorldPosition;
        private float _currentSpeedMetersPerSec;
        private bool _isMoving = false;

        public bool IsMoving => _isMoving;
        public float CurrentSpeedPxPerSec => _isMoving ? _currentSpeedMetersPerSec * basePixelsPerMeter : 0;
        public Vector3 TargetWorldPosition => _targetWorldPosition;
        public DisplayTopology Topology => _topology;
        public float PixelsPerMeter => basePixelsPerMeter;

        public event Action? OnArrival;
        public event Action<int, int>? OnPositionUpdated;

        private void Awake()
        {
            _transformer = new CoordinateTransformer(basePixelsPerMeter);

            // Default fallback topology (1080p primary) until updated by runtime
            _topology = new DisplayTopology(
                new ScreenRect(0, 0, 1920, 1080),
                new[] { new MonitorDescriptor("PRIMARY", true, new ScreenRect(0, 0, 1920, 1080)) },
                1
            );
            _targetWorldPosition = transform.position;
        }

        public void SetTopology(DisplayTopology topology)
        {
            var position = GetCurrentGlobalPixelPosition();
            _topology = topology ?? throw new ArgumentNullException(nameof(topology));
            var clamped = OverlayPlacement.SafeAnchor(topology, position.GlobalX, position.GlobalY);
            TeleportTo(clamped.X, clamped.Y);
        }

        public void SetPixelsPerMeter(float ppm)
        {
            basePixelsPerMeter = ppm;
            _transformer = new CoordinateTransformer(basePixelsPerMeter);
        }

        public void MoveTo(int globalPixelX, int globalPixelY, float speedPxPerSec = 0)
        {
            if (!_topology.IsPointOnDisplay(globalPixelX, globalPixelY))
                throw new ArgumentOutOfRangeException(nameof(globalPixelX), "Target is outside active displays");
            if (speedPxPerSec <= 0)
            {
                speedPxPerSec = defaultSpeedPxPerSec;
            }

            var safe = OverlayPlacement.SafeAnchor(_topology, globalPixelX, globalPixelY);
            var worldPt = _transformer.GlobalToWorld(safe.X, safe.Y, _topology);
            _targetWorldPosition = new Vector3(worldPt.X, worldPt.Y, transform.position.z);

            // Physical pixel velocity is continuous across mixed-DPI monitors.
            _currentSpeedMetersPerSec = speedPxPerSec / basePixelsPerMeter;

            _isMoving = true;
        }

        public void TeleportTo(int globalPixelX, int globalPixelY)
        {
            var worldPt = _transformer.GlobalToWorld(globalPixelX, globalPixelY, _topology);
            transform.position = new Vector3(worldPt.X, worldPt.Y, transform.position.z);
            _targetWorldPosition = transform.position;
            _isMoving = false;

            OnPositionUpdated?.Invoke(globalPixelX, globalPixelY);
        }

        /// <summary>Stops a walk where she is (e.g. she fell on the way). Core sees her position,
        /// not an arrival.</summary>
        public void Stop()
        {
            if (!_isMoving) return;
            _targetWorldPosition = transform.position;
            _isMoving = false;
            var here = GetCurrentGlobalPixelPosition();
            OnPositionUpdated?.Invoke(here.GlobalX, here.GlobalY);
        }

        /// <summary>Moves her instantly to a world position (snapped to a safe screen anchor),
        /// e.g. to where her physics body came to rest after a fall.</summary>
        public void TeleportToWorld(Vector3 world)
        {
            var global = _transformer.WorldToGlobal(new UnityWorldPoint(world.x, world.y, world.z), _topology);
            var safe = OverlayPlacement.SafeAnchor(_topology, global.GlobalX, global.GlobalY);
            TeleportTo(safe.X, safe.Y);
        }

        public (int GlobalX, int GlobalY) GetCurrentGlobalPixelPosition()
        {
            var worldPt = new UnityWorldPoint(transform.position.x, transform.position.y, transform.position.z);
            return _transformer.WorldToGlobal(worldPt, _topology);
        }

        private void Update()
        {
            if (!_isMoving)
            {
                if (orientTowardsMovement)
                    transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.Euler(0, 180, 0), Time.deltaTime * rotationSlerpSpeed);
                return;
            }

            Vector3 currentPos = transform.position;
            Vector3 delta = _targetWorldPosition - currentPos;
            delta.z = 0; // Maintain 2D overlay plane

            float distance = delta.magnitude;
            if (distance <= arrivalThresholdMeters)
            {
                transform.position = new Vector3(_targetWorldPosition.x, _targetWorldPosition.y, currentPos.z);
                _isMoving = false;
                var arrived = GetCurrentGlobalPixelPosition();
                OnPositionUpdated?.Invoke(arrived.GlobalX, arrived.GlobalY);
                OnArrival?.Invoke();
                return;
            }

            Vector3 direction = delta.normalized;
            float step = _currentSpeedMetersPerSec * Time.deltaTime;

            if (step >= distance)
            {
                transform.position = new Vector3(_targetWorldPosition.x, _targetWorldPosition.y, currentPos.z);
                _isMoving = false;
                OnArrival?.Invoke();
            }
            else
            {
                transform.position += direction * step;

                if (orientTowardsMovement && direction.sqrMagnitude > 0.001f)
                {
                    // Face left (-X) or right (+X)
                    float targetAngleY = direction.x >= 0 ? 90f : -90f;
                    Quaternion targetRot = Quaternion.Euler(0, targetAngleY, 0);
                    transform.rotation = Quaternion.Slerp(transform.rotation, targetRot, Time.deltaTime * rotationSlerpSpeed);
                }
            }

            var currentGlobal = GetCurrentGlobalPixelPosition();
            OnPositionUpdated?.Invoke(currentGlobal.GlobalX, currentGlobal.GlobalY);
        }
    }
}
