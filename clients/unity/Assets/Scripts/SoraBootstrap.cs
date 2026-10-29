using System;
using System.IO;
using System.Globalization;
using System.Threading;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Debugging;
using Sora.Embodiment.Native;
using Sora.Embodiment.Network;
using Sora.Embodiment.Presentation;
using Sora.Embodiment.Voice;
using UniVRM10;
using UnityEngine;

namespace Sora.Embodiment
{
    /// <summary>Self-contained scene entrypoint. No credentials, provider, or canonical state in Unity.</summary>
    public sealed class SoraBootstrap : MonoBehaviour
    {
        private readonly CancellationTokenSource _lifetime = new CancellationTokenSource();
        private string _status = "Loading verification avatar...";
        private bool _sample;
        private System.Diagnostics.Process? _coreParent;
        private float _nextParentCheck;

        private async void Start()
        {
            if (int.TryParse(Environment.GetEnvironmentVariable("SORA_CORE_PARENT_PID"), out int parentId))
            {
                try { _coreParent = System.Diagnostics.Process.GetProcessById(parentId); }
                catch (ArgumentException) { Application.Quit(); return; }
            }
            Application.runInBackground = true;
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;
            var camera = new GameObject("Overlay Camera", typeof(Camera)).GetComponent<Camera>();
            camera.tag = "MainCamera";
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.clear;
            camera.allowHDR = false;
            camera.allowMSAA = false;
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 50;
            var light = new GameObject("Avatar Light", typeof(Light)).GetComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(35, -20, 0);
            RenderSettings.ambientLight = Color.white * 0.65f;
            var window = gameObject.AddComponent<WindowPresentation>();
            var avatar = new GameObject("SORA Avatar");
            var motion = avatar.AddComponent<AvatarLocomotion>();
            var gaze = avatar.AddComponent<AvatarLookAt>();
            var presentation = avatar.AddComponent<AvatarPresentationController>();
            var reach = avatar.AddComponent<AvatarReachController>();
            var voicePresentation = avatar.AddComponent<AvatarVoicePresentationController>();
            var poseOwnership = new AvatarPoseOwnership();
            gaze.ConfigurePoseOwnership(poseOwnership);
            presentation.ConfigurePoseOwnership(poseOwnership);
            reach.ConfigurePoseOwnership(poseOwnership);
            var ragdoll = avatar.AddComponent<AvatarRagdollRecoveryController>();
            var marker = new GameObject("SORA Attention Marker").AddComponent<AttentionMarker>();
            var hud = gameObject.AddComponent<DebugOverlayHUD>();
            hud.Configure(motion, gaze, marker);
            hud.IsVisible = Environment.GetEnvironmentVariable("SORA_DEBUG_OVERLAY") == "1";
            var bridge = gameObject.AddComponent<SoraEmbodimentBehaviour>();
            bridge.Configure(motion, gaze, hud, marker, presentation, reach, voicePresentation);
            AvatarPhysicsBody? physicsBody = null;
            var grab = avatar.AddComponent<AvatarGrabController>();
            grab.Configure(motion, () => bridge.CanAcceptPhysicalGrab && !ragdoll.IsActive &&
                physicsBody?.IsFalling != true);
            var simplePhysics = avatar.AddComponent<AvatarSimplePhysicsController>();
            simplePhysics.Configure(motion,
                () => bridge.CanAcceptPhysicalGrab && !motion.IsMoving && !ragdoll.IsActive &&
                    physicsBody?.IsFalling != true);
            var supportSurfaces = avatar.AddComponent<AvatarSupportSurfaceController>();
            supportSurfaces.Configure(motion, simplePhysics);
            bridge.ConfigureSupportPhysics(supportSurfaces);
            bridge.ConfigurePhysicalFeedback(grab, simplePhysics, supportSurfaces);
            window.ConfigureGrab(grab, simplePhysics, ragdoll);
            gameObject.AddComponent<OverlayViewport>().Configure(camera, window, bridge);
            gameObject.AddComponent<PresentationMetrics>().Configure(camera, motion, marker);
            try
            {
                string? configured = Environment.GetEnvironmentVariable("SORA_VRM_PATH");
                _sample = string.IsNullOrWhiteSpace(configured);
                string path = _sample ? Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm") : configured!;
                if (!File.Exists(path)) throw new FileNotFoundException("VRM asset not found");
                // Own spring buffers per avatar so disposal cannot race the global service's next update.
                var instance = await Vrm10.LoadPathAsync(path, canLoadVrm0X: true,
                    springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
                    controlRigGenerationOption: ControlRigGenerationOption.None, ct: _lifetime.Token);
                if (_lifetime.IsCancellationRequested) { Destroy(instance.gameObject); return; }
                instance.transform.SetParent(avatar.transform, false);
                var renderers = instance.GetComponentsInChildren<Renderer>();
                if (renderers.Length == 0) throw new InvalidDataException("VRM contains no renderers");
                var bounds = renderers[0].bounds;
                foreach (var renderer in renderers) bounds.Encapsulate(renderer.bounds);
                if (bounds.size.y < 0.01f) throw new InvalidDataException("Invalid avatar height");
                // 500 physical pixels (1 unit) tall, independent of monitor DPI.
                float height = OverlayPlacement.AvatarHeightPixels / 500f;
                float scale = height / bounds.size.y;
                instance.transform.localScale = Vector3.one * scale;
                instance.transform.localPosition = new Vector3(-(bounds.center.x - avatar.transform.position.x) * scale,
                    -(bounds.min.y - avatar.transform.position.y) * scale, 0);
                var animator = instance.GetComponent<Animator>();
                if (animator == null || !animator.isHuman) throw new InvalidDataException("Humanoid rig required");
                var secondaryMotion = avatar.AddComponent<AvatarSecondaryMotionTuner>();
                voicePresentation.Configure(instance);
                // SORA_SECONDARY_COLLIDERS=0 turns off the body colliders generated for hair and
                // clothing (a diagnostic switch; on by default).
                secondaryMotion.Configure(instance, _sample ? null : path + ".parts.txt",
                    Environment.GetEnvironmentVariable("SORA_SECONDARY_COLLIDERS") != "0");
                simplePhysics.ConfigureSecondaryMotionReset(secondaryMotion.ResetSimulation);
                presentation.ConfigureRig(animator);
                gaze.ConfigureHead(animator.GetBoneTransform(HumanBodyBones.Head));
                // Eyes, blinking and eye-head coordination. SORA_EYE_RIG=0 leaves the eyes
                // still (a diagnostic switch; on by default). Configured while still at rest.
                if (Environment.GetEnvironmentVariable("SORA_EYE_RIG") != "0")
                    avatar.AddComponent<AvatarEyeRig>().Configure(instance, gaze, voicePresentation, camera);
                // Her body is a physics body (motion roadmap MA). SORA_PHYSICS_BODY=0 brings back
                // the posed body and the preset ragdoll; SORA_PHYSICS_HELP sets the help (full,
                // no-exempt, realistic or none; realistic by default).
                if (Environment.GetEnvironmentVariable("SORA_PHYSICS_BODY") != "0")
                {
                    // If her physics body can't be built (an unusual avatar), she keeps her posed
                    // body and the preset fall rather than not appearing at all.
                    var body = avatar.AddComponent<AvatarPhysicsBody>();
                    try
                    {
                        body.Configure(instance, poseOwnership,
                            AvatarPhysicsBody.HelpFor(Environment.GetEnvironmentVariable("SORA_PHYSICS_HELP")), motion);
                        body.Connect(grab, simplePhysics);
                        avatar.AddComponent<AvatarPhysicsPoseRestore>().Body = body;
                        physicsBody = body;
                        bridge.ConfigureMotion(body);
                    }
                    catch (Exception error)
                    {
                        Debug.LogWarning("Physics body unavailable, using the posed body: " + error.GetType().Name + ": " + error.Message);
                        Destroy(body);
                    }
                }
                var idlePose = avatar.AddComponent<AvatarIdlePose>();
                idlePose.Configure(animator, motion, poseOwnership, presentation, reach);
                var modeValue = Environment.GetEnvironmentVariable("SORA_AVATAR_PROACTIVITY") ?? "reactive";
                if (!Enum.TryParse<AvatarProactivityMode>(modeValue, true, out var behaviorMode) ||
                    !Enum.IsDefined(typeof(AvatarProactivityMode), behaviorMode))
                    throw new ArgumentException("Invalid SORA_AVATAR_PROACTIVITY");
                var limitValue = Environment.GetEnvironmentVariable("SORA_AVATAR_DISTRACTION_LIMIT") ?? "1";
                if (!float.TryParse(limitValue, NumberStyles.Float, CultureInfo.InvariantCulture,
                    out var distractionLimit))
                    throw new ArgumentException("Invalid SORA_AVATAR_DISTRACTION_LIMIT");
                idlePose.ConfigureBehavior(behaviorMode, distractionLimit);
                reach.Configure(animator, gaze);
                var collider = avatar.AddComponent<CapsuleCollider>();
                collider.height = height; collider.radius = height * 0.233f;
                collider.center = new Vector3(0, height / 2, 0);
                ragdoll.Configure(animator, poseOwnership, collider);
                ragdoll.ConfigureControllers(reach, gaze, presentation, simplePhysics, grab,
                    secondaryMotion.ResetSimulation);
                // With a physics body, its Connect handles landings (a hard one is a physical fall).
                if (physicsBody == null) simplePhysics.Landed += impact => { ragdoll.TryBeginFromImpact(impact); };
                avatar.AddComponent<AvatarHitTest>();
                bridge.AvatarReady = true;
                avatar.transform.rotation = Quaternion.Euler(0, 180, 0);
                string? ragdollEvidence = Environment.GetEnvironmentVariable(
                    "SORA_RAGDOLL_EVIDENCE_PATH");
                if (!string.IsNullOrWhiteSpace(ragdollEvidence))
                    avatar.AddComponent<RagdollRecoveryEvidenceRunner>().Configure(
                        ragdoll, poseOwnership, ragdollEvidence!);
                string? supportEvidence = Environment.GetEnvironmentVariable(
                    "SORA_SUPPORT_EVIDENCE_PATH");
                if (!string.IsNullOrWhiteSpace(supportEvidence))
                    avatar.AddComponent<SupportSurfaceEvidenceRunner>().Configure(
                        supportSurfaces, simplePhysics, ragdoll, motion, bridge,
                        supportEvidence!);
                _status = "";
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                _status = "Avatar unavailable. Check SORA_VRM_PATH and the player log.";
                Debug.LogError("VRM loading failed: " + e.GetType().Name);
            }
        }

        private void OnGUI()
        {
            if (!string.IsNullOrEmpty(_status)) GUI.Label(new Rect(15, 15, 500, 30), _status);
            if (_sample) GUI.Label(new Rect(15, Screen.height - 28, 560, 24),
                "Sample avatar: Seed-san © VirtualCast, Inc. — VRM Public License 1.0");
        }
        private void Update()
        {
            if (_coreParent == null || Time.realtimeSinceStartup < _nextParentCheck) return;
            _nextParentCheck = Time.realtimeSinceStartup + 1;
            if (_coreParent.HasExited) Application.Quit();
        }

        private void OnDestroy()
        { _lifetime.Cancel(); _lifetime.Dispose(); _coreParent?.Dispose(); }
    }
}
