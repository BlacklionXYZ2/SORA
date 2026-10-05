using System;
using System.Collections.Generic;

namespace Sora.Embodiment.Presentation
{
    public enum PresentationArmPreference
    {
        Nearest,
        Left,
        Right
    }

    /// <summary>
    /// Replaceable visual parameters for one semantic state or action. A profile is
    /// presentation configuration only: it carries no grant and proves no effect.
    /// </summary>
    public sealed class PresentationProfile
    {
        public string ProfileId { get; }
        public float BlendInSeconds { get; }
        public float RetractSeconds { get; }
        public float GazeWeight { get; }
        public float ReachScale { get; }
        public float BodyLeanDegrees { get; }
        public float BodyTiltDegrees { get; }
        public float PulseDegrees { get; }
        public float PulseHz { get; }
        public PresentationArmPreference ArmPreference { get; }
        public float LeftArmPitchDegrees { get; }
        public float RightArmPitchDegrees { get; }
        public float LeftLegPitchDegrees { get; }
        public float RightLegPitchDegrees { get; }
        public float LimbPulseDegrees { get; }
        public float LimbPulseHz { get; }

        public PresentationProfile(
            string profileId,
            float blendInSeconds = 0.18f,
            float retractSeconds = 0.22f,
            float gazeWeight = 0.65f,
            float reachScale = 0.96f,
            float bodyLeanDegrees = 0,
            float bodyTiltDegrees = 0,
            float pulseDegrees = 0,
            float pulseHz = 1,
            PresentationArmPreference armPreference = PresentationArmPreference.Nearest,
            float leftArmPitchDegrees = 0, float rightArmPitchDegrees = 0,
            float leftLegPitchDegrees = 0, float rightLegPitchDegrees = 0,
            float limbPulseDegrees = 0, float limbPulseHz = 1)
        {
            if (string.IsNullOrWhiteSpace(profileId)) throw new ArgumentException("Profile ID is required", nameof(profileId));
            if (blendInSeconds <= 0 || float.IsNaN(blendInSeconds) || float.IsInfinity(blendInSeconds))
                throw new ArgumentOutOfRangeException(nameof(blendInSeconds));
            if (retractSeconds <= 0 || float.IsNaN(retractSeconds) || float.IsInfinity(retractSeconds))
                throw new ArgumentOutOfRangeException(nameof(retractSeconds));
            if (gazeWeight < 0 || gazeWeight > 1 || float.IsNaN(gazeWeight))
                throw new ArgumentOutOfRangeException(nameof(gazeWeight));
            if (reachScale <= 0 || reachScale > 1 || float.IsNaN(reachScale))
                throw new ArgumentOutOfRangeException(nameof(reachScale));
            if (Math.Abs(bodyLeanDegrees) > 30 || float.IsNaN(bodyLeanDegrees))
                throw new ArgumentOutOfRangeException(nameof(bodyLeanDegrees));
            if (Math.Abs(bodyTiltDegrees) > 30 || float.IsNaN(bodyTiltDegrees))
                throw new ArgumentOutOfRangeException(nameof(bodyTiltDegrees));
            if (pulseDegrees < 0 || pulseDegrees > 10 || float.IsNaN(pulseDegrees))
                throw new ArgumentOutOfRangeException(nameof(pulseDegrees));
            if (pulseHz <= 0 || pulseHz > 10 || float.IsNaN(pulseHz))
                throw new ArgumentOutOfRangeException(nameof(pulseHz));
            if (Math.Abs(leftArmPitchDegrees) > 90 || float.IsNaN(leftArmPitchDegrees) ||
                Math.Abs(rightArmPitchDegrees) > 90 || float.IsNaN(rightArmPitchDegrees) ||
                Math.Abs(leftLegPitchDegrees) > 90 || float.IsNaN(leftLegPitchDegrees) ||
                Math.Abs(rightLegPitchDegrees) > 90 || float.IsNaN(rightLegPitchDegrees))
                throw new ArgumentOutOfRangeException(nameof(leftArmPitchDegrees));
            if (limbPulseDegrees < 0 || limbPulseDegrees > 35 || float.IsNaN(limbPulseDegrees))
                throw new ArgumentOutOfRangeException(nameof(limbPulseDegrees));
            if (limbPulseHz <= 0 || limbPulseHz > 10 || float.IsNaN(limbPulseHz))
                throw new ArgumentOutOfRangeException(nameof(limbPulseHz));
            ProfileId = profileId;
            BlendInSeconds = blendInSeconds;
            RetractSeconds = retractSeconds;
            GazeWeight = gazeWeight;
            ReachScale = reachScale;
            BodyLeanDegrees = bodyLeanDegrees;
            BodyTiltDegrees = bodyTiltDegrees;
            PulseDegrees = pulseDegrees;
            PulseHz = pulseHz;
            ArmPreference = armPreference;
            LeftArmPitchDegrees = leftArmPitchDegrees;
            RightArmPitchDegrees = rightArmPitchDegrees;
            LeftLegPitchDegrees = leftLegPitchDegrees;
            RightLegPitchDegrees = rightLegPitchDegrees;
            LimbPulseDegrees = limbPulseDegrees;
            LimbPulseHz = limbPulseHz;
        }
    }

    /// <summary>
    /// Small data registry joining Core semantic names to replaceable presentation
    /// profiles. Adding a state or style does not modify an interaction controller.
    /// </summary>
    public sealed class PresentationProfileRegistry
    {
        private readonly Dictionary<string, PresentationProfile> _states =
            new Dictionary<string, PresentationProfile>(StringComparer.Ordinal);
        private readonly Dictionary<string, PresentationProfile> _actions =
            new Dictionary<string, PresentationProfile>(StringComparer.Ordinal);

        public void RegisterState(string state, PresentationProfile profile, string style = "default") =>
            Register(_states, state, style, profile);

        public void RegisterAction(string action, PresentationProfile profile, string style = "default") =>
            Register(_actions, action, style, profile);

        public PresentationProfile ResolveState(string state, string? style = null) =>
            Resolve(_states, state, style);

        public PresentationProfile ResolveAction(string action, string? style = null) =>
            Resolve(_actions, action, style);

        private static void Register(
            IDictionary<string, PresentationProfile> profiles,
            string semanticName,
            string style,
            PresentationProfile profile)
        {
            if (string.IsNullOrWhiteSpace(semanticName)) throw new ArgumentException("Semantic name is required", nameof(semanticName));
            if (string.IsNullOrWhiteSpace(style)) throw new ArgumentException("Style is required", nameof(style));
            if (profile == null) throw new ArgumentNullException(nameof(profile));
            var key = Key(semanticName, style);
            if (profiles.ContainsKey(key)) throw new InvalidOperationException("Presentation profile is already registered");
            profiles.Add(key, profile);
        }

        private static PresentationProfile Resolve(
            IReadOnlyDictionary<string, PresentationProfile> profiles,
            string semanticName,
            string? style)
        {
            if (string.IsNullOrWhiteSpace(semanticName)) throw new ArgumentException("Semantic name is required", nameof(semanticName));
            if (!string.IsNullOrWhiteSpace(style) && profiles.TryGetValue(Key(semanticName, style!), out var styled))
                return styled;
            if (profiles.TryGetValue(Key(semanticName, "default"), out var fallback)) return fallback;
            throw new KeyNotFoundException("No presentation profile is registered for the semantic name");
        }

        private static string Key(string semanticName, string style) =>
            semanticName.Trim().ToLowerInvariant() + "\n" + style.Trim().ToLowerInvariant();

        public static PresentationProfileRegistry CreateDefaults()
        {
            var registry = new PresentationProfileRegistry();
            registry.RegisterState("idle", new PresentationProfile("state.idle", gazeWeight: 0));
            registry.RegisterState("moving", new PresentationProfile("state.moving", gazeWeight: 0.25f));
            registry.RegisterState("looking", new PresentationProfile("state.looking", gazeWeight: 1));
            registry.RegisterState("thinking", new PresentationProfile("state.thinking.focused",
                blendInSeconds: 0.3f, gazeWeight: 0.35f, bodyLeanDegrees: 5, bodyTiltDegrees: -5,
                pulseDegrees: 1.2f, pulseHz: 0.55f));
            registry.RegisterState("listening", new PresentationProfile("state.listening",
                gazeWeight: 0.8f, bodyLeanDegrees: 2));
            registry.RegisterState("speaking", new PresentationProfile("state.speaking",
                gazeWeight: 0.7f, pulseDegrees: 1.8f, pulseHz: 1.4f));
            registry.RegisterState("waiting_for_agent", new PresentationProfile("state.waiting",
                blendInSeconds: 0.35f, gazeWeight: 0.2f, bodyTiltDegrees: 3, pulseDegrees: 0.8f));
            registry.RegisterState("reading", new PresentationProfile("state.reading",
                gazeWeight: 0.9f, bodyLeanDegrees: 4));
            registry.RegisterState("typing", new PresentationProfile("state.typing",
                gazeWeight: 0.85f, bodyLeanDegrees: 6, pulseDegrees: 1.5f, pulseHz: 2));
            registry.RegisterState("waving", new PresentationProfile("state.waving",
                gazeWeight: 0.7f, rightArmPitchDegrees: -55, limbPulseDegrees: 24,
                limbPulseHz: 1.7f));
            registry.RegisterState("sitting", new PresentationProfile("state.sitting",
                gazeWeight: 0.4f, bodyLeanDegrees: 12, leftLegPitchDegrees: -65,
                rightLegPitchDegrees: -65));
            registry.RegisterState("leaning", new PresentationProfile("state.leaning",
                gazeWeight: 0.65f, bodyLeanDegrees: 14, bodyTiltDegrees: 9));
            registry.RegisterState("climbing", new PresentationProfile("state.climbing",
                gazeWeight: 0.9f, bodyLeanDegrees: -10, leftArmPitchDegrees: -65,
                rightArmPitchDegrees: -65, leftLegPitchDegrees: 20, rightLegPitchDegrees: -20,
                limbPulseDegrees: 24, limbPulseHz: 1.2f));
            registry.RegisterAction("point", new PresentationProfile("action.point", bodyLeanDegrees: 3));
            registry.RegisterAction("press", new PresentationProfile("action.press",
                blendInSeconds: 0.12f, retractSeconds: 0.18f, bodyLeanDegrees: 5));
            registry.RegisterAction("type", new PresentationProfile("action.type",
                blendInSeconds: 0.15f, retractSeconds: 0.15f, bodyLeanDegrees: 5));
            registry.RegisterAction("touch", new PresentationProfile("action.touch",
                blendInSeconds: 0.18f, retractSeconds: 0.2f, bodyLeanDegrees: 4,
                reachScale: 0.96f));
            registry.RegisterAction("place_object", new PresentationProfile("action.place_object",
                blendInSeconds: 0.25f, bodyLeanDegrees: 7));
            return registry;
        }
    }
}
