using System;
using System.Collections.Generic;
using MotionEnv.AvatarLayer;
using Sora.Embodiment.Network;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Her motion model's stream in her player (2026-10-27). Core relays a model's poses
    /// (<c>embodiment.motion</c>) in 0.4-second chunks; this plays them on a clock kept
    /// <see cref="BufferSeconds"/> behind what has arrived, so a late chunk doesn't stop her.
    /// <list type="bullet">
    /// <item><b>Source:</b> Core says who moves her. Switching blends over
    /// <see cref="BlendSeconds"/>; if chunks stop arriving she blends back to her own poses.</item>
    /// <item><b>Facing:</b> SORA owns where she faces and where she is on screen, so the model's
    /// own heading (smoothed) is taken off her hips, and only its hips height is used.</item>
    /// <item><b>Recording:</b> her realised pose is kept for the last <see cref="RecordSeconds"/>
    /// at <see cref="RecordFps"/>, always, so a Reload motion model can seed the model with what
    /// she was actually doing.</item>
    /// </list>
    /// Everything here is in Unity's frame except what goes back to Core (canonical, motion-lab's
    /// right-handed frame).
    /// </summary>
    public sealed class AvatarMotionStream
    {
        public const float BufferSeconds = 0.5f;
        public const float BlendSeconds = 0.3f;
        public const float RecordSeconds = 3f;
        public const int RecordFps = 20;
        /// <summary>After this long without a chunk she goes back to her own poses.</summary>
        public const float StaleSeconds = 2f;
        public const float HeadingSmoothingSeconds = 0.5f;
        private const double KeepPlayedSeconds = 0.5;

        private sealed class Frame
        {
            public double Time;
            public readonly Quaternion[] Local = new Quaternion[Canonical.Count];
            public Vector3 Root;
            public readonly bool[] Contacts = new bool[4];
        }

        private readonly List<Frame> _frames = new();
        private readonly Frame[] _ring = new Frame[(int)(RecordSeconds * RecordFps)];
        private int _ringStart, _ringCount;
        private float _sinceRecord, _travel;
        private double _clock;
        private bool _clockRunning;
        private bool _modelOwns;
        private float _sinceChunk;
        private float _heading;
        private bool _haveHeading;

        public AvatarMotionStream()
        {
            for (var i = 0; i < _ring.Length; i++) _ring[i] = new Frame();
        }

        /// <summary>Who Core says moves her: "algorithmic" or a model ("ardy").</summary>
        public string Source { get; private set; } = "algorithmic";
        /// <summary>How much of her pose is the model's (0 … 1).</summary>
        public float Weight { get; private set; }
        /// <summary>Seconds of model motion buffered beyond the playback clock.</summary>
        public float Buffered => _frames.Count == 0 ? 0 : (float)(_frames[^1].Time - _clock);
        /// <summary>Times the clock caught up with the buffer and had to wait.</summary>
        public int Underruns { get; private set; }
        /// <summary>Raised when Core asks for her recording (the handover seed).</summary>
        public event Action? SeedRequested;

        /// <summary>The model's smoothed facing, as a unit vector in the canonical frame (x, z):
        /// the direction to ask it to travel in, so it walks the way it already faces.</summary>
        public Vector2 CanonicalForward
        {
            get
            {
                var radians = _heading * Mathf.Deg2Rad;
                return new Vector2(-Mathf.Sin(radians), Mathf.Cos(radians));
            }
        }

        /// <summary>A message from Core (already validated by the transport).</summary>
        public void Accept(MotionMessageDto message)
        {
            switch (message.Op)
            {
                case "source":
                    Source = message.Source ?? "algorithmic";
                    _modelOwns = Source != "algorithmic";
                    break;
                case "record":
                    break; // she always keeps the last few seconds
                case "seed_request":
                    SeedRequested?.Invoke();
                    break;
                case "chunk":
                    AddChunk(message.Chunk!);
                    break;
            }
        }

        /// <summary>Back to her own poses at once (Core is gone).</summary>
        public void Reset()
        {
            Source = "algorithmic";
            _modelOwns = false;
            Weight = 0;
            _frames.Clear();
            _clockRunning = false;
            _haveHeading = false;
        }

        private void AddChunk(MotionChunkDto chunk)
        {
            if (chunk.Seq == 0) // a new stream (a seed or start restarts stream time)
            {
                _frames.Clear();
                _clockRunning = false;
                _haveHeading = false;
            }
            if (!_clockRunning)
            {
                _clock = chunk.T0 - BufferSeconds;
                _clockRunning = true;
            }
            // A newer plan replaces anything it overlaps.
            _frames.RemoveAll(f => f.Time >= chunk.T0 - 1e-4);
            var step = 1.0 / chunk.Fps;
            for (var i = 0; i < chunk.Frames.Count; i++)
            {
                var dto = chunk.Frames[i];
                var frame = new Frame { Time = chunk.T0 + i * step };
                for (var j = 0; j < Canonical.Count; j++)
                {
                    var q = dto.Rot[j];
                    frame.Local[j] = Canonical.ToUnity(new Quaternion(q[0], q[1], q[2], q[3]).normalized);
                }
                frame.Root = Canonical.ToUnity(new Vector3(dto.Root[0], dto.Root[1], dto.Root[2]));
                Array.Copy(dto.Contacts, frame.Contacts, 4);
                _frames.Add(frame);
            }
            _sinceChunk = 0;
        }

        /// <summary>Moves the clock on and samples the model's pose into <paramref name="pose"/>
        /// (heading removed, root at the origin but for its height). False when there is
        /// nothing to play.</summary>
        public bool Advance(float deltaTime, CanonicalPose pose)
        {
            _sinceChunk += deltaTime;
            var playing = _frames.Count > 0;
            var owns = _modelOwns && playing && _sinceChunk < StaleSeconds;
            Weight = Mathf.MoveTowards(Weight, owns ? 1f : 0f, deltaTime / BlendSeconds);
            if (!playing) return false;
            if (!_modelOwns && Weight <= 0)
            {
                // Blended out: nothing more to play until the model owns her again.
                _frames.Clear();
                _clockRunning = false;
                _haveHeading = false;
                return false;
            }

            // Hold the buffer near its target: a few percent faster or slower, never a jump.
            var last = _frames[^1].Time;
            var ahead = last - _clock;
            var rate = 1 + Mathf.Clamp((float)(ahead - (BufferSeconds + 0.2)) * 0.1f, -0.05f, 0.05f);
            var before = _clock;
            _clock += deltaTime * rate;
            if (_clock > last)
            {
                if (before < last) Underruns++;
                _clock = last;
            }
            while (_frames.Count > 2 && _frames[1].Time < _clock - KeepPlayedSeconds) _frames.RemoveAt(0);
            Sample(_clock, pose);

            // The model's facing, smoothed so her pelvis keeps its own twist within a stride.
            var forward = pose.Local[0] * Vector3.forward;
            var yaw = Mathf.Atan2(forward.x, forward.z) * Mathf.Rad2Deg;
            if (!_haveHeading) { _heading = yaw; _haveHeading = true; }
            else _heading += Mathf.DeltaAngle(_heading, yaw) * (1 - Mathf.Exp(-deltaTime / HeadingSmoothingSeconds));
            pose.Local[0] = Quaternion.AngleAxis(-_heading, Vector3.up) * pose.Local[0];
            pose.Root = new Vector3(0, pose.Root.y, 0);
            return true;
        }

        private void Sample(double time, CanonicalPose pose)
        {
            var b = 0;
            while (b < _frames.Count - 1 && _frames[b + 1].Time <= time) b++;
            var from = _frames[b];
            var to = b + 1 < _frames.Count ? _frames[b + 1] : from;
            var span = to.Time - from.Time;
            var t = span > 1e-6 ? Mathf.Clamp01((float)((time - from.Time) / span)) : 0f;
            for (var j = 0; j < Canonical.Count; j++) pose.Local[j] = Quaternion.Slerp(from.Local[j], to.Local[j], t);
            pose.Root = Vector3.Lerp(from.Root, to.Root, t);
            var nearer = t < 0.5f ? from : to;
            Array.Copy(nearer.Contacts, pose.Contacts, 4);
        }

        /// <summary>
        /// Keeps her realised pose for the handover seed: canonical local rotations (Unity's
        /// frame, her facing taken off), the canonical hips height, and how fast she travels
        /// (canonical metres a second). Her travel goes along +Z, the way the seed faces.
        /// </summary>
        public void Record(float deltaTime, Quaternion[] canonicalLocal, float hipsHeight, float speed)
        {
            _travel += speed * deltaTime;
            if (_travel > 1000) // keep float precision over hours of walking
            {
                _travel -= 1000;
                foreach (var f in _ring) f.Root.z -= 1000;
            }
            _sinceRecord += deltaTime;
            const float period = 1f / RecordFps;
            if (_sinceRecord < period - 1e-4f && _ringCount > 0) return;
            // One frame per period; a long frame doesn't record a burst of copies.
            _sinceRecord = Mathf.Clamp(_sinceRecord - period, 0, period);
            int slot;
            if (_ringCount < _ring.Length) slot = (_ringStart + _ringCount++) % _ring.Length;
            else { slot = _ringStart; _ringStart = (_ringStart + 1) % _ring.Length; }
            var frame = _ring[slot];
            Array.Copy(canonicalLocal, frame.Local, Canonical.Count);
            frame.Root = new Vector3(0, hipsHeight, _travel);
        }

        /// <summary>Recorded frames kept (at <see cref="RecordFps"/>).</summary>
        public int RecordedFrames => _ringCount;

        /// <summary>Her recording as seed frames, oldest first, in the canonical frame.</summary>
        public MotionFrameDto[] Seed()
        {
            var frames = new MotionFrameDto[_ringCount];
            var start = _ring[_ringStart].Root.z;
            for (var k = 0; k < _ringCount; k++)
            {
                var frame = _ring[(_ringStart + k) % _ring.Length];
                var rot = new float[Canonical.Count][];
                for (var j = 0; j < Canonical.Count; j++)
                {
                    var q = Canonical.FromUnity(frame.Local[j]).normalized;
                    rot[j] = new[] { q.x, q.y, q.z, q.w };
                }
                // Canonical root: x mirrored (zero here), travel measured from the first frame.
                var root = Canonical.FromUnity(new Vector3(0, frame.Root.y, frame.Root.z - start));
                frames[k] = new MotionFrameDto { Root = new[] { root.x, root.y, root.z }, Rot = rot,
                    Contacts = new bool[4] };
            }
            return frames;
        }
    }
}
