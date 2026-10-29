using System.Collections;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using MotionEnv.AvatarLayer;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// Motion roadmap MA in SORA's player: her body is a physics body. These tests wire her exactly
/// as SoraBootstrap does (locomotion, grab, SORA's drop physics, <c>AvatarPhysicsBody.Connect</c>)
/// and drive grabbing and dropping the way SORA's window does, so the integration itself is
/// covered (audit 2026-10-18: the owner's bugs came from the wiring).
/// </summary>
public sealed class P18PhysicsBodyTests
{
    private sealed class Rig
    {
        public GameObject Avatar = null!;
        public Vrm10Instance Instance = null!;
        public AvatarPhysicsBody Body = null!;
        public AvatarPoseOwnership Ownership = null!;
        public AvatarLocomotion Motion = null!;
        public AvatarGrabController Grab = null!;
        public AvatarSimplePhysicsController Drop = null!;

        public Vector3 Root => Avatar.transform.position;
        public Transform Bone(HumanBodyBones bone) => Instance.GetComponent<Animator>().GetBoneTransform(bone);
    }

    [Test]
    public void TheAvatarLayerMatchesMotionLab()
    {
        var lab = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../../motion-lab/unity-env/Assets/AvatarLayer"));
        if (!Directory.Exists(lab)) Assert.Ignore("motion-lab isn't next to SORA");
        var mine = Path.Combine(Application.dataPath, "Scripts/AvatarLayer");
        using var sha = SHA256.Create();
        foreach (var file in Directory.GetFiles(lab, "*.cs"))
        {
            var copy = Path.Combine(mine, Path.GetFileName(file));
            Assert.IsTrue(File.Exists(copy), Path.GetFileName(file) + " is missing; run motion-lab's unity-env/tools/sync-to-sora.ps1");
            CollectionAssert.AreEqual(sha.ComputeHash(File.ReadAllBytes(file)), sha.ComputeHash(File.ReadAllBytes(copy)),
                Path.GetFileName(file) + " has drifted from motion-lab's; run motion-lab's unity-env/tools/sync-to-sora.ps1");
        }
    }

    [Test]
    public void AnUnknownHelpSettingFallsBackInsteadOfFailing()
    {
        LogAssert.Expect(LogType.Warning, new System.Text.RegularExpressions.Regex("SORA_PHYSICS_HELP 'realistc'"));
        var dial = AvatarPhysicsBody.HelpFor("realistc");
        Assert.AreEqual(HelpDial.Ladder[2].Dial.Balance, dial.Balance);
        Assert.AreEqual(HelpDial.Ladder[0].Dial.Exempt, AvatarPhysicsBody.HelpFor(" FULL ").Exempt);
    }

    private static IEnumerator Load(System.Action<Vrm10Instance> done)
    {
        var task = Vrm10.LoadPathAsync(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"), canLoadVrm0X: true,
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        done(task.Result);
    }

    /// <summary>Wired as SoraBootstrap wires her.</summary>
    private static IEnumerator Build(System.Action<Rig> done)
    {
        var rig = new Rig();
        yield return Load(i => rig.Instance = i);
        rig.Avatar = new GameObject("SORA Avatar");
        rig.Motion = rig.Avatar.AddComponent<AvatarLocomotion>();
        rig.Instance.transform.SetParent(rig.Avatar.transform, false);
        var bounds = rig.Instance.GetComponentsInChildren<Renderer>().Select(r => r.bounds).Aggregate((a, b) => { a.Encapsulate(b); return a; });
        rig.Instance.transform.localScale = Vector3.one * (1f / bounds.size.y);
        rig.Instance.transform.localPosition = new Vector3(0, -bounds.min.y / bounds.size.y, 0);
        rig.Ownership = new AvatarPoseOwnership();
        rig.Motion.TeleportTo(900, 1000);
        AvatarPhysicsBody? body = null;
        rig.Grab = rig.Avatar.AddComponent<AvatarGrabController>();
        rig.Grab.Configure(rig.Motion, () => body?.IsFalling != true);
        rig.Drop = rig.Avatar.AddComponent<AvatarSimplePhysicsController>();
        rig.Drop.Configure(rig.Motion, () => !rig.Motion.IsMoving && body?.IsFalling != true);
        body = rig.Body = rig.Avatar.AddComponent<AvatarPhysicsBody>();
        rig.Body.Configure(rig.Instance, rig.Ownership, AvatarPhysicsBody.HelpFor(null), rig.Motion);
        rig.Body.Connect(rig.Grab, rig.Drop);
        rig.Avatar.AddComponent<AvatarPhysicsPoseRestore>().Body = rig.Body;
        var idle = rig.Avatar.AddComponent<AvatarIdlePose>();
        idle.Configure(rig.Instance.GetComponent<Animator>(), rig.Motion, rig.Ownership);
        rig.Avatar.transform.rotation = Quaternion.Euler(0, 180, 0);
        done(rig);
    }

    private static IEnumerator Wait(float seconds)
    {
        var end = Time.time + seconds;
        while (Time.time < end) yield return null;
    }

    /// <summary>What SORA's window does each frame when nothing is grabbed.</summary>
    private static IEnumerator TickDrop(Rig rig, float seconds)
    {
        var end = Time.time + seconds;
        while (Time.time < end) { rig.Drop.Tick(Time.unscaledDeltaTime); yield return null; }
    }

    private static IEnumerator WaitUntilUp(Rig rig, float limit)
    {
        var start = Time.time;
        while (Time.time - start < limit && (rig.Body.IsFalling || Time.time - start < 1f)) yield return null;
    }

    [UnityTest]
    public IEnumerator HerBodyFollowsHerAnimationAndStaysSteady()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(3f);
        var hips = rig.Bone(HumanBodyBones.Hips).position;
        Debug.Log($"P18 standing: pose error {rig.Body.PoseError:0.0}°, mass {rig.Body.Body.Mass:0.0} kg, resyncs {rig.Body.Resyncs}");
        Assert.IsFalse(rig.Body.IsFalling);
        Assert.Less(rig.Body.PoseError, 5f, "her body keeps to the animation");
        var restHips = rig.Body.Body.Fit.RestPosition(0).y;
        var simHips = rig.Body.Body.Links[0].transform.position.y - rig.Body.Body.RootOffset.y;
        Assert.AreEqual(restHips, simHips, 0.03f, "standing: her hips within 3 cm of their rest height");
        var scale = rig.Instance.transform.lossyScale.y;
        Assert.AreEqual(rig.Instance.transform.position.y + simHips * scale, hips.y, 0.002f, "the display shows the simulation");
        Assert.AreEqual(9.81f * rig.Body.PixelsPerMetre, rig.Drop.GravityPxPerSecondSquared, 0.5f, "SORA's drops fall at real gravity for her size");
        Assert.AreEqual(0, rig.Body.Resyncs);
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Owner, 2026-10-17: after getting up she bent to the side and fell again, over and
    /// over. Now she gets up facing the way she faced, SORA's position moves to where her body is,
    /// and she stays up.</summary>
    [UnityTest]
    public IEnumerator AHardLandingIsAPhysicalFallAndSheGetsUpAndStaysUp()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        Assert.IsFalse(rig.Body.TryFallFromLanding(new Vector2(0, 400)), "a soft landing isn't a fall");
        Assert.IsTrue(rig.Body.TryFallFromLanding(new Vector2(300, 1600)));
        Assert.AreEqual("physics fall", rig.Ownership.Owner, "her animation pauses while she falls");
        var lowestHead = float.MaxValue;
        var head = rig.Bone(HumanBodyBones.Head);
        var start = Time.time;
        while (Time.time - start < 25f && (rig.Body.IsFalling || Time.time - start < 1f))
        {
            lowestHead = Mathf.Min(lowestHead, head.position.y - rig.Root.y);
            yield return null;
        }
        var upAfter = Time.time - start;
        yield return Wait(5f);
        var hips = rig.Body.Body.Links[0].transform;
        var tilt = Vector3.Angle(hips.up, Vector3.up);
        var drift = new Vector2(hips.position.x - rig.Body.Body.RootOffset.x, hips.position.z - rig.Body.Body.RootOffset.z).magnitude;
        Debug.Log($"P18 fall: lowest head {lowestHead:0.00} units, up after {upAfter:0.0} s; 5 s later: falling {rig.Body.IsFalling}, " +
                  $"hips tilt {tilt:0}°, hips {drift:0.00} m from SORA's position, resyncs {rig.Body.Resyncs} ({rig.Body.LastResync})");
        Assert.Less(lowestHead, 0.4f, "she went down");
        Assert.IsFalse(rig.Body.IsFalling, "she got up and stayed up");
        Assert.IsNull(rig.Ownership.Owner, "her animation has the body back");
        Assert.Less(tilt, 10f, "standing straight, not bent to the side");
        Assert.Less(drift, 0.15f, "SORA's position followed her body");
        Assert.AreEqual(0, rig.Body.Resyncs);
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Owner, 2026-10-17: walking dragged her feet, and she fell when she stopped.</summary>
    [UnityTest]
    public IEnumerator SheWalksAndStopsWithoutFalling()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        var startX = rig.Root.x;
        rig.Motion.MoveTo(1400, 1000, 300);
        var foot = rig.Body.Body.Link(Canonical.Index("leftFoot")).transform;
        var lowestFoot = float.MaxValue; var highestFoot = float.MinValue;
        while (rig.Motion.IsMoving)
        {
            lowestFoot = Mathf.Min(lowestFoot, foot.position.y);
            highestFoot = Mathf.Max(highestFoot, foot.position.y);
            yield return null;
        }
        yield return Wait(5f);
        var tilt = Vector3.Angle(rig.Body.Body.Links[0].transform.up, Vector3.up);
        Debug.Log($"P18 walk: travelled {rig.Root.x - startX:0.00} units; left foot lifted up to {(highestFoot - lowestFoot) * 100:0} cm; " +
                  $"5 s after stopping: falling {rig.Body.IsFalling}, tilt {tilt:0}°, resyncs {rig.Body.Resyncs} ({rig.Body.LastResync})");
        Assert.Greater(highestFoot - lowestFoot, 0.04f, "her feet lift as she walks instead of dragging");
        Assert.IsFalse(rig.Body.IsFalling, "she didn't fall while walking or when she stopped");
        Assert.Less(tilt, 10f);
        Assert.AreEqual(0, rig.Body.Resyncs, "her body kept up with SORA without being moved");
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Audit 2026-10-18: SORA runs her at 800 px/s (V1 acceptance step 5) and makes
    /// gestures at 1200 px/s. She runs with a moment in the air, without falling, and her planted
    /// feet don't skate.</summary>
    [UnityTest]
    public IEnumerator SheRunsWithoutFallingOrSkating([Values(800f, 1200f)] float speed)
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        var startX = rig.Root.x;
        rig.Motion.MoveTo(200, 1000, speed);
        var feet = new[] { rig.Body.Body.Link(Canonical.Index("leftFoot")).transform, rig.Body.Body.Link(Canonical.Index("rightFoot")).transform };
        var floor = rig.Body.Body.Links[0].transform.position.y - rig.Body.Body.Fit.RestPosition(0).y;
        var ankle = rig.Body.Body.Fit.RestPosition(rig.Body.Body.Fit.IndexOf(Canonical.Index("leftFoot"))).y;
        var plantedAt = new Vector3?[2];
        var skate = 0f; var airborne = 0;
        while (rig.Motion.IsMoving)
        {
            var down = 0;
            for (var f = 0; f < 2; f++)
            {
                var p = feet[f].position;
                var planted = p.y < floor + ankle + 0.015f;
                if (planted) down++;
                if (!planted) { plantedAt[f] = null; continue; }
                if (plantedAt[f] is not Vector3 at) { plantedAt[f] = p; continue; }
                skate = Mathf.Max(skate, new Vector2(p.x - at.x, p.z - at.z).magnitude);
            }
            if (down == 0) airborne++;
            yield return null;
        }
        yield return Wait(5f);
        Debug.Log($"P18 run at {speed} px/s: travelled {startX - rig.Root.x:0.00} units, frames with both feet up {airborne}, " +
                  $"worst planted-foot skate {skate * 100:0.0} cm, falling {rig.Body.IsFalling}, resyncs {rig.Body.Resyncs} ({rig.Body.LastResync})");
        Assert.IsFalse(rig.Body.IsFalling, "she didn't fall");
        Assert.Greater(airborne, 0, "a run has moments with both feet in the air");
        Assert.Less(skate, 0.15f, "a planted foot doesn't skate");
        Assert.AreEqual(0, rig.Body.Resyncs);
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Audit 2026-10-18: if she falls by herself mid-walk, SORA stops moving her and her
    /// body stays where it fell (it used to slide along with SORA's walk).</summary>
    [UnityTest]
    public IEnumerator FallingMidWalkStopsTheWalkAndSheDoesNotSlide()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        rig.Motion.MoveTo(1700, 1000, 300);
        yield return Wait(0.8f);
        rig.Body.Trip();
        yield return null; yield return null;
        Assert.IsTrue(rig.Body.IsFalling);
        Assert.IsFalse(rig.Motion.IsMoving, "SORA stopped walking her");
        Assert.AreEqual("physics fall", rig.Ownership.Owner);
        var rootAtFall = rig.Root;
        var hips = rig.Bone(HumanBodyBones.Hips);
        var hipsAtFall = hips.position;
        var maxRootMove = 0f;
        var start = Time.time;
        while (Time.time - start < 25f && rig.Body.IsFalling)
        {
            maxRootMove = Mathf.Max(maxRootMove, Vector3.Distance(rig.Root, rootAtFall));
            yield return null;
        }
        Debug.Log($"P18 fall mid-walk: SORA's root moved {maxRootMove:0.000} units during the fall; " +
                  $"hips moved {Vector3.Distance(hips.position, hipsAtFall):0.00} units; up again {!rig.Body.IsFalling}");
        Assert.Less(maxRootMove, 0.01f, "SORA's root stayed put while she fell");
        Assert.IsFalse(rig.Body.IsFalling, "she got up");
        Assert.IsNull(rig.Ownership.Owner);
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Owner, 2026-10-17: picked up she ragdolled (good), but dropped she froze mid-air,
    /// got up floating, then fell through the floor and flew around. Driven through SORA's own
    /// grab and drop, as its window does: picked up by the head she hangs from it; dropped, she
    /// falls with SORA's drop and lands on the floor, falls over, and gets up.</summary>
    [UnityTest]
    public IEnumerator PickedUpByTheHeadAndDroppedThroughSorasOwnGrab()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        var start = rig.Motion.GetCurrentGlobalPixelPosition();
        // The cursor over her face: the head joint is at the base of her skull, so a little above it.
        var head = rig.Bone(HumanBodyBones.Head).position + Vector3.up * 0.06f * rig.Body.Body.Height * rig.Instance.transform.lossyScale.y;
        var headPixel = new Vector2Int(start.GlobalX, start.GlobalY - Mathf.RoundToInt((head.y - rig.Root.y) * AvatarPhysicsBody.PixelsPerUnit));
        Assert.IsTrue(rig.Grab.BeginGrab(headPixel.x, headPixel.y, head), "grabbed");
        rig.Drop.SuspendForGrab();
        // Drag up 450 px over half a second, then hold still.
        for (var t = 0f; t < 1.5f; t += Time.unscaledDeltaTime)
        {
            rig.Grab.DragTo(headPixel.x, headPixel.y - Mathf.RoundToInt(450 * Mathf.Clamp01(t / 0.5f)), Time.unscaledDeltaTime);
            yield return null;
        }
        Debug.Log($"P18 held: mode {rig.Body.Mode}, held by {rig.Body.Body.HeldLink.name}, " +
                  $"hips {rig.Body.Body.HeldPoint.y - rig.Body.Body.Links[0].transform.position.y:0.00} m below the grip");
        Assert.AreEqual(PhysicsBodyMode.Held, rig.Body.Mode);
        StringAssert.Contains("head", rig.Body.Body.HeldLink.name, "held where she was grabbed");
        Assert.Greater(rig.Body.Body.HeldPoint.y - rig.Body.Body.Links[0].transform.position.y, 0.3f, "she hangs below the grip");
        Assert.IsFalse(rig.Body.IsFalling, "being held isn't a fall");
        // Let go: SORA's drop carries her down, then she lands.
        rig.Grab.EndGrab();
        Assert.IsTrue(rig.Drop.Release(rig.Grab.TakeReleaseVelocity()), "SORA's drop takes over");
        var lowestHips = float.MaxValue; var maxAway = 0f;
        Vector3? landedAt = null;
        var started = Time.time;
        while (Time.time - started < 25f && (rig.Body.IsFalling || rig.Drop.IsActive || Time.time - started < 1.5f))
        {
            rig.Drop.Tick(Time.unscaledDeltaTime);
            if (landedAt == null && rig.Body.IsFalling) landedAt = rig.Body.Body.RootOffset;
            if (landedAt is Vector3 at)
            {
                var h = rig.Body.Body.Links[0].transform.position;
                lowestHips = Mathf.Min(lowestHips, h.y - at.y);
                maxAway = Mathf.Max(maxAway, new Vector2(h.x - at.x, h.z - at.z).magnitude);
            }
            yield return null;
        }
        yield return TickDrop(rig, 3f);
        Debug.Log($"P18 drop: fell {landedAt != null}; hips went down to {lowestHips:0.00} m above the floor, at most {maxAway:0.00} m from where she landed; " +
                  $"falling {rig.Body.IsFalling}, mode {rig.Body.Mode}, resyncs {rig.Body.Resyncs} ({rig.Body.LastResync})");
        Assert.IsNotNull(landedAt, "a 450 px drop is a hard landing: she falls");
        Assert.Greater(lowestHips, 0.02f, "she lay on the floor, not through it");
        Assert.Less(lowestHips, 0.4f, "she went down");
        Assert.Less(maxAway, 1.2f, "she didn't fly off");
        Assert.IsFalse(rig.Body.IsFalling);
        Assert.AreEqual(PhysicsBodyMode.Standing, rig.Body.Mode);
        Assert.AreSame(rig.Body.Body.Links[0], rig.Body.Body.HeldLink, "held at the hips again once she stands");
        Assert.AreEqual(0, rig.Body.Resyncs);
        Object.Destroy(rig.Avatar);
        yield return null;
    }

    /// <summary>Owner, 2026-10-17: she got stuck and could not move (by command or by hand): a fall
    /// that never finished kept her pose. Every fall now ends and gives her back.</summary>
    [UnityTest]
    public IEnumerator EveryFallEndsAndGivesHerBack()
    {
        Rig rig = null!;
        yield return Build(r => rig = r);
        yield return Wait(1f);
        Assert.IsTrue(rig.Body.TryFallFromLanding(new Vector2(0, 1050)));
        var start = Time.time;
        yield return WaitUntilUp(rig, 26f);
        Debug.Log($"P18 landing on her feet: falling {rig.Body.IsFalling} after {Time.time - start:0.0} s, owner {rig.Ownership.Owner ?? "none"}");
        Assert.IsFalse(rig.Body.IsFalling, "the fall ended");
        Assert.IsNull(rig.Ownership.Owner, "SORA has her pose back");
        yield return Wait(2f);
        rig.Body.Trip();
        start = Time.time;
        yield return WaitUntilUp(rig, 26f);
        Debug.Log($"P18 trip: falling {rig.Body.IsFalling} after {Time.time - start:0.0} s, owner {rig.Ownership.Owner ?? "none"}");
        Assert.IsFalse(rig.Body.IsFalling, "the fall ended");
        Assert.IsNull(rig.Ownership.Owner, "SORA has her pose back");
        Assert.IsTrue(rig.Grab.BeginGrab(900, 800, rig.Bone(HumanBodyBones.Hips).position), "she can be picked up again");
        Object.Destroy(rig.Avatar);
        yield return null;
    }
}
