using System;
using System.Linq;
using MotionEnv.AvatarLayer;
using UniVRM10;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Sora.Embodiment.Avatar
{
    /// <summary>What has her body right now.</summary>
    public enum PhysicsBodyMode
    {
        /// <summary>On a surface: SORA's animation drives the motors; SORA places her on screen.</summary>
        Standing,
        /// <summary>Picked up, or carried through the air by SORA's drop: she hangs loosely from
        /// where she was grabbed (her hips if she wasn't), with nothing under her.</summary>
        Held,
        /// <summary>A physical fall and getting up: her body has itself; SORA follows it.</summary>
        Falling,
    }

    /// <summary>
    /// Motion roadmap MA in SORA's player: her body is a physics body (built and measured in
    /// motion-lab's training environment, <c>Assets/Scripts/AvatarLayer</c>).
    /// <list type="bullet">
    /// <item>It simulates at her real size in metres, at 120 Hz, in its own physics scene, in a
    /// fixed frame (world divided by her display scale). Her 500-pixel body shows the result.</item>
    /// <item><b>Standing:</b> SORA's animation is what the joint motors aim for; walking and
    /// running use the stand-in gait (feet lifted, stride and cadence matched to speed, a moment
    /// in the air when running), and the surface she stands on is solid.</item>
    /// <item><b>Held</b> (grabbed, or dropping through the air): she hangs at low muscle tone from
    /// the point she was grabbed by, and nothing starts a fall.</item>
    /// <item><b>Falling:</b> a hard landing, or her body tipping over by itself, is a physical
    /// fall: SORA stops moving her, she settles and gets up (stand-in), and SORA then moves her
    /// on screen to where her body actually is.</item>
    /// <item>Only one side ever owns her position, so nothing pulls her across the screen; if the
    /// two disagree by more than half a metre, her body is moved, not dragged.</item>
    /// </list>
    /// </summary>
    [DefaultExecutionOrder(20025)]
    public sealed class AvatarPhysicsBody : MonoBehaviour
    {
        public const float Step = 1f / 120f;
        /// <summary>At most this many physics steps a frame; a slower frame lets her fall behind
        /// rather than spiral (the resync catches up).</summary>
        public const int MaxStepsPerFrame = 8;
        public const float PixelsPerUnit = 500f;
        /// <summary>A landing at least this fast (px/s, downward) becomes a fall, as before.</summary>
        public const float FallImpactPxPerSecond = 1000f;
        /// <summary>Muscle tone while she is held: loose, as the owner wanted when picked up.</summary>
        public const float HeldTone = 0.3f;
        /// <summary>A hand holding her is stronger than the balance helper may be.</summary>
        public const float HeldStrength = 4f;
        /// <summary>Further apart than this (metres), her body is moved to SORA's position.</summary>
        public const float ResyncDistance = 0.5f;
        /// <summary>Steps on the spot after walking or getting up (one cycle at a time, up to
        /// three): each foot comes back under her hips.</summary>
        public const float StepInPlaceSeconds = 1.1f;
        /// <summary>After getting up she settles over both planted feet this long before any
        /// step: when she first counts as up, her hips are still moving into place.</summary>
        public const float SettleBeforeSteppingSeconds = 0.6f;
        /// <summary>The balance helper's vertical share in SORA (see PhysicsBody).</summary>
        public const float BalanceVerticalShare = 1f;
        private const string Owner = "physics fall";
        private static int _scenes;

        private Scene _scene;
        private PhysicsScene _physics;
        private AvatarFit _fit = null!;
        private PhysicsBody _body = null!;
        private DesktopSurfaces _floor = null!;
        private BoxCollider _floorCollider = null!;
        private FallController _falls = null!;
        private Transform _instance = null!;
        private float _scale = 1f;
        private Transform[] _bones = Array.Empty<Transform>();
        private Quaternion[] _animationLocal = Array.Empty<Quaternion>();
        private Vector3 _animationHips;
        private bool _haveAnimation;
        private Quaternion[] _targets = Array.Empty<Quaternion>();
        private Quaternion[] _stepTargets = Array.Empty<Quaternion>();
        private Quaternion[] _gaitTargets = Array.Empty<Quaternion>();
        private Quaternion[] _fallTargets = Array.Empty<Quaternion>();
        private readonly CanonicalPose _standing = new();
        private readonly CanonicalPose _walk = new();
        private readonly StandInMotion _motion = new();
        private readonly CanonicalPose _streamPose = new();
        private Quaternion[] _streamTargets = Array.Empty<Quaternion>();
        private readonly Quaternion[] _realisedCanonical = new Quaternion[Canonical.Count];
        private float _streamWeight;
        private int[] _legJoints = Array.Empty<int>();
        private readonly int[] _hip = new int[2], _foot = new int[2], _thigh = new int[2];
        private AvatarPoseOwnership? _ownership;
        private AvatarLocomotion? _locomotion;
        private Func<bool> _held = () => false;
        private HelpDial _help;
        private float _accumulator, _time, _gaitPhase, _gaitSpeed, _walkBlend;
        private PhysicsBodyMode _mode = PhysicsBodyMode.Standing;
        private bool _synced;
        private int _stepsSinceSync;
        private float _stepInPlace, _settleBeforeStepping;
        private bool _wasMoving;
        private int _extraSteps;
        /// <summary>Her depth (simulation z): invisible on screen, so her body owns it.</summary>
        private float _depth;
        private Vector3? _grabPoint;              // world, from SORA's grab, until she is held
        private Vector3 _holdPoint, _holdRoot;    // simulation space, while held at a grab point
        private bool _heldByGrab;

        public bool IsConfigured => _body != null;
        /// <summary>True from a fall's start until she is standing again.</summary>
        public bool IsFalling => _mode == PhysicsBodyMode.Falling;
        public PhysicsBodyMode Mode => _mode;
        public FallPhase Phase => _falls?.Phase ?? FallPhase.Supported;
        public PhysicsBody Body => _body;
        public HelpLog HelpUsed => _body.Log;
        /// <summary>Screen pixels per metre of her body (for real gravity in SORA's drop).</summary>
        public float PixelsPerMetre => PixelsPerUnit * _scale;
        /// <summary>Mean angle between SORA's animation and her body, last frame (degrees).</summary>
        public float PoseError { get; private set; }
        /// <summary>How many times her body was moved to SORA's position instead of pulled.</summary>
        public int Resyncs { get; private set; }
        /// <summary>Why the last resync happened (for diagnosis).</summary>
        public string LastResync { get; private set; } = "";
        /// <summary>Her motion model's stream (2026-10-27): when a model moves her, its poses
        /// are what the motors aim for, in place of SORA's animation and the stand-in gait.</summary>
        public AvatarMotionStream MotionStream { get; } = new();
        /// <summary>How fast SORA moves her, in canonical metres a second (her leg length).</summary>
        public float CanonicalSpeed => _locomotion != null && _locomotion.IsMoving && IsConfigured
            ? _locomotion.CurrentSpeedPxPerSec / PixelsPerUnit / _scale / _fit.RootScale : 0f;

        /// <summary>Help settings by name: full, no-exempt, realistic (default) or none. An
        /// unknown name is reported and the default used, so a typo can't take her body away.</summary>
        public static HelpDial HelpFor(string? name)
        {
            switch ((name ?? "").Trim().ToLowerInvariant())
            {
                case "full": return HelpDial.Ladder[0].Dial;
                case "no-exempt": return HelpDial.Ladder[1].Dial;
                case "realistic": case "": return HelpDial.Ladder[2].Dial;
                case "none": return HelpDial.None;
                default:
                    Debug.LogWarning($"Physics body: SORA_PHYSICS_HELP '{name}' isn't full, no-exempt, realistic or none; using realistic");
                    return HelpDial.Ladder[2].Dial;
            }
        }

        /// <summary>Call right after the avatar loads, while it is still in its rest pose.</summary>
        /// <param name="held">True while SORA holds her: dragging, or her drop through the air.</param>
        public void Configure(Vrm10Instance instance, AvatarPoseOwnership? ownership, HelpDial help,
            AvatarLocomotion? locomotion = null, Func<bool>? held = null)
        {
            if (instance == null) throw new ArgumentNullException(nameof(instance));
            _instance = instance.transform;
            _ownership = ownership;
            _locomotion = locomotion;
            _held = held ?? (() => false);
            _help = help;
            var animator = instance.GetComponent<Animator>();
            _fit = new AvatarFit(animator);
            foreach (var issue in _fit.RestPoseIssues)
                Debug.LogWarning("Physics body: the avatar's rest pose isn't a T-pose: " + issue + "; her poses will be offset by that much");
            _scale = _instance.lossyScale.y;
            _scene = SceneManager.CreateScene("SORA physics body " + ++_scenes,
                new CreateSceneParameters(LocalPhysicsMode.Physics3D));
            var previous = SceneManager.GetActiveScene();
            SceneManager.SetActiveScene(_scene);
            try
            {
                _body = new PhysicsBody(_fit, origin: Vector3.zero);
                _floor = DesktopSurfaces.Create(new DesktopSurfaces.Surface("support",
                    new Vector3(0, -0.05f, 0), new Vector3(50, 0.1f, 50)));
                foreach (var c in _floor.Colliders) _floorCollider = c;
            }
            finally { SceneManager.SetActiveScene(previous); }
            _physics = _scene.GetPhysicsScene();
            _body.Help = help;
            _body.BalanceVerticalShare = BalanceVerticalShare;
            _falls = new FallController(_body, _floor) { NormalHelp = help };
            _motion.Stand(0, _standing);
            var n = _fit.Map.Joints.Count;
            _bones = new Transform[n];
            for (var i = 0; i < n; i++) _bones[i] = _fit.Bone(_fit.Map.Joints[i])!;
            _animationLocal = new Quaternion[n];
            _targets = new Quaternion[n];
            _stepTargets = new Quaternion[n];
            _gaitTargets = new Quaternion[n];
            _fallTargets = new Quaternion[n];
            _streamTargets = new Quaternion[n];
            _legJoints = new[] { "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes", "rightUpperLeg", "rightLowerLeg", "rightFoot", "rightToes" }
                .Select(name => _fit.IndexOf(Canonical.Index(name))).Where(i => i >= 0).ToArray();
            for (var side = 0; side < 2; side++)
            {
                var prefix = side == 0 ? "left" : "right";
                _thigh[side] = _hip[side] = _fit.IndexOf(Canonical.Index(prefix + "UpperLeg"));
                _foot[side] = _fit.IndexOf(Canonical.Index(prefix + "Foot"));
            }
            var rest = new Quaternion[n];
            for (var i = 0; i < n; i++) rest[i] = Quaternion.identity;
            _body.Teleport(_body.SimPoint(_fit.RestPosition(0)), _body.Frame, rest);
            Debug.Log($"Physics body: {n} links, {_body.Mass:0.0} kg, {_fit.Height:0.00} m, help {help}");
        }

        /// <summary>
        /// The wiring SoraBootstrap uses (and the tests use the same): when SORA holds her, where
        /// she was grabbed, and her landings. Grabbing and SORA's drop must also wait while she
        /// falls (<see cref="IsFalling"/>), which their own setup checks.
        /// </summary>
        public void Connect(AvatarGrabController? grab, AvatarSimplePhysicsController? drop)
        {
            _held = () => (grab != null && grab.IsGrabbed) ||
                          (drop != null && drop.State is SimplePhysicsState.Held or SimplePhysicsState.Falling);
            if (grab != null) grab.Grabbed += () => OnGrabbed(grab.GrabPointWorld);
            if (drop != null)
            {
                drop.Landed += impact => TryFallFromLanding(impact);
                // Drops fall at real gravity for her size, so they match her body's own falls.
                drop.GravityPxPerSecondSquared = 9.81f * PixelsPerMetre;
            }
        }

        // ---- Mapping between SORA's world and the simulation (a fixed frame, in her metres) ----

        private Vector3 ToSim(Vector3 world) => world / _scale;
        private Vector3 ToWorld(Vector3 sim) => sim * _scale;
        /// <summary>Her facing on screen as a turn about the vertical, from facing the viewer.</summary>
        private Quaternion Turn => Quaternion.Euler(0, _instance.rotation.eulerAngles.y, 0);

        /// <summary>Where SORA has her on screen, with her own depth.</summary>
        private Vector3 OnScreen()
        {
            var root = ToSim(_instance.position);
            return new Vector3(root.x, root.y, _depth);
        }

        /// <summary>
        /// A landing from SORA's drop physics (screen pixels per second, y down). A hard one
        /// becomes a physical fall; a soft one, she just lands.
        /// </summary>
        public bool TryFallFromLanding(Vector2 impactPixelsPerSecond)
        {
            if (!IsConfigured || IsFalling) return false;
            // She is on a surface again: it is solid, right under her, and nothing holds her.
            _body.RootOffset = OnScreen();
            PlaceFloorUnderRoot();
            if (_mode == PhysicsBodyMode.Held) LetGo();
            if (!float.IsFinite(impactPixelsPerSecond.x) || !float.IsFinite(impactPixelsPerSecond.y) ||
                impactPixelsPerSecond.y < FallImpactPxPerSecond) return false;
            if (_ownership != null && !_ownership.TryAcquire(Owner)) return false;
            _locomotion?.Stop();
            // Screen pixels → world units → her metres (screen y points down).
            var velocity = ToSim(new Vector3(impactPixelsPerSecond.x, -impactPixelsPerSecond.y, 0) / PixelsPerUnit);
            _body.Links[0].linearVelocity = velocity;
            _mode = PhysicsBodyMode.Falling;
            _falls.Suspended = false;
            _falls.ExpectFlight = false;
            _falls.Facing = Turn;
            _falls.Drop();
            Debug.Log($"Physics body: hard landing at {impactPixelsPerSecond} px/s, falling at {_time:0.00} s");
            return true;
        }

        /// <summary>Makes her stumble and fall where she stands (tests and diagnostics); her body
        /// then falls as if it had tipped over by itself.</summary>
        public void Trip()
        {
            if (_mode != PhysicsBodyMode.Standing) return;
            _falls.Trip();
            BeginOwnFall();
        }

        /// <summary>Run before SORA's pose writers: they continue from last frame's animation,
        /// not from the physics result.</summary>
        internal void RestoreAnimationPose()
        {
            if (!_haveAnimation) return;
            for (var i = 0; i < _bones.Length; i++) _bones[i].localRotation = _animationLocal[i];
            _bones[0].localPosition = _animationHips;
        }

        private void PlaceFloorUnderRoot()
        {
            var root = ToSim(_instance.position);
            _floorCollider.transform.position = new Vector3(root.x, root.y - 0.05f, root.z);
            _floorCollider.enabled = true;
            Physics.SyncTransforms();
        }

        private void LateUpdate()
        {
            if (!IsConfigured) return;
            // What SORA's animation wants this frame: the motor targets.
            for (var i = 0; i < _bones.Length; i++) _animationLocal[i] = _bones[i].localRotation;
            _animationHips = _bones[0].localPosition;
            _haveAnimation = true;
            _fit.ReadNormalized(_targets);

            UpdateMode();
            var turn = Turn;
            if (_mode != PhysicsBodyMode.Falling)
            {
                // SORA owns her position on screen (x and y); her body owns her depth.
                _body.RootOffset = OnScreen();
                if (_mode == PhysicsBodyMode.Standing && _floorCollider.enabled)
                {
                    // Walking along a surface keeps the floor under her; it never jumps through her.
                    var floor = _floorCollider.transform.position;
                    var root = _body.RootOffset;
                    if (Mathf.Abs(root.y - 0.05f - floor.y) > 0.02f) PlaceFloorUnderRoot();
                    else _floorCollider.transform.position = new Vector3(root.x, floor.y, root.z);
                }
                ApplyGait();
            }
            ApplyMotionStream();

            var hipsTarget = _body.RootOffset + turn * HipsRest();
            // The first frame (after SORA has placed and turned her), and whenever the two
            // disagree badly while she stands: move her body rather than pull it.
            if (_mode == PhysicsBodyMode.Standing && (!_synced || (_stepsSinceSync > 0 && TooFarApart(hipsTarget))))
                Resync(hipsTarget, turn, "SORA's position");

            _accumulator = Mathf.Min(_accumulator + Time.deltaTime, MaxStepsPerFrame * Step);
            while (_accumulator >= Step)
            {
                _accumulator -= Step;
                _time += Step;
                if (_mode == PhysicsBodyMode.Standing) _falls.Facing = turn;
                var pose = _falls.Step(Step, _time, _standing);
                if (_mode == PhysicsBodyMode.Standing && _falls.Phase != FallPhase.Supported) BeginOwnFall();
                if (_mode == PhysicsBodyMode.Falling && _falls.Phase == FallPhase.Supported) FinishFall();
                switch (_mode)
                {
                    case PhysicsBodyMode.Standing:
                        Array.Copy(_targets, _stepTargets, _targets.Length);
                        if (_walkBlend > 0 && _streamWeight < 0.5f) PlaceSwingFoot(turn, _stepTargets);
                        _body.SetTargets(_stepTargets);
                        _body.BalanceTargetPosition = Reachable(_body.RootOffset + turn * HipsRest(), turn);
                        _body.BalanceTargetRotation = turn * _targets[0];
                        break;
                    case PhysicsBodyMode.Held:
                        _body.SetTargets(_targets);
                        if (_heldByGrab) _body.BalanceTargetPosition = _holdPoint + (_body.RootOffset - _holdRoot);
                        else
                        {
                            _body.BalanceTargetPosition = _body.RootOffset + turn * HipsRest();
                            _body.BalanceTargetRotation = turn * _targets[0];
                        }
                        break;
                    default:
                        _body.SetTargets(_fit.Fold(pose, _fallTargets));
                        break;
                }
                _body.BeforeStep(Step);
                _physics.Simulate(Step);
                _stepsSinceSync++;
            }

            // Physics should never produce NaN; if it ever does, start her again where SORA has her.
            if (!IsFinite(_body.Links[0].transform.position))
            {
                Debug.LogWarning("Physics body: the simulation went non-finite; resetting her body");
                _mode = PhysicsBodyMode.Standing;
                _falls.Suspended = false;
                _body.HoldAtHips();
                _body.BalanceStrength = 1f;
                _body.Help = _help;
                _body.SetTone(_ => 1f);
                if (_ownership?.Owner == Owner) _ownership.Release(Owner);
                Resync(_body.RootOffset + turn * _fit.RestPosition(0), turn, "a non-finite simulation");
            }

            if (_mode == PhysicsBodyMode.Standing)
            {
                var realised = _body.ReadNormalized();
                var sum = 0f;
                for (var i = 1; i < realised.Length; i++) sum += Quaternion.Angle(realised[i], _targets[i]);
                PoseError = sum / (realised.Length - 1);
                RecordRealised(realised, turn);
            }
            // Drawn relative to where SORA has her root now, so her body stays where it is in the
            // world even if SORA moved her root meanwhile (during a fall).
            _body.WriteToAvatar(turn, OnScreen());
        }

        private static bool IsFinite(Vector3 v) => float.IsFinite(v.x) && float.IsFinite(v.y) && float.IsFinite(v.z);

        private void Resync(Vector3 hipsTarget, Quaternion turn, string why)
        {
            if (_synced)
            {
                Resyncs++;
                var off = _body.Links[0].transform.position - hipsTarget;
                LastResync = IsFinite(off)
                    ? $"{_time:0.00} s, {_mode}, {new Vector2(off.x, off.z).magnitude:0.00} m sideways, {off.y:0.00} m up ({why})"
                    : $"{_time:0.00} s, {_mode} ({why})";
                Debug.Log("Physics body: resynced to " + LastResync);
            }
            _body.Teleport(hipsTarget, turn * _targets[0], _targets);
            _synced = true;
            _stepsSinceSync = 0;
            _depth = hipsTarget.z - (turn * HipsRest()).z;
            if (_mode == PhysicsBodyMode.Standing) PlaceFloorUnderRoot();
        }

        /// <summary>
        /// The balance helper never asks for hips higher than her planted feet allow: with a foot
        /// out in front or behind (after a stride or getting up), straight legs can't reach the
        /// standing height, and a stiff height target would tip her pelvis instead.
        /// </summary>
        private Vector3 Reachable(Vector3 hipsTarget, Quaternion turn)
        {
            var floorTop = _floorCollider.transform.position.y + 0.05f;
            var highest = hipsTarget.y;
            var hipsRest = _fit.RestPosition(0);
            for (var side = 0; side < 2; side++)
            {
                var hipRest = _fit.RestPosition(_hip[side]);
                var ankleRest = _fit.RestPosition(_foot[side]);
                var foot = _body.Links[_foot[side]].transform.position;
                if (foot.y > floorTop + ankleRest.y + 0.03f) continue; // lifted: not holding her up
                var reach = hipRest.y - ankleRest.y;                       // hip joint to ankle, straight
                var hip = hipsTarget + turn * (hipRest - hipsRest);
                var apart = new Vector2(hip.x - foot.x, hip.z - foot.z).magnitude;
                var hipHeight = foot.y + Mathf.Sqrt(Mathf.Max(reach * reach - apart * apart, 0)) - 0.01f;
                highest = Mathf.Min(highest, hipHeight + (hipsRest.y - hipRest.y));
            }
            // A wide stance lowers her a little; never pull her down towards the floor.
            return new Vector3(hipsTarget.x, Mathf.Max(highest, hipsTarget.y - 0.25f), hipsTarget.z);
        }

        /// <summary>
        /// The foot in the air is placed under her body by gravity, not by her pelvis: if her pelvis
        /// has tipped, that thigh's target is turned back by the same amount. The planted foot is
        /// left alone. (People shuffle their feet together this way.)
        /// </summary>
        private void PlaceSwingFoot(Quaternion turn, Quaternion[] targets)
        {
            var tipped = Quaternion.Inverse(turn * _targets[0]) * _body.Links[0].transform.rotation;
            tipped.ToAngleAxis(out var angle, out var axis);
            if (angle > 180) angle -= 360;
            if (!float.IsFinite(axis.x) || Mathf.Abs(angle) < 0.5f) return;
            var duty = StandInMotion.DutyFactor(_gaitSpeed);
            for (var side = 0; side < 2; side++)
            {
                var swing = StandInMotion.SwingAmount(_gaitPhase + side * 0.5f, duty);
                if (swing < 0.05f) continue;
                var undo = Quaternion.AngleAxis(-Mathf.Clamp(angle, -35f, 35f) * Mathf.Min(1f, swing * 2f) * _walkBlend, axis);
                targets[_thigh[side]] = undo * targets[_thigh[side]];
            }
        }

        private Vector3 FeetCenter() =>
            (_body.Links[_foot[0]].transform.position + _body.Links[_foot[1]].transform.position) / 2
            - Turn * new Vector3(0, 0, _fit.RestPosition(_foot[0]).z - _fit.RestPosition(0).z);

        /// <summary>When she has finished stepping, SORA's position moves between her feet (if
        /// they are more than 5 cm off), so her hips settle over them.</summary>
        private void StandOverFeet()
        {
            if (_locomotion == null || _locomotion.IsMoving) return;
            var feet = FeetCenter();
            _depth = feet.z;
            var root = ToSim(_instance.position);
            if (Mathf.Abs(feet.x - root.x) < 0.05f) return;
            MoveSoraTo(ToWorld(new Vector3(feet.x, root.y, root.z)));
        }

        /// <summary>Moves SORA's screen position so that her model's root lands on a world point.</summary>
        private void MoveSoraTo(Vector3 instanceWorld)
        {
            if (_locomotion == null) return;
            var root = _locomotion.transform.position + (instanceWorld - _instance.position);
            _locomotion.TeleportToWorld(new Vector3(root.x, root.y, _locomotion.transform.position.z));
        }

        /// <summary>Whether both feet are under her hips (within 12 cm, sideways).</summary>
        private bool FeetUnderHer()
        {
            for (var side = 0; side < 2; side++)
            {
                var hip = _body.Links[_hip[side]].transform.position;
                var foot = _body.Links[_foot[side]].transform.position;
                if (new Vector2(hip.x - foot.x, hip.z - foot.z).magnitude > 0.12f) return false;
            }
            return true;
        }

        /// <summary>Her legs own her height, so only sideways distance (or a very large height
        /// difference, like a jump between surfaces) means SORA and her body disagree.</summary>
        private bool TooFarApart(Vector3 hipsTarget)
        {
            var off = _body.Links[0].transform.position - hipsTarget;
            return new Vector2(off.x, off.z).magnitude > ResyncDistance || Mathf.Abs(off.y) > 0.9f;
        }

        /// <summary>Her hips' rest position (her metres), lowered a little while she walks or runs.</summary>
        private Vector3 HipsRest()
        {
            var rest = _fit.RestPosition(0);
            var hips = rest;
            if (_walkBlend > 0)
            {
                var walking = _fit.HipsFor(new Vector3(0, _walk.Root.y, 0));
                hips = Vector3.Lerp(rest, new Vector3(rest.x, walking.y, rest.z), _walkBlend);
            }
            if (_streamWeight > 0)
            {
                var model = _fit.HipsFor(new Vector3(0, _streamPose.Root.y, 0));
                hips = Vector3.Lerp(hips, new Vector3(rest.x, model.y, rest.z), _streamWeight);
            }
            return hips;
        }

        // ---- Her motion model ---------------------------------------------------------------------

        /// <summary>While a model moves her (and she stands), its pose replaces SORA's animation
        /// and the stand-in gait as the motor targets, blended in and out. Physics, falls, being
        /// held and SORA's position on screen stay exactly as they are.</summary>
        private void ApplyMotionStream()
        {
            var playing = MotionStream.Advance(Time.deltaTime, _streamPose);
            _streamWeight = playing && _mode == PhysicsBodyMode.Standing ? MotionStream.Weight : 0f;
            if (_streamWeight <= 0) return;
            _fit.Fold(_streamPose, _streamTargets);
            for (var i = 0; i < _targets.Length; i++)
                _targets[i] = Quaternion.Slerp(_targets[i], _streamTargets[i], _streamWeight);
            // A running model has both feet off the floor for a moment: that isn't a fall.
            if (_streamWeight >= 0.5f)
                _falls.ExpectFlight = !(_streamPose.Contacts[0] || _streamPose.Contacts[1] ||
                                        _streamPose.Contacts[2] || _streamPose.Contacts[3]);
        }

        /// <summary>Records her realised pose for a handover seed, in canonical terms with her
        /// facing on screen taken off (the seed faces +Z).</summary>
        private void RecordRealised(Quaternion[] realised, Quaternion turn)
        {
            for (var j = 0; j < Canonical.Count; j++) _realisedCanonical[j] = Quaternion.identity;
            var compose = _fit.Map.Compose;
            for (var i = 0; i < compose.Count; i++) _realisedCanonical[compose[i][0]] = realised[i];
            _realisedCanonical[compose[0][0]] = Quaternion.Inverse(turn) * realised[0];
            var hips = Quaternion.Inverse(turn) * (_body.Links[0].transform.position - _body.RootOffset);
            var height = (hips.y - _fit.RestPosition(0).y) / _fit.RootScale + Canonical.HipsHeight;
            MotionStream.Record(Time.deltaTime, _realisedCanonical, height, CanonicalSpeed);
        }

        // ---- Holding ----------------------------------------------------------------------------

        private void OnGrabbed(Vector3 grabPointWorld)
        {
            _grabPoint = grabPointWorld;
            if (_mode == PhysicsBodyMode.Held) HoldAtGrab(); // re-grabbed while dropping
        }

        /// <summary>Holds her at the body part nearest where SORA's grab took hold (screen plane),
        /// free to swing from it.</summary>
        private void HoldAtGrab()
        {
            if (_grabPoint is not Vector3 grab) return;
            _grabPoint = null;
            var p = ToSim(grab);
            Collider? best = null;
            var bestPoint = Vector3.zero;
            var bestDistance = float.MaxValue;
            foreach (var c in _body.Colliders)
            {
                var q = c.ClosestPoint(new Vector3(p.x, p.y, c.bounds.center.z));
                // Nearest part on screen; where several contain the point, the one centred nearest.
                var center = c.bounds.center;
                var d = new Vector2(q.x - p.x, q.y - p.y).magnitude + 0.01f * new Vector2(center.x - p.x, center.y - p.y).magnitude;
                if (d < bestDistance) { bestDistance = d; best = c; bestPoint = q; }
            }
            if (best == null || best.attachedArticulationBody == null) return;
            _body.HoldAt(best.attachedArticulationBody, bestPoint, holdRotation: false);
            _holdPoint = bestPoint;
            _holdRoot = _body.RootOffset;
            _heldByGrab = true;
            Debug.Log($"Physics body: held by the {best.attachedArticulationBody.name.Replace("Link ", "")}");
        }

        private void LetGo()
        {
            _mode = PhysicsBodyMode.Standing;
            _falls.Suspended = false;
            _body.HoldAtHips();
            _body.BalanceStrength = 1f;
            _body.Help = _help;
            _body.SetTone(_ => 1f);
            _heldByGrab = false;
            _grabPoint = null;
            PlaceFloorUnderRoot();
            Debug.Log($"Physics body: let go at {_time:0.00} s");
        }

        private void UpdateMode()
        {
            if (_mode == PhysicsBodyMode.Falling) return;
            var held = _held();
            if (held && _mode != PhysicsBodyMode.Held)
            {
                _mode = PhysicsBodyMode.Held;
                _falls.Suspended = true;
                _floorCollider.enabled = false;           // nothing under her in mid-air
                _body.Help = new HelpDial(0, 0, 1);       // held, nothing else
                _body.BalanceStrength = HeldStrength;
                _body.SetTone(_ => HeldTone);
                _walkBlend = 0;
                _locomotion?.Stop();
                if (_grabPoint != null) HoldAtGrab();
                Debug.Log($"Physics body: held at {_time:0.00} s");
            }
            else if (!held && _mode == PhysicsBodyMode.Held) LetGo();
        }

        // ---- Walking and running ------------------------------------------------------------------

        /// <summary>While SORA moves her, her legs take the stand-in gait: feet lifted, knees bent,
        /// each foot planted front to back, stride and cadence matched to her speed, and a moment
        /// with both feet in the air when she runs.</summary>
        private void ApplyGait()
        {
            var moving = _mode == PhysicsBodyMode.Standing && _locomotion != null && _locomotion.IsMoving;
            if (_wasMoving && !moving) _stepInPlace = StepInPlaceSeconds;
            _wasMoving = moving;
            if (_settleBeforeStepping > 0 && !moving)
            {
                _settleBeforeStepping = Mathf.Max(0, _settleBeforeStepping - Time.deltaTime);
                if (_settleBeforeStepping == 0 && !FeetUnderHer()) StartSteppingAfterGettingUp();
            }
            // Keep stepping (up to three steps) until both feet are under her.
            var before = _stepInPlace;
            _stepInPlace = Mathf.Max(0, _stepInPlace - Time.deltaTime);
            if (before > 0 && _stepInPlace == 0 && !FeetUnderHer() && _extraSteps < 2) { _stepInPlace = StepInPlaceSeconds; _extraSteps++; }
            else if (before > 0 && _stepInPlace == 0) StandOverFeet();
            if (_stepInPlace == 0 && !moving) _extraSteps = 0;
            var stepping = moving || _stepInPlace > 0;
            _walkBlend = Mathf.MoveTowards(_walkBlend, stepping ? 1f : 0f, Time.deltaTime / 0.25f);
            if (_walkBlend <= 0) { _gaitPhase = 0; _falls.ExpectFlight = false; return; }
            var speedPx = moving ? _locomotion!.CurrentSpeedPxPerSec : 0f;
            // Pixels a second → world units → her metres → canonical metres (her leg length).
            _gaitSpeed = speedPx / PixelsPerUnit / _scale / _fit.RootScale;
            _gaitPhase += Time.deltaTime / StandInMotion.GaitPeriod(_gaitSpeed);
            _falls.ExpectFlight = StandInMotion.HasFlight(_gaitSpeed);
            _motion.Gait(_gaitPhase, _gaitSpeed, _walk);
            _fit.Fold(_walk, _gaitTargets);
            foreach (var i in _legJoints) _targets[i] = Quaternion.Slerp(_targets[i], _gaitTargets[i], _walkBlend);
        }

        // ---- Falling --------------------------------------------------------------------------------

        /// <summary>Her body started a fall by itself (a stumble or a tip): SORA stops moving her
        /// and her animation pauses until she is up again.</summary>
        private void BeginOwnFall()
        {
            _mode = PhysicsBodyMode.Falling;
            _ownership?.TryAcquire(Owner);
            _locomotion?.Stop();
            Debug.Log($"Physics body: fell by herself ({_falls.Trigger}) at {_time:0.00} s");
        }

        /// <summary>Steps on the spot to bring her feet under her after getting up. The stand-in
        /// get-up can finish with one foot still off the floor, so that foot steps first and the
        /// one she is standing on stays planted. (Phase 0.6 starts the left foot's swing with the
        /// right planted; 0.1 the other way round.)</summary>
        private void StartSteppingAfterGettingUp()
        {
            var leftHigher = _body.Links[_foot[0]].transform.position.y > _body.Links[_foot[1]].transform.position.y;
            _gaitPhase = leftHigher ? 0.6f : 0.1f;
            _stepInPlace = StepInPlaceSeconds;
        }

        /// <summary>She is up again: SORA's position becomes where her body actually is.</summary>
        private void FinishFall()
        {
            Debug.Log($"Physics body: standing again at {_time:0.00} s after: {string.Join("; ", _falls.Events.Skip(Math.Max(0, _falls.Events.Count - 6)))}");
            _mode = PhysicsBodyMode.Standing;
            _body.Help = _help;
            // Between her feet: the balance helper then brings her hips over them, as a person
            // stands up over their feet.
            var feet = FeetCenter();
            var floorTop = _floorCollider.transform.position.y + 0.05f;
            _stepInPlace = 0;
            _settleBeforeStepping = SettleBeforeSteppingSeconds;
            _depth = feet.z;
            MoveSoraTo(ToWorld(new Vector3(feet.x, floorTop, ToSim(_instance.position).z)));
            _body.RootOffset = OnScreen();
            if (_ownership?.Owner == Owner) _ownership.Release(Owner);
        }

        private void OnDestroy()
        {
            if (_ownership?.Owner == Owner) _ownership.Release(Owner);
            if (_scene.IsValid() && _scene.isLoaded) SceneManager.UnloadSceneAsync(_scene);
        }
    }

    /// <summary>Puts SORA's animation pose back before its pose writers run (see
    /// <see cref="AvatarPhysicsBody.RestoreAnimationPose"/>).</summary>
    [DefaultExecutionOrder(19980)]
    public sealed class AvatarPhysicsPoseRestore : MonoBehaviour
    {
        public AvatarPhysicsBody? Body;
        private void LateUpdate() => Body?.RestoreAnimationPose();
    }
}
