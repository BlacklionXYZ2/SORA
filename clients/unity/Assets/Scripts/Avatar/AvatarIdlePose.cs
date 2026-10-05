using System;
using Sora.Embodiment.Presentation;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public enum AvatarProactivityMode { Quiet, Reactive, Ambient }

    /// <summary>
    /// Bounded local pose only. Ambient mode never selects a desktop target or
    /// starts an action; expressive states still require a Core command.
    /// </summary>
    [DefaultExecutionOrder(20000)]
    public sealed class AvatarIdlePose : MonoBehaviour
    {
        private Transform? _leftArm, _rightArm, _leftLeg, _rightLeg;
        private Quaternion _leftArmRest, _rightArmRest, _leftLegRest, _rightLegRest;
        private AvatarLocomotion _motion = null!;
        private AvatarPresentationController? _presentation;
        private AvatarReachController? _reach;
        private AvatarPoseOwnership? _poseOwnership;
        private AvatarProactivityMode _mode = AvatarProactivityMode.Reactive;
        private float _distractionLimit = 1;

        public void Configure(Animator animator, AvatarLocomotion motion,
            AvatarPoseOwnership? poseOwnership = null,
            AvatarPresentationController? presentation = null,
            AvatarReachController? reach = null)
        {
            if (animator == null) throw new ArgumentNullException(nameof(animator));
            ConfigureRig(
                animator.GetBoneTransform(HumanBodyBones.LeftUpperArm),
                animator.GetBoneTransform(HumanBodyBones.RightUpperArm),
                animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg),
                animator.GetBoneTransform(HumanBodyBones.RightUpperLeg),
                motion, poseOwnership, presentation, reach);
        }

        public void ConfigureRig(Transform leftArm, Transform rightArm, Transform leftLeg,
            Transform rightLeg, AvatarLocomotion motion,
            AvatarPoseOwnership? poseOwnership = null,
            AvatarPresentationController? presentation = null,
            AvatarReachController? reach = null)
        {
            _leftArm = leftArm != null ? leftArm : throw new ArgumentNullException(nameof(leftArm));
            _rightArm = rightArm != null ? rightArm : throw new ArgumentNullException(nameof(rightArm));
            _leftLeg = leftLeg != null ? leftLeg : throw new ArgumentNullException(nameof(leftLeg));
            _rightLeg = rightLeg != null ? rightLeg : throw new ArgumentNullException(nameof(rightLeg));
            _motion = motion != null ? motion : throw new ArgumentNullException(nameof(motion));
            _poseOwnership = poseOwnership;
            _presentation = presentation;
            _reach = reach;
            _leftArmRest = _leftArm.localRotation;
            _rightArmRest = _rightArm.localRotation;
            _leftLegRest = _leftLeg.localRotation;
            _rightLegRest = _rightLeg.localRotation;
        }

        public void ConfigureBehavior(AvatarProactivityMode mode, float distractionLimit = 1)
        {
            if (!Enum.IsDefined(typeof(AvatarProactivityMode), mode))
                throw new ArgumentOutOfRangeException(nameof(mode));
            if (float.IsNaN(distractionLimit) || distractionLimit < 0 || distractionLimit > 1)
                throw new ArgumentOutOfRangeException(nameof(distractionLimit));
            _mode = mode;
            _distractionLimit = distractionLimit;
        }

        public void ApplyPose(float elapsedSeconds)
        {
            if (_poseOwnership?.IsOwned == true || _leftArm == null || _rightArm == null ||
                _leftLeg == null || _rightLeg == null || _motion == null) return;
            var profile = _presentation?.CurrentProfile;
            var commanded = profile != null && _presentation!.CurrentState != "idle";
            var moving = _motion.IsMoving;
            var running = moving && _motion.CurrentSpeedPxPerSec >= 450;
            var gait = moving ? Mathf.Sin(elapsedSeconds * (running ? 12 : 9)) *
                (running ? 34 : 18) : 0;
            var passive = !moving && !commanded && _mode != AvatarProactivityMode.Quiet ?
                Mathf.Sin(elapsedSeconds * 1.7f) *
                (_mode == AvatarProactivityMode.Ambient ? 2.5f : 1.5f) * _distractionLimit : 0;
            var pulse = !moving && commanded ?
                Mathf.Sin(elapsedSeconds * profile!.LimbPulseHz * Mathf.PI * 2) *
                profile.LimbPulseDegrees : 0;
            var leftArmPitch = moving ? gait : passive + (commanded ? profile!.LeftArmPitchDegrees : 0);
            var rightArmPitch = moving ? -gait : -passive +
                (commanded ? profile!.RightArmPitchDegrees + pulse : 0);
            var leftLegPitch = moving ? -gait : commanded ? profile!.LeftLegPitchDegrees + pulse : 0;
            var rightLegPitch = moving ? gait : commanded ? profile!.RightLegPitchDegrees - pulse : 0;
            var reaching = _reach != null && _reach.State != ReachControllerState.Idle;
            if (!reaching)
            {
                _leftArm.localRotation = _leftArmRest * Quaternion.Euler(leftArmPitch, 0, 65);
                _rightArm.localRotation = _rightArmRest * Quaternion.Euler(rightArmPitch, 0, -65);
            }
            _leftLeg.localRotation = _leftLegRest * Quaternion.Euler(leftLegPitch, 0, 0);
            _rightLeg.localRotation = _rightLegRest * Quaternion.Euler(rightLegPitch, 0, 0);
        }

        private void LateUpdate() => ApplyPose(Time.unscaledTime);

        private void OnDisable()
        {
            if (_poseOwnership?.IsOwned == true) return;
            if (_leftArm != null) _leftArm.localRotation = _leftArmRest;
            if (_rightArm != null) _rightArm.localRotation = _rightArmRest;
            if (_leftLeg != null) _leftLeg.localRotation = _leftLegRest;
            if (_rightLeg != null) _rightLeg.localRotation = _rightLegRest;
        }
    }
}
