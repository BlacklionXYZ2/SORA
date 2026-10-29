using System;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    /// <summary>What the eyes are attending to this tick.</summary>
    public enum GazeMode
    {
        /// <summary>No commanded target: she looks at the viewer, with glances away.</summary>
        Viewer,
        /// <summary>A commanded target (a window, a control, the pointer).</summary>
        Target,
    }

    /// <summary>
    /// Where the eyes point, from published oculomotor measurements rather than a learned model.
    /// The gaze is held as a world direction, so when the head or body turns the eyes stay on
    /// their target (the vestibulo-ocular reflex) without extra work.
    /// <list type="bullet">
    /// <item>Saccades: ballistic jumps whose duration follows the main sequence
    /// (about 21 ms + 2.2 ms per degree) with peak speed capped near 500°/s.</item>
    /// <item>Fixations: holds of a few hundred milliseconds, with small jumps around the target.</item>
    /// <item>Smooth pursuit: errors below the saccade threshold are followed at up to 40°/s.</item>
    /// <item>Glances: at the viewer she looks away now and then, and often when she starts
    /// speaking (thinking), then comes back.</item>
    /// </list>
    /// </summary>
    public sealed class GazeModel
    {
        public const float SaccadeThresholdDegrees = 2.0f;
        public const float PursuitDegreesPerSecond = 40f;
        public const float PeakSaccadeDegreesPerSecond = 500f;

        private readonly System.Random _random;
        private Vector3 _from, _to;
        private float _saccadeElapsed, _saccadeDuration;
        private Vector2 _offset; // degrees (yaw, pitch) around the desired direction
        private float _nextFixationShift;
        private float _glanceRemaining, _nextGlance;
        private bool _wasSpeaking;
        private bool _initialised;

        public GazeModel(int seed)
        {
            _random = new System.Random(seed);
            _nextGlance = Range(2f, 6f);
        }

        /// <summary>The current gaze direction (world space, unit length).</summary>
        public Vector3 Direction { get; private set; } = Vector3.forward;
        public bool InSaccade => _saccadeDuration > 0;
        /// <summary>Amplitude in degrees of a saccade started on the last tick, else 0.</summary>
        public float SaccadeStartedDegrees { get; private set; }
        public bool Glancing => _glanceRemaining > 0;

        /// <summary>Main-sequence duration in seconds for a saccade of the given amplitude.</summary>
        public static float SaccadeDuration(float amplitudeDegrees)
        {
            var mainSequence = 0.021f + 0.0022f * amplitudeDegrees;
            // A minimum-jerk profile peaks at 1.875 × mean speed; keep that below the cap.
            var speedLimited = 1.875f * amplitudeDegrees / PeakSaccadeDegreesPerSecond;
            return Mathf.Max(mainSequence, speedLimited);
        }

        /// <summary>Minimum-jerk position profile, 0 to 1.</summary>
        public static float Profile(float t)
        {
            t = Mathf.Clamp01(t);
            return t * t * t * (10f + t * (-15f + 6f * t));
        }

        public Vector3 Tick(float deltaSeconds, Vector3 desiredDirection, GazeMode mode, bool speaking)
        {
            SaccadeStartedDegrees = 0;
            if (deltaSeconds <= 0 || desiredDirection.sqrMagnitude < 1e-8f) return Direction;
            desiredDirection.Normalize();
            if (!_initialised)
            {
                Direction = desiredDirection;
                _initialised = true;
            }

            UpdateIntent(deltaSeconds, mode, speaking);
            var goal = Offset(desiredDirection, _offset);

            if (InSaccade)
            {
                _saccadeElapsed += deltaSeconds;
                var t = _saccadeElapsed / _saccadeDuration;
                Direction = Vector3.Slerp(_from, _to, Profile(t)).normalized;
                if (t >= 1f) { Direction = _to; _saccadeDuration = 0; }
                return Direction;
            }

            var error = Vector3.Angle(Direction, goal);
            if (error > SaccadeThresholdDegrees)
            {
                _from = Direction;
                _to = goal;
                _saccadeElapsed = 0;
                _saccadeDuration = SaccadeDuration(error);
                SaccadeStartedDegrees = error;
                // The first tick of a saccade already moves.
                _saccadeElapsed = Mathf.Min(deltaSeconds, _saccadeDuration);
                Direction = Vector3.Slerp(_from, _to, Profile(_saccadeElapsed / _saccadeDuration)).normalized;
                if (_saccadeElapsed >= _saccadeDuration) { Direction = _to; _saccadeDuration = 0; }
                return Direction;
            }

            var step = PursuitDegreesPerSecond * deltaSeconds;
            Direction = Vector3.RotateTowards(Direction, goal, step * Mathf.Deg2Rad, 0f).normalized;
            return Direction;
        }

        private void UpdateIntent(float dt, GazeMode mode, bool speaking)
        {
            var speechOnset = speaking && !_wasSpeaking;
            _wasSpeaking = speaking;

            if (_glanceRemaining > 0)
            {
                _glanceRemaining -= dt;
                if (_glanceRemaining <= 0 || mode == GazeMode.Target)
                {
                    _glanceRemaining = 0;
                    _offset = Vector2.zero;
                    _nextGlance = Range(2.5f, 7f);
                    _nextFixationShift = Range(0.4f, 1.0f);
                }
                return;
            }

            if (mode == GazeMode.Viewer)
            {
                _nextGlance -= dt;
                // Looking away while starting to speak, as people do while they think.
                var thinking = speechOnset && _random.NextDouble() < 0.6;
                if (thinking || _nextGlance <= 0)
                {
                    var side = _random.NextDouble() < 0.5 ? -1f : 1f;
                    _offset = new Vector2(side * Range(8f, 18f), thinking ? Range(-12f, -4f) : Range(-8f, 4f));
                    _glanceRemaining = thinking ? Range(0.8f, 1.8f) : Range(0.4f, 1.2f);
                    return;
                }
            }

            // Small fixational shifts around the target: wider over a window than on the viewer.
            _nextFixationShift -= dt;
            if (_nextFixationShift <= 0)
            {
                var spread = mode == GazeMode.Target ? 2.5f : 1.2f;
                _offset = new Vector2(Range(-spread, spread), Range(-spread, spread) * 0.6f);
                _nextFixationShift = mode == GazeMode.Target ? Range(0.3f, 0.9f) : Range(0.6f, 1.6f);
            }
        }

        /// <summary>Turns a direction by yaw (about world up) and pitch (about its own right axis).</summary>
        public static Vector3 Offset(Vector3 direction, Vector2 yawPitchDegrees)
        {
            if (yawPitchDegrees == Vector2.zero) return direction;
            var right = Vector3.Cross(Vector3.up, direction);
            if (right.sqrMagnitude < 1e-6f) right = Vector3.right;
            var turned = Quaternion.AngleAxis(yawPitchDegrees.x, Vector3.up) *
                Quaternion.AngleAxis(-yawPitchDegrees.y, right.normalized) * direction;
            return turned.normalized;
        }

        private float Range(float min, float max) => min + (float)_random.NextDouble() * (max - min);
    }

    /// <summary>
    /// Blinking from measured rates: about 15 to 20 a minute at rest, more while speaking, fewer
    /// while attending to something. A quick close, a brief hold and a slower opening; sometimes a
    /// double blink; and a likely blink with a large gaze shift.
    /// </summary>
    public sealed class BlinkModel
    {
        public const float CloseSeconds = 0.07f;
        public const float HoldSeconds = 0.04f;
        public const float OpenSeconds = 0.14f;
        private const float MinimumGap = 0.6f;

        private readonly System.Random _random;
        private float _untilNext;
        private float _phase = -1; // seconds into the current blink, or -1
        private float _sinceLast = 10f;
        private bool _doublePending;

        public BlinkModel(int seed)
        {
            _random = new System.Random(seed);
            _untilNext = Interval(GazeMode.Viewer, false);
        }

        public float Weight { get; private set; }
        public int Count { get; private set; }

        /// <summary>Mean interval in seconds for the state (a resting rate of about 17 a minute).</summary>
        public static float MeanInterval(GazeMode mode, bool speaking) =>
            speaking ? 2.6f : mode == GazeMode.Target ? 4.8f : 3.5f;

        public float Tick(float deltaSeconds, GazeMode mode, bool speaking, float saccadeDegrees)
        {
            if (deltaSeconds <= 0) return Weight;
            _sinceLast += deltaSeconds;
            if (_phase < 0)
            {
                _untilNext -= deltaSeconds;
                var gazeEvoked = saccadeDegrees > 20f && _sinceLast > MinimumGap &&
                    _random.NextDouble() < Mathf.Clamp01((saccadeDegrees - 20f) / 40f + 0.3f);
                if (_untilNext <= 0 || gazeEvoked) Start();
            }
            if (_phase >= 0)
            {
                _phase += deltaSeconds;
                Weight = Shape(_phase);
                if (_phase >= CloseSeconds + HoldSeconds + OpenSeconds)
                {
                    _phase = -1;
                    Weight = 0;
                    if (_doublePending) { _doublePending = false; _untilNext = 0.12f; }
                    else _untilNext = Interval(mode, speaking);
                }
            }
            return Weight;
        }

        /// <summary>Lid closure 0 to 1 at a time into a blink.</summary>
        public static float Shape(float t)
        {
            if (t < CloseSeconds) { var c = t / CloseSeconds; return c * c; }
            if (t < CloseSeconds + HoldSeconds) return 1f;
            var o = (t - CloseSeconds - HoldSeconds) / OpenSeconds;
            return o >= 1f ? 0f : 1f - o * (2f - o);
        }

        private void Start()
        {
            _phase = 0;
            _sinceLast = 0;
            Count++;
            if (!_doublePending && _random.NextDouble() < 0.1) _doublePending = true;
        }

        private float Interval(GazeMode mode, bool speaking)
        {
            // A minimum gap plus an exponential remainder, so intervals vary naturally.
            var mean = MeanInterval(mode, speaking);
            var u = Math.Max(1e-6, _random.NextDouble());
            return MinimumGap + (float)(-Math.Log(u)) * (mean - MinimumGap);
        }
    }
}
