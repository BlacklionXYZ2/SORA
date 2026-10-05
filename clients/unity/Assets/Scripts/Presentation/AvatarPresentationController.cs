using System;
using UnityEngine;

namespace Sora.Embodiment.Presentation
{
    /// <summary>
    /// Holds the active semantic presentation profile. It deliberately has no
    /// authority, desktop side effect, or effect-verification API.
    /// </summary>
    [DefaultExecutionOrder(19990)]
    public sealed class AvatarPresentationController : MonoBehaviour
    {
        private PresentationProfileRegistry _profiles = PresentationProfileRegistry.CreateDefaults();
        private Transform? _poseTransform;
        private Quaternion _restRotation;
        private Quaternion _transitionStart;
        private float _transitionElapsed;
        private float _presentationTime;
        private Sora.Embodiment.Avatar.AvatarPoseOwnership? _poseOwnership;

        public string CurrentState { get; private set; } = "idle";
        public string CurrentStyle { get; private set; } = "default";
        public PresentationProfile CurrentProfile { get; private set; } = null!;
        public bool IsPoseOwned => _poseOwnership?.IsOwned == true;
        public event Action<PresentationProfile>? OnProfileChanged;

        public void ConfigurePoseOwnership(
            Sora.Embodiment.Avatar.AvatarPoseOwnership poseOwnership) =>
            _poseOwnership = poseOwnership ?? throw new ArgumentNullException(nameof(poseOwnership));

        private void Awake()
        {
            CurrentProfile = _profiles.ResolveState(CurrentState);
        }

        public void Configure(PresentationProfileRegistry profiles)
        {
            _profiles = profiles ?? throw new ArgumentNullException(nameof(profiles));
            SetState("idle");
        }

        public void ConfigureRig(Animator animator)
        {
            if (animator == null) throw new ArgumentNullException(nameof(animator));
            var pose = animator.GetBoneTransform(HumanBodyBones.UpperChest) ??
                animator.GetBoneTransform(HumanBodyBones.Chest) ??
                animator.GetBoneTransform(HumanBodyBones.Spine);
            if (pose == null) throw new ArgumentException("Humanoid torso bone required", nameof(animator));
            ConfigurePoseTransform(pose);
        }

        public void ConfigurePoseTransform(Transform poseTransform)
        {
            _poseTransform = poseTransform != null ? poseTransform :
                throw new ArgumentNullException(nameof(poseTransform));
            _restRotation = _poseTransform.localRotation;
            _transitionStart = _restRotation;
            _transitionElapsed = 0;
            _presentationTime = 0;
        }

        public PresentationProfile SetState(string state, string? style = null)
        {
            var profile = _profiles.ResolveState(state, style);
            CurrentState = state.Trim().ToLowerInvariant();
            CurrentStyle = string.IsNullOrWhiteSpace(style) ? "default" : style!.Trim().ToLowerInvariant();
            Activate(profile);
            return profile;
        }

        public PresentationProfile PresentAction(string action, string? style = null)
        {
            var profile = _profiles.ResolveAction(action, style);
            Activate(profile);
            return profile;
        }

        public void ResetToIdle() => SetState("idle");

        public void Advance(float deltaSeconds)
        {
            if (deltaSeconds < 0 || float.IsNaN(deltaSeconds) || float.IsInfinity(deltaSeconds))
                throw new ArgumentOutOfRangeException(nameof(deltaSeconds));
            _transitionElapsed += deltaSeconds;
            _presentationTime += deltaSeconds;
        }

        public void ApplyPose()
        {
            if (_poseOwnership?.IsOwned == true) return;
            if (_poseTransform == null || CurrentProfile == null) return;
            var pulse = Mathf.Sin(_presentationTime * CurrentProfile.PulseHz * Mathf.PI * 2) *
                CurrentProfile.PulseDegrees;
            var target = _restRotation * Quaternion.Euler(CurrentProfile.BodyLeanDegrees, 0,
                CurrentProfile.BodyTiltDegrees + pulse);
            var progress = Mathf.Clamp01(_transitionElapsed / CurrentProfile.BlendInSeconds);
            _poseTransform.localRotation = Quaternion.Slerp(_transitionStart, target, progress);
        }

        private void Activate(PresentationProfile profile)
        {
            if (_poseTransform != null) _transitionStart = _poseTransform.localRotation;
            CurrentProfile = profile;
            _transitionElapsed = 0;
            _presentationTime = 0;
            OnProfileChanged?.Invoke(profile);
        }

        private void LateUpdate()
        {
            Advance(Time.unscaledDeltaTime);
            ApplyPose();
        }

        private void OnDisable()
        {
            if (_poseTransform != null) _poseTransform.localRotation = _restRotation;
        }
    }
}
