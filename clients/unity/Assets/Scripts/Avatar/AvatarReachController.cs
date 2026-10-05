using System;
using Sora.Embodiment.Presentation;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public enum ReachArm
    {
        None,
        Left,
        Right
    }

    public enum ReachControllerState
    {
        Idle,
        BlendingIn,
        Holding,
        Retracting,
        Interrupted
    }

    public enum ReachPresentationOutcome
    {
        None,
        Presented,
        OutOfReach,
        Interrupted
    }

    /// <summary>
    /// Deterministic two-bone presentation IK. It chooses an arm, blends a
    /// fingertip toward a reachable world target, and always retracts to an idle
    /// controller state. It cannot authorize or execute a desktop action.
    /// </summary>
    [DefaultExecutionOrder(20010)]
    public sealed class AvatarReachController : MonoBehaviour
    {
        private Transform? _leftUpper;
        private Transform? _leftLower;
        private Transform? _leftFingertip;
        private Transform? _rightUpper;
        private Transform? _rightLower;
        private Transform? _rightFingertip;
        private AvatarLookAt? _gaze;
        private PresentationProfile? _profile;
        private Vector3 _target;
        private float _weight;
        private Quaternion _activeUpperBase;
        private Quaternion _activeLowerBase;
        private Quaternion _activeFingertipBase;
        private AvatarPoseOwnership? _poseOwnership;

        public ReachArm ActiveArm { get; private set; } = ReachArm.None;
        public ReachControllerState State { get; private set; } = ReachControllerState.Idle;
        public ReachPresentationOutcome LastOutcome { get; private set; } = ReachPresentationOutcome.None;
        public float Weight => _weight;
        public Vector3 Target => _target;
        public bool IsConfigured => _leftUpper != null && _leftLower != null && _leftFingertip != null &&
            _rightUpper != null && _rightLower != null && _rightFingertip != null;

        public void ConfigurePoseOwnership(AvatarPoseOwnership poseOwnership) =>
            _poseOwnership = poseOwnership ?? throw new ArgumentNullException(nameof(poseOwnership));

        public void Configure(Animator animator, AvatarLookAt? gaze = null)
        {
            if (animator == null) throw new ArgumentNullException(nameof(animator));
            if (!animator.isHuman) throw new ArgumentException("Humanoid animator required", nameof(animator));
            ConfigureRig(
                animator.GetBoneTransform(HumanBodyBones.LeftUpperArm),
                animator.GetBoneTransform(HumanBodyBones.LeftLowerArm),
                animator.GetBoneTransform(HumanBodyBones.LeftHand),
                animator.GetBoneTransform(HumanBodyBones.RightUpperArm),
                animator.GetBoneTransform(HumanBodyBones.RightLowerArm),
                animator.GetBoneTransform(HumanBodyBones.RightHand),
                gaze);
        }

        public void ConfigureRig(
            Transform leftUpper,
            Transform leftLower,
            Transform leftFingertip,
            Transform rightUpper,
            Transform rightLower,
            Transform rightFingertip,
            AvatarLookAt? gaze = null)
        {
            _leftUpper = leftUpper != null ? leftUpper : throw new ArgumentNullException(nameof(leftUpper));
            _leftLower = leftLower != null ? leftLower : throw new ArgumentNullException(nameof(leftLower));
            _leftFingertip = leftFingertip != null ? leftFingertip : throw new ArgumentNullException(nameof(leftFingertip));
            _rightUpper = rightUpper != null ? rightUpper : throw new ArgumentNullException(nameof(rightUpper));
            _rightLower = rightLower != null ? rightLower : throw new ArgumentNullException(nameof(rightLower));
            _rightFingertip = rightFingertip != null ? rightFingertip : throw new ArgumentNullException(nameof(rightFingertip));
            _gaze = gaze;
            ValidateChain(_leftUpper, _leftLower, _leftFingertip);
            ValidateChain(_rightUpper, _rightLower, _rightFingertip);
            ResetController();
        }

        public bool BeginReach(Vector3 target, PresentationProfile profile)
        {
            if (!IsConfigured) throw new InvalidOperationException("Reach rig is not configured");
            if (!IsFinite(target)) throw new ArgumentOutOfRangeException(nameof(target));
            if (_poseOwnership?.IsOwned == true)
            {
                LastOutcome = ReachPresentationOutcome.Interrupted;
                return false;
            }
            if (State != ReachControllerState.Idle) RestoreActiveBase();
            _profile = profile ?? throw new ArgumentNullException(nameof(profile));
            var arm = SelectArm(target, profile);
            if (arm == ReachArm.None)
            {
                ResetController();
                LastOutcome = ReachPresentationOutcome.OutOfReach;
                return false;
            }
            _target = target;
            ActiveArm = arm;
            CaptureActiveBase();
            State = ReachControllerState.BlendingIn;
            LastOutcome = ReachPresentationOutcome.None;
            _gaze?.LookAtWorldPoint(target, profile.GazeWeight);
            return true;
        }

        public void Retract()
        {
            if (State == ReachControllerState.Idle) return;
            State = ReachControllerState.Retracting;
            LastOutcome = ReachPresentationOutcome.Presented;
        }

        public void Interrupt()
        {
            if (State == ReachControllerState.Idle) return;
            State = ReachControllerState.Interrupted;
            LastOutcome = ReachPresentationOutcome.Interrupted;
        }

        public void AbortImmediate()
        {
            if (State != ReachControllerState.Idle)
                LastOutcome = ReachPresentationOutcome.Interrupted;
            RestoreActiveBase();
            ActiveArm = ReachArm.None;
            State = ReachControllerState.Idle;
            _weight = 0;
            _profile = null;
            _gaze?.ResetGaze();
        }

        public void Advance(float deltaSeconds)
        {
            if (deltaSeconds < 0 || float.IsNaN(deltaSeconds) || float.IsInfinity(deltaSeconds))
                throw new ArgumentOutOfRangeException(nameof(deltaSeconds));
            if (_profile == null || State == ReachControllerState.Idle) return;
            if (State == ReachControllerState.BlendingIn)
            {
                _weight = Mathf.MoveTowards(_weight, 1, deltaSeconds / _profile.BlendInSeconds);
                if (_weight >= 1) State = ReachControllerState.Holding;
                return;
            }
            if (State == ReachControllerState.Retracting || State == ReachControllerState.Interrupted)
            {
                _weight = Mathf.MoveTowards(_weight, 0, deltaSeconds / _profile.RetractSeconds);
                if (_weight <= 0)
                {
                    RestoreActiveBase();
                    ActiveArm = ReachArm.None;
                    State = ReachControllerState.Idle;
                    _profile = null;
                    _gaze?.ResetGaze();
                }
            }
        }

        public void ApplyProceduralIk()
        {
            if (_poseOwnership?.IsOwned == true) return;
            if (_weight <= 0 || ActiveArm == ReachArm.None) return;
            RestoreActiveBase();
            if (ActiveArm == ReachArm.Left)
                SolveArm(_leftUpper!, _leftLower!, _leftFingertip!, _target, _weight, true);
            else
                SolveArm(_rightUpper!, _rightLower!, _rightFingertip!, _target, _weight, false);
        }

        private ReachArm SelectArm(Vector3 target, PresentationProfile profile)
        {
            var leftReachable = CanReach(_leftUpper!, _leftLower!, _leftFingertip!, target, profile.ReachScale);
            var rightReachable = CanReach(_rightUpper!, _rightLower!, _rightFingertip!, target, profile.ReachScale);
            if (!leftReachable && !rightReachable) return ReachArm.None;
            if (profile.ArmPreference == PresentationArmPreference.Left && leftReachable) return ReachArm.Left;
            if (profile.ArmPreference == PresentationArmPreference.Right && rightReachable) return ReachArm.Right;
            if (!leftReachable) return ReachArm.Right;
            if (!rightReachable) return ReachArm.Left;
            var leftDistance = Vector3.Distance(_leftUpper!.position, target);
            var rightDistance = Vector3.Distance(_rightUpper!.position, target);
            if (Mathf.Abs(leftDistance - rightDistance) < 0.0001f)
                return transform.InverseTransformPoint(target).x < 0 ? ReachArm.Left : ReachArm.Right;
            return leftDistance < rightDistance ? ReachArm.Left : ReachArm.Right;
        }

        private static bool CanReach(
            Transform upper,
            Transform lower,
            Transform fingertip,
            Vector3 target,
            float reachScale)
        {
            var upperLength = Vector3.Distance(upper.position, lower.position);
            var lowerLength = Vector3.Distance(lower.position, fingertip.position);
            var distance = Vector3.Distance(upper.position, target);
            var maximum = (upperLength + lowerLength) * reachScale;
            var minimum = Mathf.Abs(upperLength - lowerLength) + 0.0001f;
            return distance >= minimum && distance <= maximum;
        }

        private static void SolveArm(
            Transform upper,
            Transform lower,
            Transform fingertip,
            Vector3 target,
            float weight,
            bool left)
        {
            var upperStart = upper.rotation;
            var lowerStart = lower.rotation;
            var fingertipStart = fingertip.rotation;
            var shoulder = upper.position;
            var upperLength = Vector3.Distance(shoulder, lower.position);
            var lowerLength = Vector3.Distance(lower.position, fingertip.position);
            var toTarget = target - shoulder;
            var distance = Mathf.Clamp(toTarget.magnitude, 0.0001f, upperLength + lowerLength - 0.0001f);
            var direction = toTarget.normalized;
            var pole = left ? Vector3.forward : Vector3.back;
            pole = Vector3.ProjectOnPlane(pole, direction).normalized;
            if (pole.sqrMagnitude < 0.0001f) pole = Vector3.ProjectOnPlane(Vector3.up, direction).normalized;
            var along = (upperLength * upperLength - lowerLength * lowerLength + distance * distance) /
                (2 * distance);
            var bend = Mathf.Sqrt(Mathf.Max(0, upperLength * upperLength - along * along));
            var desiredElbow = shoulder + direction * along + pole * bend;

            upper.rotation = Quaternion.FromToRotation(lower.position - shoulder, desiredElbow - shoulder) * upper.rotation;
            lower.rotation = Quaternion.FromToRotation(fingertip.position - lower.position, target - lower.position) * lower.rotation;
            var desiredHand = Quaternion.LookRotation(transformSafeForward(direction), Vector3.up);

            var solvedUpper = upper.rotation;
            var solvedLower = lower.rotation;
            upper.rotation = upperStart;
            lower.rotation = lowerStart;
            fingertip.rotation = fingertipStart;
            upper.rotation = Quaternion.Slerp(upperStart, solvedUpper, weight);
            lower.rotation = Quaternion.Slerp(lowerStart, solvedLower, weight);
            fingertip.rotation = Quaternion.Slerp(fingertipStart, desiredHand, weight * 0.35f);
        }

        private static Vector3 transformSafeForward(Vector3 direction) =>
            Mathf.Abs(Vector3.Dot(direction, Vector3.up)) > 0.98f ? Vector3.forward : direction;

        private static void ValidateChain(Transform upper, Transform lower, Transform fingertip)
        {
            if (Vector3.Distance(upper.position, lower.position) <= 0.0001f ||
                Vector3.Distance(lower.position, fingertip.position) <= 0.0001f)
                throw new ArgumentException("Reach bones must have non-zero segment lengths");
        }

        private static bool IsFinite(Vector3 value) =>
            !float.IsNaN(value.x) && !float.IsInfinity(value.x) &&
            !float.IsNaN(value.y) && !float.IsInfinity(value.y) &&
            !float.IsNaN(value.z) && !float.IsInfinity(value.z);

        private void CaptureActiveBase()
        {
            var upper = ActiveArm == ReachArm.Left ? _leftUpper! : _rightUpper!;
            var lower = ActiveArm == ReachArm.Left ? _leftLower! : _rightLower!;
            var fingertip = ActiveArm == ReachArm.Left ? _leftFingertip! : _rightFingertip!;
            _activeUpperBase = upper.localRotation;
            _activeLowerBase = lower.localRotation;
            _activeFingertipBase = fingertip.localRotation;
        }

        private void RestoreActiveBase()
        {
            if (ActiveArm == ReachArm.None) return;
            var upper = ActiveArm == ReachArm.Left ? _leftUpper! : _rightUpper!;
            var lower = ActiveArm == ReachArm.Left ? _leftLower! : _rightLower!;
            var fingertip = ActiveArm == ReachArm.Left ? _leftFingertip! : _rightFingertip!;
            upper.localRotation = _activeUpperBase;
            lower.localRotation = _activeLowerBase;
            fingertip.localRotation = _activeFingertipBase;
        }

        private void ResetController()
        {
            ActiveArm = ReachArm.None;
            State = ReachControllerState.Idle;
            LastOutcome = ReachPresentationOutcome.None;
            _weight = 0;
            _profile = null;
            _gaze?.ResetGaze();
        }

        private void LateUpdate()
        {
            Advance(Time.unscaledDeltaTime);
            ApplyProceduralIk();
        }

        private void OnDisable()
        {
            AbortImmediate();
        }
    }
}
