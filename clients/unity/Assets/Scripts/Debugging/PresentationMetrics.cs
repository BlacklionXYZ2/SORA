using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Sora.Embodiment.Avatar;
using UnityEngine;

namespace Sora.Embodiment.Debugging
{
    /// <summary>Opt-in local presentation evidence, never captures the desktop or credentials.</summary>
    public sealed class PresentationMetrics : MonoBehaviour
    {
        private readonly List<float> _frames = new List<float>(3600);
        private readonly FrameTiming[] _timing = new FrameTiming[1];
        private Camera _camera = null!;
        private AvatarLocomotion _motion = null!;
        private AttentionMarker _marker = null!;
        private string? _directory;
        private float _nextWrite = 65;
        private double _cpuMs, _gpuMs;
        private bool _captured;
        public void Configure(Camera camera, AvatarLocomotion motion, AttentionMarker marker)
        {
            _camera = camera; _motion = motion; _marker = marker;
            _directory = Environment.GetEnvironmentVariable("SORA_PRESENTATION_EVIDENCE_DIR");
        }
        private void Update()
        {
            if (Time.unscaledTime < 5 || string.IsNullOrWhiteSpace(_directory)) return;
            // Capture the first live marker, with a bounded fallback for idle-only runs.
            if (!_captured && (_marker.Point != null || Time.unscaledTime >= 30))
            { CaptureOwnCamera(); _captured = true; }
            if (_frames.Count < 3600) _frames.Add(Time.unscaledDeltaTime * 1000);
            FrameTimingManager.CaptureFrameTimings();
            if (FrameTimingManager.GetLatestTimings(1, _timing) > 0)
            { _cpuMs = _timing[0].cpuFrameTime; _gpuMs = _timing[0].gpuFrameTime; }
            if (Time.unscaledTime >= _nextWrite) { Write(); _nextWrite = Time.unscaledTime + 60; }
        }
        private void Write()
        {
            if (string.IsNullOrWhiteSpace(_directory) || _frames.Count == 0) return;
            // Scene teardown order is unspecified; keep the last complete periodic sample.
            if (_camera == null || _motion == null || _marker == null) return;
            try
            {
                Directory.CreateDirectory(_directory!);
                var sorted = _frames.OrderBy(v => v).ToArray();
                var point = _motion.GetCurrentGlobalPixelPosition();
                var rendered = _camera.WorldToScreenPoint(_motion.transform.position);
                File.WriteAllText(Path.Combine(_directory!, "presentation-metrics.json"), JsonConvert.SerializeObject(new {
                    recorded_at = DateTimeOffset.UtcNow, unity = Application.unityVersion,
                    graphics_api = SystemInfo.graphicsDeviceType.ToString(), samples = sorted.Length,
                    mean_frame_ms = sorted.Average(), p50_frame_ms = sorted[sorted.Length / 2],
                    p95_frame_ms = sorted[(int)((sorted.Length - 1) * 0.95)],
                    latest_cpu_frame_ms = _cpuMs, latest_gpu_frame_ms = _gpuMs,
                    timing_note = "Zero CPU/GPU values mean unavailable. Warmup excluded; bounded first 3600 frames.",
                    global_anchor = new { x = point.GlobalX, y = point.GlobalY },
                    rendered_client_anchor = new { x = rendered.x, y = Screen.height - rendered.y },
                    viewport = new { width = Screen.width, height = Screen.height },
                    marker_target_id = _marker.TargetId,
                    visual_alignment_verified = false,
                    cross_process_click_through_verified = false
                }, Formatting.Indented));
            }
            catch (Exception e) { Debug.LogWarning("Presentation evidence unavailable: " + e.GetType().Name); }
        }
        private void OnDestroy() { Write(); }

        private void CaptureOwnCamera()
        {
            // Render only this camera, never the user's desktop or other applications.
            var previousTarget = _camera.targetTexture;
            var previousActive = RenderTexture.active;
            var target = RenderTexture.GetTemporary(Screen.width, Screen.height, 24, RenderTextureFormat.ARGB32);
            var texture = new Texture2D(Screen.width, Screen.height, TextureFormat.RGBA32, false);
            try
            {
                _camera.targetTexture = target;
                _camera.Render();
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
                texture.Apply();
                Directory.CreateDirectory(_directory!);
                File.WriteAllBytes(Path.Combine(_directory!, "camera.png"), texture.EncodeToPNG());
            }
            finally
            {
                _camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                RenderTexture.ReleaseTemporary(target);
                Destroy(texture);
            }
        }
    }
}
