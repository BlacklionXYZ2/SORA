using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using UniVRM10;
using UnityEngine;

namespace Sora.Embodiment.Voice
{
    public enum VoicePresentationResetReason
    {
        Completed,
        Paused,
        Interrupted,
        DeviceLost,
        Disconnected,
        Failed
    }

    /// <summary>
    /// Client-local audio-derived presentation frame. This is deliberately absent from the Core
    /// command DTO and cannot be supplied by a dialogue model.
    /// </summary>
    public readonly struct VoicePresentationFrame
    {
        public string PlaybackId { get; }
        public long OutputEpoch { get; }
        public int Sequence { get; }
        public double PositionMs { get; }
        public double DurationMs { get; }
        public float MouthOpen { get; }
        public string Emotion { get; }

        public VoicePresentationFrame(string playbackId, long outputEpoch, int sequence,
            double positionMs, double durationMs, float mouthOpen, string emotion)
        {
            if (string.IsNullOrWhiteSpace(playbackId))
                throw new ArgumentException("Playback identity is required", nameof(playbackId));
            if (outputEpoch < 0) throw new ArgumentOutOfRangeException(nameof(outputEpoch));
            if (sequence < 0 || sequence > 1_000_000)
                throw new ArgumentOutOfRangeException(nameof(sequence));
            if (positionMs < 0 || positionMs > 86_400_000 || double.IsNaN(positionMs) ||
                double.IsInfinity(positionMs)) throw new ArgumentOutOfRangeException(nameof(positionMs));
            if (durationMs <= 0 || durationMs > 1_000 || double.IsNaN(durationMs) ||
                double.IsInfinity(durationMs)) throw new ArgumentOutOfRangeException(nameof(durationMs));
            if (mouthOpen < 0 || mouthOpen > 1 || float.IsNaN(mouthOpen) ||
                float.IsInfinity(mouthOpen)) throw new ArgumentOutOfRangeException(nameof(mouthOpen));
            Emotion = NormalizeEmotion(emotion);
            PlaybackId = playbackId;
            OutputEpoch = outputEpoch;
            Sequence = sequence;
            PositionMs = positionMs;
            DurationMs = durationMs;
            MouthOpen = mouthOpen;
        }

        internal static string NormalizeEmotion(string emotion)
        {
            string normalized = (emotion ?? string.Empty).Trim().ToLowerInvariant();
            return normalized switch
            {
                "neutral" or "warm" or "cheerful" or "concerned" or "focused" => normalized,
                _ => throw new ArgumentException("Unknown voice emotion", nameof(emotion))
            };
        }
    }

    /// <summary>
    /// Applies an ordered local audio clock to VRM mouth/emotion expressions. No desktop authority,
    /// task result, model text, or Core animation frame enters this controller.
    /// </summary>
    public sealed class AvatarVoicePresentationController : MonoBehaviour
    {
        private Vrm10Instance? _avatar;
        private long _latestEpoch = -1;
        private int _nextSequence;
        private double _nextPositionMs;
        private float _lastFrameTime;
        private readonly string? _evidencePath = Environment.GetEnvironmentVariable("SORA_VOICE_EVIDENCE_PATH");
        private readonly List<object> _evidence = new List<object>();
        private int _evidenceFramesRemaining;

        public string? ActivePlaybackId { get; private set; }
        public long ActiveOutputEpoch { get; private set; } = -1;
        public float MouthOpen { get; private set; }
        public string Emotion { get; private set; } = "neutral";
        public VoicePresentationResetReason? LastResetReason { get; private set; }

        public void Configure(Vrm10Instance avatar) =>
            _avatar = avatar != null ? avatar : throw new ArgumentNullException(nameof(avatar));

        public bool Begin(string playbackId, long outputEpoch, string emotion)
        {
            if (string.IsNullOrWhiteSpace(playbackId) || outputEpoch < 0) return false;
            string normalized;
            try { normalized = VoicePresentationFrame.NormalizeEmotion(emotion); }
            catch (ArgumentException) { return false; }
            if (outputEpoch < _latestEpoch) return false;
            if (ActivePlaybackId != null)
                return ActivePlaybackId == playbackId && ActiveOutputEpoch == outputEpoch;
            ActivePlaybackId = playbackId;
            ActiveOutputEpoch = outputEpoch;
            _latestEpoch = Math.Max(_latestEpoch, outputEpoch);
            _nextSequence = 0;
            _nextPositionMs = 0;
            _lastFrameTime = Time.realtimeSinceStartup;
            MouthOpen = 0;
            Emotion = normalized;
            LastResetReason = null;
            ApplyExpressions();
            return true;
        }

        public bool ApplyFrame(VoicePresentationFrame frame)
        {
            if (ActivePlaybackId != frame.PlaybackId || ActiveOutputEpoch != frame.OutputEpoch)
                return false;
            if (frame.Sequence != _nextSequence ||
                Math.Abs(frame.PositionMs - _nextPositionMs) > 1.0)
                return false;
            if (frame.Emotion != Emotion) return false;
            MouthOpen = frame.MouthOpen;
            _lastFrameTime = Time.realtimeSinceStartup;
            _nextSequence++;
            _nextPositionMs = frame.PositionMs + frame.DurationMs;
            ApplyExpressions();
            return true;
        }

        public bool Reset(string playbackId, long outputEpoch,
            VoicePresentationResetReason reason)
        {
            if (ActivePlaybackId != playbackId || ActiveOutputEpoch != outputEpoch) return false;
            ResetAll(reason);
            return true;
        }

        public void ResetAll(VoicePresentationResetReason reason)
        {
            ActivePlaybackId = null;
            ActiveOutputEpoch = -1;
            _nextSequence = 0;
            _nextPositionMs = 0;
            MouthOpen = 0;
            Emotion = "neutral";
            LastResetReason = reason;
            ApplyExpressions();
        }

        public void ResetTransport()
        {
            ResetAll(VoicePresentationResetReason.Disconnected);
            _latestEpoch = -1; // A new owned worker has a new session-local epoch domain.
        }

        private void Update()
        {
            // Gaps in synthesis, transport stalls and worker crashes must not freeze an open mouth.
            if (MouthOpen > 0 && Time.realtimeSinceStartup - _lastFrameTime > 0.35f)
            { MouthOpen = 0; ApplyExpressions(); }
        }

        private void ApplyExpressions()
        {
            if (_avatar == null) return;
            var expressions = _avatar.Runtime.Expression;
            expressions.SetWeight(ExpressionKey.Aa, MouthOpen);
            expressions.SetWeight(ExpressionKey.Happy, Emotion == "cheerful" ? 0.35f : 0);
            expressions.SetWeight(ExpressionKey.Relaxed, Emotion == "warm" ? 0.25f : 0);
            expressions.SetWeight(ExpressionKey.Sad, Emotion == "concerned" ? 0.2f : 0);
            expressions.SetWeight(ExpressionKey.Neutral, Emotion == "focused" ? 0.15f : 0);
            // Opt-in fixture evidence only; ordinary Core avatar launches strip evidence flags.
            if (!string.IsNullOrEmpty(_evidencePath)) _evidenceFramesRemaining = 2;
        }

        private void LateUpdate()
        {
            if (_avatar != null && _evidenceFramesRemaining > 0 && _evidence.Count < 400)
            {
                _evidenceFramesRemaining--;
                var expressions = _avatar.Runtime.Expression;
                _evidence.Add(new { recorded_at = DateTime.UtcNow, playback_id = ActivePlaybackId,
                    output_epoch = ActiveOutputEpoch, mouth_open = MouthOpen,
                    vrm_mouth_weight = expressions.GetWeight(ExpressionKey.Aa), emotion = Emotion,
                    vrm_applied_weight = expressions.ActualWeights.TryGetValue(ExpressionKey.Aa, out var weight) ? weight : 0,
                    reset_reason = LastResetReason?.ToString() });
                try { File.WriteAllText(_evidencePath, JsonConvert.SerializeObject(_evidence)); }
                catch (IOException) { Debug.LogWarning("Voice fixture evidence write unavailable"); }
            }
        }

        private void OnDisable() => ResetAll(VoicePresentationResetReason.Disconnected);
    }
}
