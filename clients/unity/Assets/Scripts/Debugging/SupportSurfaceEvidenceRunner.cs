using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Network;
using UnityEngine;

namespace Sora.Embodiment.Debugging
{
    /// <summary>Opt-in packaged acceptance for P12.4; inactive without an explicit path.</summary>
    public sealed class SupportSurfaceEvidenceRunner : MonoBehaviour
    {
        [Serializable]
        private sealed class Scenario
        {
            public string invalidation = "";
            public string landed_on = "";
            public string final_support = "";
            public bool resumed_falling;
        }

        [Serializable]
        private sealed class Evidence
        {
            public string recorded_at_utc = "";
            public bool core_snapshot_received;
            public bool moving_surface_carried_avatar;
            public List<Scenario> scenarios = new List<Scenario>();
        }

        private AvatarSupportSurfaceController? _supports;
        private AvatarSimplePhysicsController? _physics;
        private AvatarRagdollRecoveryController? _ragdoll;
        private AvatarLocomotion? _motion;
        private SoraEmbodimentBehaviour? _bridge;
        private string? _path;

        public void Configure(AvatarSupportSurfaceController supports,
            AvatarSimplePhysicsController physics, AvatarRagdollRecoveryController ragdoll,
            AvatarLocomotion motion, SoraEmbodimentBehaviour bridge, string path)
        {
            _supports = supports; _physics = physics; _ragdoll = ragdoll;
            _motion = motion; _bridge = bridge; _path = path;
        }

        private IEnumerator Start()
        {
            if (_supports == null || _physics == null || _ragdoll == null || _motion == null ||
                _bridge == null || string.IsNullOrWhiteSpace(_path)) yield break;
            float deadline = Time.realtimeSinceStartup + 10;
            while ((!_bridge.HasAcceptedTopology || _supports.SelectedWindowCount == 0) &&
                Time.realtimeSinceStartup < deadline) yield return null;
            var evidence = new Evidence
            {
                recorded_at_utc = DateTime.UtcNow.ToString("O"),
                core_snapshot_received = _bridge.HasAcceptedTopology &&
                    _supports.SelectedWindowCount == 1,
            };
            var monitor = _motion.Topology.FindMonitor(
                _motion.GetCurrentGlobalPixelPosition().GlobalX,
                _motion.GetCurrentGlobalPixelPosition().GlobalY) ??
                _motion.Topology.Monitors[0];
            int x = monitor.WorkArea.X + monitor.WorkArea.Width / 2;
            int top = monitor.WorkArea.Bottom - 180;
            var invalidations = new[]
            {
                AvatarSupportSurfaceState.Minimized,
                AvatarSupportSurfaceState.Closed,
                AvatarSupportSurfaceState.Occluded,
            };
            foreach (var invalidation in invalidations)
            {
                var active = Surface(x, top, AvatarSupportSurfaceState.Active);
                _supports.ApplySnapshot(new[] { active }, _motion.Topology.Revision,
                    DateTime.UtcNow);
                _motion.TeleportTo(x, top - 100);
                _physics.LoseSupport();
                yield return WaitForRest();
                string landed = _supports.CurrentSurfaceKind ?? "";
                if (invalidation == AvatarSupportSurfaceState.Minimized)
                {
                    int before = _motion.GetCurrentGlobalPixelPosition().GlobalY;
                    var moved = Surface(x, top - 40, AvatarSupportSurfaceState.Moving);
                    _supports.ApplySnapshot(new[] { moved }, _motion.Topology.Revision,
                        DateTime.UtcNow);
                    evidence.moving_surface_carried_avatar =
                        _motion.GetCurrentGlobalPixelPosition().GlobalY == before - 40;
                    top -= 40;
                }
                var unavailable = Surface(x, top, invalidation);
                _supports.ApplySnapshot(new[] { unavailable }, _motion.Topology.Revision,
                    DateTime.UtcNow);
                bool resumed = _physics.IsActive;
                yield return WaitForRest();
                evidence.scenarios.Add(new Scenario
                {
                    invalidation = invalidation.ToString(),
                    landed_on = landed,
                    final_support = _supports.CurrentSurfaceKind ?? "",
                    resumed_falling = resumed,
                });
            }
            string fullPath = Path.GetFullPath(_path!);
            string directory = Path.GetDirectoryName(fullPath) ?? "";
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            File.WriteAllText(fullPath, JsonUtility.ToJson(evidence, true));
            Debug.Log($"Support surface acceptance: {evidence.scenarios.Count} invalidations");
        }

        private AvatarSupportSurface Surface(int centerX, int top,
            AvatarSupportSurfaceState state) => new AvatarSupportSurface(
                "window:packaged-fixture",
                new ScreenRect(centerX - 250, top, 500, 120), state,
                DateTime.UtcNow.AddSeconds(10));

        private IEnumerator WaitForRest()
        {
            float deadline = Time.realtimeSinceStartup + 6;
            while ((_physics!.IsActive || _ragdoll!.IsActive) &&
                Time.realtimeSinceStartup < deadline) yield return null;
        }
    }
}
