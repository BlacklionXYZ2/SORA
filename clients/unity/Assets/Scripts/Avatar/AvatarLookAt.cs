using System;
using UnityEngine;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Clamped gaze and head-tracking controller for the SORA avatar.
    /// Directs head/eyes toward commanded physical screen pixel coordinates
    /// with strict angular limits to preserve natural humanoid anatomical posture.
    /// </summary>
    [DefaultExecutionOrder(20001)]
    public class AvatarLookAt : MonoBehaviour
    {
        [Header("Bones & Transforms")]
        [SerializeField]
        private Transform? headBone;

        [Header("Angular Limits (Degrees)")]
        [SerializeField]
        private float maxYawAngle = 60.0f; // Left/Right limit

        [SerializeField]
        private float maxPitchAngle = 30.0f; // Up/Down limit

        [Header("Smoothing")]
        [SerializeField]
        private float gazeSlerpSpeed = 8.0f;

        [SerializeField]
        private float basePixelsPerMeter = 500.0f;

        private CoordinateTransformer _transformer = null!;
        private DisplayTopology _topology = null!;

        private Vector3 _targetWorldPoint;
        private bool _isLooking = false;
        private float _presentationWeight = 1.0f;
        private Quaternion _originalHeadRotation;
        private AvatarPoseOwnership? _poseOwnership;

        public bool IsLooking => _isLooking;
        public void ConfigureHead(Transform head)
        {
            headBone = head;
            _originalHeadRotation = head.localRotation;
        }
        public void ConfigurePoseOwnership(AvatarPoseOwnership poseOwnership) =>
            _poseOwnership = poseOwnership ?? throw new ArgumentNullException(nameof(poseOwnership));
        public Vector3 TargetWorldPoint => _targetWorldPoint;

        private void Awake()
        {
            _transformer = new CoordinateTransformer(basePixelsPerMeter);
            _topology = new DisplayTopology(
                new ScreenRect(0, 0, 1920, 1080),
                new[] { new MonitorDescriptor("PRIMARY", true, new ScreenRect(0, 0, 1920, 1080)) },
                1
            );

            if (headBone != null)
            {
                _originalHeadRotation = headBone.localRotation;
            }
        }

        public void SetTopology(DisplayTopology topology)
        {
            _topology = topology ?? throw new ArgumentNullException(nameof(topology));
        }

        public void LookAtScreenPoint(int globalPixelX, int globalPixelY)
        {
            LookAtScreenPoint(globalPixelX, globalPixelY, 1.0f);
        }

        public void LookAtScreenPoint(int globalPixelX, int globalPixelY, float presentationWeight)
        {
            var worldPt = _transformer.GlobalToWorld(globalPixelX, globalPixelY, _topology);
            // Default depth in front of avatar
            LookAtWorldPoint(new Vector3(worldPt.X, worldPt.Y, transform.position.z - 0.5f),
                presentationWeight);
        }

        public void LookAtWorldPoint(Vector3 worldPoint)
        {
            LookAtWorldPoint(worldPoint, 1.0f);
        }

        public void LookAtWorldPoint(Vector3 worldPoint, float presentationWeight)
        {
            if (presentationWeight < 0 || presentationWeight > 1 || float.IsNaN(presentationWeight))
                throw new ArgumentOutOfRangeException(nameof(presentationWeight));
            _targetWorldPoint = worldPoint;
            _presentationWeight = presentationWeight;
            _isLooking = true;
        }

        public void ResetGaze()
        {
            _isLooking = false;
            _presentationWeight = 1.0f;
        }

        public void ApplyGaze(float deltaSeconds)
        {
            if (_poseOwnership?.IsOwned == true) return;
            if (headBone == null) return;

            if (!_isLooking)
            {
                // Smoothly return head to neutral pose
                headBone.localRotation = Quaternion.Slerp(headBone.localRotation, _originalHeadRotation,
                    deltaSeconds * gazeSlerpSpeed);
                return;
            }

            // Direction from head to target
            Vector3 headPos = headBone.position;
            Vector3 toTarget = _targetWorldPoint - headPos;
            if (toTarget.sqrMagnitude < 0.0001f) return;

            // Convert to local space of avatar body
            Vector3 localDir = transform.InverseTransformDirection(toTarget.normalized);

            // Compute yaw and pitch
            float yaw = Mathf.Atan2(localDir.x, localDir.z) * Mathf.Rad2Deg;
            float pitch = -Mathf.Asin(Mathf.Clamp(localDir.y, -1f, 1f)) * Mathf.Rad2Deg;

            // Clamp angles to anatomical limits
            float clampedYaw = Mathf.Clamp(yaw, -maxYawAngle, maxYawAngle) * _presentationWeight;
            float clampedPitch = Mathf.Clamp(pitch, -maxPitchAngle, maxPitchAngle) * _presentationWeight;

            Quaternion targetLocalRot = Quaternion.Euler(clampedPitch, clampedYaw, 0f) * _originalHeadRotation;
            headBone.localRotation = Quaternion.Slerp(headBone.localRotation, targetLocalRot,
                deltaSeconds * gazeSlerpSpeed);
        }

        private void LateUpdate() => ApplyGaze(Time.deltaTime);
    }
}
