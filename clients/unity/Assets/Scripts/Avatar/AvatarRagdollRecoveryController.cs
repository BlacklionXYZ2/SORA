using System;
using System.Collections.Generic;
using Sora.Embodiment.Presentation;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public enum RagdollRecoveryState
    {
        Inactive,
        Falling,
        Settling,
        Recovering,
    }

    public enum RagdollOrientation
    {
        Upright,
        Front,
        Back,
        LeftSide,
        RightSide,
    }

    public enum RagdollRecoveryOutcome
    {
        None,
        Recovered,
        TimeoutReset,
        Interrupted,
    }

    /// <summary>
    /// Bounded screen-plane ragdoll pose and recovery. P12.3 deliberately uses
    /// deterministic joint constraints instead of unconstrained Rigidbody chains:
    /// the avatar has one body collision proxy, finite joint limits, a measured
    /// settle interval, and an exact-pose timeout reset.
    /// </summary>
    [DefaultExecutionOrder(20020)]
    public sealed class AvatarRagdollRecoveryController : MonoBehaviour
    {
        private const string PoseOwner = "ragdoll-recovery";

        private sealed class Joint
        {
            public readonly Transform Transform;
            public readonly Quaternion Rest;
            public readonly float LimitDegrees;
            public Quaternion RecoveryStart;

            public Joint(Transform transform, float limitDegrees)
            {
                Transform = transform;
                Rest = transform.localRotation;
                LimitDegrees = limitDegrees;
                RecoveryStart = Rest;
            }
        }

        [SerializeField] private float fallSeconds = 0.32f;
        [SerializeField] private float settleSeconds = 0.22f;
        [SerializeField] private float getUpSeconds = 0.65f;
        [SerializeField] private float timeoutSeconds = 3.0f;
        [SerializeField] private float jointSpeedDegreesPerSecond = 520f;
        [SerializeField] private float settleAngleDegrees = 0.75f;
        [SerializeField] private float minimumImpactSpeedPxPerSecond = 1000f;
        [SerializeField] private float sideImpactSpeedPxPerSecond = 350f;

        private readonly List<Joint> _joints = new List<Joint>();
        private AvatarPoseOwnership? _poseOwnership;
        private AvatarReachController? _reach;
        private AvatarLookAt? _gaze;
        private AvatarPresentationController? _presentation;
        private AvatarSimplePhysicsController? _simplePhysics;
        private AvatarGrabController? _grab;
        private Action? _resetSecondaryMotion;
        private Collider? _bodyCollision;
        private Quaternion _orientation = Quaternion.identity;
        private Quaternion _targetOrientation = Quaternion.identity;
        private float _stateElapsed;
        private float _totalElapsed;
        private float _settledElapsed;

        public RagdollRecoveryState State { get; private set; } = RagdollRecoveryState.Inactive;
        public RagdollOrientation DetectedOrientation { get; private set; } = RagdollOrientation.Upright;
        public RagdollRecoveryOutcome LastOutcome { get; private set; } = RagdollRecoveryOutcome.None;
        public bool IsActive => State != RagdollRecoveryState.Inactive;
        public bool IsConfigured => _joints.Count > 0 && _poseOwnership != null && _bodyCollision != null;
        public int JointCount => _joints.Count;
        public bool HasBodyCollision => _bodyCollision != null && _bodyCollision.enabled;
        public event Action? RecoveryCompleted;
        public event Action<string>? RecoveryFailed;

        public void Configure(Animator animator, AvatarPoseOwnership poseOwnership,
            Collider bodyCollision)
        {
            if (animator == null) throw new ArgumentNullException(nameof(animator));
            if (!animator.isHuman) throw new ArgumentException("Humanoid animator required", nameof(animator));
            ConfigureRig(
                Required(animator, HumanBodyBones.Hips),
                Required(animator, HumanBodyBones.Spine),
                animator.GetBoneTransform(HumanBodyBones.Chest),
                Required(animator, HumanBodyBones.Head),
                Required(animator, HumanBodyBones.LeftUpperArm),
                Required(animator, HumanBodyBones.LeftLowerArm),
                Required(animator, HumanBodyBones.RightUpperArm),
                Required(animator, HumanBodyBones.RightLowerArm),
                Required(animator, HumanBodyBones.LeftUpperLeg),
                Required(animator, HumanBodyBones.LeftLowerLeg),
                Required(animator, HumanBodyBones.RightUpperLeg),
                Required(animator, HumanBodyBones.RightLowerLeg),
                poseOwnership, bodyCollision);
        }

        public void ConfigureRig(Transform hips, Transform spine, Transform? chest,
            Transform head, Transform leftUpperArm, Transform leftLowerArm,
            Transform rightUpperArm, Transform rightLowerArm, Transform leftUpperLeg,
            Transform leftLowerLeg, Transform rightUpperLeg, Transform rightLowerLeg,
            AvatarPoseOwnership poseOwnership, Collider bodyCollision)
        {
            if (IsActive) SafetyReset(RagdollRecoveryOutcome.Interrupted);
            _poseOwnership = poseOwnership ?? throw new ArgumentNullException(nameof(poseOwnership));
            _bodyCollision = bodyCollision != null ? bodyCollision :
                throw new ArgumentNullException(nameof(bodyCollision));
            _joints.Clear();
            Add(hips, 88); Add(spine, 48); if (chest != null && chest != spine) Add(chest, 42);
            Add(head, 42); Add(leftUpperArm, 105); Add(leftLowerArm, 115);
            Add(rightUpperArm, 105); Add(rightLowerArm, 115);
            Add(leftUpperLeg, 78); Add(leftLowerLeg, 105);
            Add(rightUpperLeg, 78); Add(rightLowerLeg, 105);
        }

        public void ConfigureControllers(AvatarReachController? reach, AvatarLookAt? gaze,
            AvatarPresentationController? presentation, AvatarSimplePhysicsController? simplePhysics,
            AvatarGrabController? grab, Action? resetSecondaryMotion = null)
        {
            _reach = reach;
            _gaze = gaze;
            _presentation = presentation;
            _simplePhysics = simplePhysics;
            _grab = grab;
            _resetSecondaryMotion = resetSecondaryMotion;
        }

        public void ConfigureTiming(float fall, float settle, float getUp, float timeout)
        {
            if (!FinitePositive(fall) || !FinitePositive(settle) || !FinitePositive(getUp) ||
                !FinitePositive(timeout)) throw new ArgumentOutOfRangeException(nameof(fall));
            fallSeconds = fall; settleSeconds = settle; getUpSeconds = getUp;
            timeoutSeconds = timeout;
        }

        public bool BeginRagdoll(RagdollOrientation orientation)
        {
            if (!IsConfigured) throw new InvalidOperationException("Ragdoll rig is not configured");
            if (orientation == RagdollOrientation.Upright) return false;
            if (IsActive || !_poseOwnership!.TryAcquire(PoseOwner)) return false;
            _reach?.AbortImmediate();
            _gaze?.ResetGaze();
            _presentation?.ResetToIdle();
            _simplePhysics?.StopSimulation();
            _grab?.CancelForCaptureLoss();
            _resetSecondaryMotion?.Invoke();
            _orientation = Quaternion.identity;
            _targetOrientation = OrientationRotation(orientation);
            DetectedOrientation = RagdollOrientation.Upright;
            LastOutcome = RagdollRecoveryOutcome.None;
            State = RagdollRecoveryState.Falling;
            _stateElapsed = 0;
            _totalElapsed = 0;
            _settledElapsed = 0;
            return true;
        }

        /// <summary>
        /// Converts a sufficiently hard P12.2 landing into local presentation recovery.
        /// This does not publish the semantic fall/land events reserved for P12.5.
        /// </summary>
        public bool TryBeginFromImpact(Vector2 impactVelocityPixelsPerSecond)
        {
            if (!Finite(impactVelocityPixelsPerSecond.x) ||
                !Finite(impactVelocityPixelsPerSecond.y) ||
                impactVelocityPixelsPerSecond.y < minimumImpactSpeedPxPerSecond)
                return false;
            var orientation = Mathf.Abs(impactVelocityPixelsPerSecond.x) >=
                sideImpactSpeedPxPerSecond ?
                (impactVelocityPixelsPerSecond.x >= 0 ? RagdollOrientation.RightSide :
                    RagdollOrientation.LeftSide) :
                RagdollOrientation.Front;
            return BeginRagdoll(orientation);
        }

        public void Advance(float deltaSeconds)
        {
            if (deltaSeconds < 0 || float.IsNaN(deltaSeconds) || float.IsInfinity(deltaSeconds))
                throw new ArgumentOutOfRangeException(nameof(deltaSeconds));
            if (!IsActive || deltaSeconds == 0) return;
            _totalElapsed += deltaSeconds;
            _stateElapsed += deltaSeconds;
            if (_totalElapsed >= timeoutSeconds)
            {
                SafetyReset(RagdollRecoveryOutcome.TimeoutReset);
                return;
            }

            if (State == RagdollRecoveryState.Falling || State == RagdollRecoveryState.Settling)
            {
                float progress = State == RagdollRecoveryState.Falling ?
                    Mathf.Clamp01(_stateElapsed / fallSeconds) : 1f;
                _orientation = Quaternion.Slerp(Quaternion.identity, _targetOrientation,
                    Smooth(progress));
                float remaining = ApplyFallPose(deltaSeconds);
                DetectedOrientation = ClassifyOrientation(_orientation * Vector3.up);
                if (State == RagdollRecoveryState.Falling && progress >= 1)
                {
                    State = RagdollRecoveryState.Settling;
                    _stateElapsed = 0;
                }
                else if (State == RagdollRecoveryState.Settling)
                {
                    _settledElapsed = remaining <= settleAngleDegrees ?
                        _settledElapsed + deltaSeconds : 0;
                    if (_settledElapsed >= settleSeconds) StartRecovery();
                }
                return;
            }

            float recoveryProgress = Mathf.Clamp01(_stateElapsed / getUpSeconds);
            float blend = Smooth(recoveryProgress);
            foreach (var joint in _joints)
                joint.Transform.localRotation = Quaternion.Slerp(joint.RecoveryStart,
                    joint.Rest, blend);
            _orientation = Quaternion.Slerp(_targetOrientation, Quaternion.identity, blend);
            DetectedOrientation = ClassifyOrientation(_orientation * Vector3.up);
            if (recoveryProgress >= 1) FinishRecovery();
        }

        public void Interrupt() => SafetyReset(RagdollRecoveryOutcome.Interrupted);

        public static RagdollOrientation ClassifyOrientation(Vector3 bodyUp)
        {
            if (!Finite(bodyUp) || bodyUp.sqrMagnitude < 0.0001f)
                return RagdollOrientation.Upright;
            bodyUp.Normalize();
            if (Mathf.Abs(bodyUp.y) >= 0.72f) return RagdollOrientation.Upright;
            if (Mathf.Abs(bodyUp.z) >= Mathf.Abs(bodyUp.x))
                return bodyUp.z >= 0 ? RagdollOrientation.Front : RagdollOrientation.Back;
            return bodyUp.x >= 0 ? RagdollOrientation.RightSide : RagdollOrientation.LeftSide;
        }

        private float ApplyFallPose(float deltaSeconds)
        {
            float maximumRemaining = 0;
            for (int i = 0; i < _joints.Count; i++)
            {
                var joint = _joints[i];
                Quaternion offset = JointOffset(i, _targetOrientation);
                float angle = Quaternion.Angle(Quaternion.identity, offset);
                if (angle > joint.LimitDegrees)
                    offset = Quaternion.Slerp(Quaternion.identity, offset,
                        joint.LimitDegrees / angle);
                var target = joint.Rest * offset;
                joint.Transform.localRotation = Quaternion.RotateTowards(
                    joint.Transform.localRotation, target, jointSpeedDegreesPerSecond * deltaSeconds);
                maximumRemaining = Mathf.Max(maximumRemaining,
                    Quaternion.Angle(joint.Transform.localRotation, target));
            }
            return maximumRemaining;
        }

        private void StartRecovery()
        {
            foreach (var joint in _joints) joint.RecoveryStart = joint.Transform.localRotation;
            State = RagdollRecoveryState.Recovering;
            _stateElapsed = 0;
        }

        private void FinishRecovery()
        {
            RestorePose();
            State = RagdollRecoveryState.Inactive;
            DetectedOrientation = RagdollOrientation.Upright;
            LastOutcome = RagdollRecoveryOutcome.Recovered;
            _poseOwnership?.Release(PoseOwner);
            _resetSecondaryMotion?.Invoke();
            RecoveryCompleted?.Invoke();
        }

        private void SafetyReset(RagdollRecoveryOutcome outcome)
        {
            if (!IsActive && _poseOwnership?.Owner != PoseOwner) return;
            RestorePose();
            State = RagdollRecoveryState.Inactive;
            DetectedOrientation = RagdollOrientation.Upright;
            LastOutcome = outcome;
            _poseOwnership?.Release(PoseOwner);
            _resetSecondaryMotion?.Invoke();
            if (outcome != RagdollRecoveryOutcome.Recovered)
                RecoveryFailed?.Invoke(outcome.ToString().ToLowerInvariant());
        }

        private void RestorePose()
        {
            foreach (var joint in _joints) joint.Transform.localRotation = joint.Rest;
            _orientation = Quaternion.identity;
        }

        private void Add(Transform transform, float limit)
        {
            if (transform == null) throw new ArgumentNullException(nameof(transform));
            if (_joints.Exists(joint => joint.Transform == transform)) return;
            _joints.Add(new Joint(transform, limit));
        }

        private static Transform Required(Animator animator, HumanBodyBones bone) =>
            animator.GetBoneTransform(bone) ??
            throw new ArgumentException($"Humanoid bone required: {bone}", nameof(animator));

        private static Quaternion OrientationRotation(RagdollOrientation orientation)
        {
            switch (orientation)
            {
                case RagdollOrientation.Front: return Quaternion.Euler(88, 0, 0);
                case RagdollOrientation.Back: return Quaternion.Euler(-88, 0, 0);
                case RagdollOrientation.LeftSide: return Quaternion.Euler(0, 0, 88);
                case RagdollOrientation.RightSide: return Quaternion.Euler(0, 0, -88);
                default: return Quaternion.identity;
            }
        }

        private static Quaternion JointOffset(int index, Quaternion orientation)
        {
            if (index == 0) return orientation;
            float sign = index % 2 == 0 ? 1 : -1;
            if (index <= 3) return Quaternion.Slerp(Quaternion.identity, orientation, 0.28f);
            if (index <= 7) return Quaternion.Euler(18 * sign, 0, 34 * sign);
            return Quaternion.Euler(-24 * sign, 0, 8 * sign);
        }

        private static float Smooth(float value) => value * value * (3f - 2f * value);
        private static bool FinitePositive(float value) => Finite(value) && value > 0;
        private static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        private static bool Finite(Vector3 value) => Finite(value.x) && Finite(value.y) && Finite(value.z);

        private void LateUpdate() => Advance(Time.unscaledDeltaTime);
        private void OnDisable()
        {
            if (IsActive) SafetyReset(RagdollRecoveryOutcome.Interrupted);
        }
    }
}
