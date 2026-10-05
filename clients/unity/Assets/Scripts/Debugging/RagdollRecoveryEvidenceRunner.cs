using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Sora.Embodiment.Avatar;
using UnityEngine;

namespace Sora.Embodiment.Debugging
{
    /// <summary>Opt-in packaged-player acceptance probe. Never runs without an explicit path.</summary>
    public sealed class RagdollRecoveryEvidenceRunner : MonoBehaviour
    {
        [Serializable]
        private sealed class ScenarioEvidence
        {
            public string requested = "";
            public string detected = "";
            public string outcome = "";
            public float elapsed_seconds;
        }

        [Serializable]
        private sealed class Evidence
        {
            public string recorded_at_utc = "";
            public int constrained_joint_count;
            public bool body_collision_enabled;
            public bool pose_lease_released;
            public List<ScenarioEvidence> scenarios = new List<ScenarioEvidence>();
        }

        private AvatarRagdollRecoveryController? _controller;
        private AvatarPoseOwnership? _ownership;
        private string? _path;

        public void Configure(AvatarRagdollRecoveryController controller,
            AvatarPoseOwnership ownership, string path)
        {
            _controller = controller ?? throw new ArgumentNullException(nameof(controller));
            _ownership = ownership ?? throw new ArgumentNullException(nameof(ownership));
            _path = string.IsNullOrWhiteSpace(path) ?
                throw new ArgumentException("Evidence path is required", nameof(path)) : path;
        }

        private IEnumerator Start()
        {
            if (_controller == null || _ownership == null || string.IsNullOrWhiteSpace(_path))
                yield break;
            var evidence = new Evidence
            {
                recorded_at_utc = DateTime.UtcNow.ToString("O"),
                constrained_joint_count = _controller.JointCount,
                body_collision_enabled = _controller.HasBodyCollision,
            };
            var scenarios = new[]
            {
                RagdollOrientation.Front,
                RagdollOrientation.Back,
                RagdollOrientation.LeftSide,
                RagdollOrientation.RightSide,
            };
            foreach (var requested in scenarios)
            {
                if (!_controller.BeginRagdoll(requested))
                    throw new InvalidOperationException("Unable to acquire packaged ragdoll pose");
                float elapsed = 0;
                var detected = RagdollOrientation.Upright;
                while (_controller.IsActive && elapsed < 4f)
                {
                    if (_controller.DetectedOrientation != RagdollOrientation.Upright)
                        detected = _controller.DetectedOrientation;
                    elapsed += Time.unscaledDeltaTime;
                    yield return null;
                }
                evidence.scenarios.Add(new ScenarioEvidence
                {
                    requested = requested.ToString(),
                    detected = detected.ToString(),
                    outcome = _controller.LastOutcome.ToString(),
                    elapsed_seconds = elapsed,
                });
                yield return null;
            }
            evidence.pose_lease_released = !_ownership.IsOwned;
            string directory = Path.GetDirectoryName(_path) ?? "";
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            File.WriteAllText(_path, JsonUtility.ToJson(evidence, true));
            Debug.Log($"Ragdoll recovery acceptance: {evidence.scenarios.Count} scenarios, " +
                $"{evidence.constrained_joint_count} constrained joints");
        }
    }
}
