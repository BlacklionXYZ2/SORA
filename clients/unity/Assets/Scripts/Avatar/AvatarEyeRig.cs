using System;
using Sora.Embodiment.Voice;
using UniGLTF.Extensions.VRMC_vrm;
using UniVRM10;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Drives her eyes and eyelids from <see cref="GazeModel"/> and <see cref="BlinkModel"/>.
    /// The eye limits come from each avatar's own VRM look-at settings: a bone avatar (Alice)
    /// turns its eye bones, an expression avatar (Seed-san) uses its look expressions.
    /// Runs after every pose writer, so the eyes are aimed from the head's final pose this frame.
    /// </summary>
    [DefaultExecutionOrder(20030)]
    public sealed class AvatarEyeRig : MonoBehaviour
    {
        /// <summary>Comfortable human eye-in-head range, in degrees. The avatar's own VRM range
        /// is reached at these angles, so every avatar uses all of its authored eye travel.</summary>
        public const float HorizontalRange = 35f, UpRange = 25f, DownRange = 30f;
        private const float LidFollowWeight = 0.15f;

        private Vrm10Instance? _instance;
        private AvatarLookAt? _look;
        private AvatarVoicePresentationController? _voice;
        private Camera? _camera;
        private GazeModel _gaze = new(1);
        private BlinkModel _blink = new(2);
        private Eye? _left, _right;

        public bool IsConfigured => _instance != null;
        public bool UsesEyeBones => _left != null && _right != null;
        public GazeModel Gaze => _gaze;
        public BlinkModel Blink => _blink;
        /// <summary>Eye-in-head angles applied on the last frame, in real-world degrees.</summary>
        public float EyeYaw { get; private set; }
        public float EyePitch { get; private set; }

        private sealed class Eye
        {
            public Transform Bone = null!;
            public Quaternion Pre, Post;
        }

        /// <summary>Call while the avatar is still in its rest pose, right after loading.</summary>
        public void Configure(Vrm10Instance instance, AvatarLookAt? look,
            AvatarVoicePresentationController? voice, Camera? viewer, int seed = 0)
        {
            _instance = instance != null ? instance : throw new ArgumentNullException(nameof(instance));
            _look = look;
            _voice = voice;
            _camera = viewer;
            _gaze = new GazeModel(seed * 2 + 1);
            _blink = new BlinkModel(seed * 2 + 2);
            instance.LookAtTargetType = VRM10ObjectLookAt.LookAtTargetTypes.YawPitchValue;
            var animator = instance.GetComponent<Animator>();
            var leftEye = animator != null ? animator.GetBoneTransform(HumanBodyBones.LeftEye) : null;
            var rightEye = animator != null ? animator.GetBoneTransform(HumanBodyBones.RightEye) : null;
            if (instance.Vrm.LookAt.LookAtType == LookAtType.bone && leftEye != null && rightEye != null)
            {
                _left = Capture(instance.transform, leftEye);
                _right = Capture(instance.transform, rightEye);
            }
        }

        // UniVRM's own bone applier, expressed in the avatar root's frame so it is independent of
        // where the avatar stands or faces: local' = Pre · Euler(pitch, yaw, 0) · Post.
        private static Eye Capture(Transform root, Transform bone)
        {
            var rest = Quaternion.Inverse(root.rotation) * bone.rotation;
            return new Eye { Bone = bone, Pre = bone.localRotation * Quaternion.Inverse(rest), Post = rest };
        }

        private void LateUpdate()
        {
            if (_instance == null) return;
            Step(Time.deltaTime);
        }

        /// <summary>Advances the gaze and blink by one frame and applies them.</summary>
        public void Step(float deltaSeconds)
        {
            if (_instance == null) return;
            var runtime = _instance.Runtime;
            var origin = runtime.LookAt.LookAtOriginTransform;
            var speaking = _voice != null && _voice.ActivePlaybackId != null;
            var mode = _look != null && _look.IsLooking ? GazeMode.Target : GazeMode.Viewer;
            var desired = mode == GazeMode.Target
                ? _look!.TargetWorldPoint - origin.position
                : ViewerDirection();
            var gaze = _gaze.Tick(deltaSeconds, desired, mode, speaking);

            // Eye-in-head angles relative to the head's current pose: this is where the gaze held
            // in world space turns into counter-rotation when the head moves.
            var (yaw, pitch) = runtime.LookAt.CalculateYawPitchFromLookAtPosition(origin.position + gaze);
            yaw = Mathf.Clamp(yaw, -HorizontalRange, HorizontalRange);
            pitch = Mathf.Clamp(pitch, -DownRange, UpRange);
            EyeYaw = yaw;
            EyePitch = pitch;

            var lookAt = _instance.Vrm.LookAt;
            var vrmYaw = yaw / HorizontalRange * lookAt.HorizontalOuter.CurveXRangeDegree;
            var vrmPitch = pitch >= 0
                ? pitch / UpRange * lookAt.VerticalUp.CurveXRangeDegree
                : pitch / DownRange * lookAt.VerticalDown.CurveXRangeDegree;
            // UniVRM applies this on its next pass (expression avatars); bone avatars are also
            // aimed here, this frame, after the head has moved.
            runtime.LookAt.SetYawPitchManually(vrmYaw, vrmPitch);
            if (UsesEyeBones) ApplyBones(lookAt, vrmYaw, vrmPitch);

            var blink = _blink.Tick(deltaSeconds, mode, speaking, _gaze.SaccadeStartedDegrees);
            // Upper lids follow the eyes down a little.
            var lids = UsesEyeBones ? Mathf.Clamp01(-pitch / DownRange) * LidFollowWeight : 0f;
            runtime.Expression.SetWeight(ExpressionKey.Blink, Mathf.Max(blink, lids));
        }

        private Vector3 ViewerDirection()
        {
            // The overlay camera looks into the scene, so the viewer is behind it.
            if (_camera != null) return -_camera.transform.forward;
            return _instance != null ? _instance.transform.forward : Vector3.back;
        }

        private void ApplyBones(VRM10ObjectLookAt lookAt, float yaw, float pitch)
        {
            float leftYaw, rightYaw;
            if (yaw < 0)
            {
                leftYaw = -lookAt.HorizontalOuter.Map(-yaw);
                rightYaw = -lookAt.HorizontalInner.Map(-yaw);
            }
            else
            {
                leftYaw = lookAt.HorizontalInner.Map(yaw);
                rightYaw = lookAt.HorizontalOuter.Map(yaw);
            }
            var bonePitch = pitch < 0 ? lookAt.VerticalDown.Map(-pitch) : -lookAt.VerticalUp.Map(pitch);
            _left!.Bone.localRotation = _left.Pre * Quaternion.Euler(bonePitch, leftYaw, 0) * _left.Post;
            _right!.Bone.localRotation = _right.Pre * Quaternion.Euler(bonePitch, rightYaw, 0) * _right.Post;
        }
    }
}
