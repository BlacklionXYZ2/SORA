using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// Motion roadmap MA: the eye and focus rig. Eyes are driven by measured oculomotor rules
/// (saccades, fixations, pursuit, the vestibulo-ocular reflex, blinking), not a learned model.
/// </summary>
public sealed class P17EyeRigTests
{
    private const float Dt = 1f / 60f;

    private static Vector3 Yawed(float degrees) => Quaternion.AngleAxis(degrees, Vector3.up) * Vector3.forward;

    [Test]
    public void SaccadesFollowTheMainSequenceAndNeverExceedPeakSpeed()
    {
        Assert.AreEqual(0.043f, GazeModel.SaccadeDuration(10), 0.001f);
        Assert.AreEqual(0.075f, GazeModel.SaccadeDuration(20), 0.002f, "speed-limited above about 14°");
        Assert.Greater(GazeModel.SaccadeDuration(40), 0.021f + 0.0022f * 40, "large saccades are speed limited");
        Assert.AreEqual(0f, GazeModel.Profile(0), 1e-6f);
        Assert.AreEqual(0.5f, GazeModel.Profile(0.5f), 1e-6f);
        Assert.AreEqual(1f, GazeModel.Profile(1), 1e-6f);

        var model = new GazeModel(7);
        const float dt = 1f / 1000f;
        model.Tick(dt, Vector3.forward, GazeMode.Target, false);
        for (var i = 0; i < 1000; i++) model.Tick(dt, Vector3.forward, GazeMode.Target, false);
        var peak = 0f;
        var started = 0f;
        var previous = model.Direction;
        for (var i = 0; i < 300; i++)
        {
            model.Tick(dt, Yawed(30), GazeMode.Target, false);
            started = Mathf.Max(started, model.SaccadeStartedDegrees);
            peak = Mathf.Max(peak, Vector3.Angle(previous, model.Direction) / dt);
            previous = model.Direction;
        }
        Assert.Greater(started, 25f, "a 30° target jump starts one saccade, not a slow drift");
        Assert.LessOrEqual(peak, GazeModel.PeakSaccadeDegreesPerSecond * 1.02f);
        Assert.Greater(peak, 300f, "saccades are fast");
        Assert.Less(Vector3.Angle(model.Direction, Yawed(30)), 3.5f, "lands on the target, within fixation scatter");
    }

    [Test]
    public void ASlowlyMovingTargetIsPursuedWithoutBigCatchUpJumps()
    {
        var model = new GazeModel(3);
        var biggest = 0f;
        var worstError = 0f;
        for (var i = 0; i < 240; i++)
        {
            var target = Yawed(-20 + 10f * i * Dt); // 10°/s
            model.Tick(Dt, target, GazeMode.Target, false);
            if (i < 30) continue;
            biggest = Mathf.Max(biggest, model.SaccadeStartedDegrees);
            worstError = Mathf.Max(worstError, Vector3.Angle(model.Direction, target));
        }
        Assert.Less(worstError, 4.5f);
        Assert.Less(biggest, 6.5f, "only small fixational jumps; pursuit keeps up");
    }

    [Test]
    public void SheGlancesAwayFromTheViewerAndOftenWhenSheStartsSpeaking()
    {
        var glances = 0;
        var speechGlances = 0;
        for (var seed = 0; seed < 40; seed++)
        {
            var model = new GazeModel(seed);
            var was = false;
            // Ten seconds quietly, then she starts speaking.
            for (var i = 0; i < 600; i++)
            {
                model.Tick(Dt, Vector3.forward, GazeMode.Viewer, false);
                if (model.Glancing && !was) glances++;
                was = model.Glancing;
            }
            while (model.Glancing) model.Tick(Dt, Vector3.forward, GazeMode.Viewer, false);
            model.Tick(Dt, Vector3.forward, GazeMode.Viewer, true);
            if (model.Glancing) speechGlances++;
        }
        Assert.That(glances / 40f, Is.InRange(1f, 4f), "a glance every few seconds at rest");
        Assert.That(speechGlances, Is.InRange(16, 32), "about 60% look away as they start speaking");
    }

    [Test]
    public void BlinkRatesMatchMeasuredValues()
    {
        float PerMinute(GazeMode mode, bool speaking)
        {
            var blink = new BlinkModel(11);
            for (var i = 0; i < 60 * 600; i++) blink.Tick(Dt, mode, speaking, 0);
            return blink.Count / 10f;
        }
        var rest = PerMinute(GazeMode.Viewer, false);
        var speaking = PerMinute(GazeMode.Viewer, true);
        var attending = PerMinute(GazeMode.Target, false);
        Debug.Log($"P17 blinks a minute: rest {rest:0.0}, speaking {speaking:0.0}, attending {attending:0.0}");
        Assert.That(rest, Is.InRange(13f, 22f));
        Assert.Greater(speaking, rest);
        Assert.Less(attending, rest);
    }

    [Test]
    public void ABlinkClosesFastAndOpensSlowly()
    {
        Assert.AreEqual(0f, BlinkModel.Shape(0), 1e-6f);
        Assert.AreEqual(1f, BlinkModel.Shape(BlinkModel.CloseSeconds + 0.01f), 1e-6f);
        Assert.AreEqual(0f, BlinkModel.Shape(BlinkModel.CloseSeconds + BlinkModel.HoldSeconds + BlinkModel.OpenSeconds), 1e-6f);
        Assert.Less(BlinkModel.CloseSeconds, BlinkModel.OpenSeconds);
        var total = BlinkModel.CloseSeconds + BlinkModel.HoldSeconds + BlinkModel.OpenSeconds;
        Assert.That(total, Is.InRange(0.2f, 0.4f));
    }

    [Test]
    public void LargeGazeShiftsBringBlinks()
    {
        int Count(float saccade)
        {
            var blink = new BlinkModel(5);
            for (var i = 0; i < 60 * 300; i++) blink.Tick(Dt, GazeMode.Target, false, i % 90 == 0 ? saccade : 0);
            return blink.Count;
        }
        Assert.Greater(Count(45), Count(0) * 1.5f);
    }

    [Test]
    public void TheHeadStaysForSmallShiftsAndTurnsForLargeOnes()
    {
        var avatar = new GameObject("avatar");
        var head = new GameObject("head").transform;
        head.SetParent(avatar.transform, false);
        head.localPosition = new Vector3(0, 1.5f, 0);
        var look = avatar.AddComponent<AvatarLookAt>();
        look.ConfigureHead(head);
        look.LookAtWorldPoint(head.position + Yawed(8));
        for (var i = 0; i < 60; i++) look.ApplyGaze(Dt);
        Assert.Less(Quaternion.Angle(Quaternion.identity, head.localRotation), 0.5f, "8°: the eyes alone");
        look.LookAtWorldPoint(head.position + Yawed(40));
        look.ApplyGaze(Dt);
        Assert.IsTrue(look.HeadEngaged);
        for (var i = 0; i < 90; i++) look.ApplyGaze(Dt);
        Assert.Greater(Quaternion.Angle(Quaternion.identity, head.localRotation), 35f, "40°: the head turns too");
        Assert.IsFalse(look.HeadEngaged, "and settles");
        Object.Destroy(avatar);
    }

    private static IEnumerator Load(string path, System.Action<Vrm10Instance> done)
    {
        var task = Vrm10.LoadPathAsync(path, canLoadVrm0X: true,
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        done(task.Result);
    }

    private static int _savedFrameRate;

    // SORA's player runs at 60 fps; the test player is uncapped unless told otherwise.
    [SetUp] public void At60Fps() { _savedFrameRate = Application.targetFrameRate; Application.targetFrameRate = 60; QualitySettings.vSyncCount = 0; }
    [TearDown] public void RestoreFrameRate() => Application.targetFrameRate = _savedFrameRate;

    private static (AvatarEyeRig rig, AvatarLookAt look) Rig(Vrm10Instance instance)
    {
        // An AvatarLookAt with no head: it only supplies the target.
        var look = new GameObject("look").AddComponent<AvatarLookAt>();
        var rig = instance.gameObject.AddComponent<AvatarEyeRig>();
        rig.Configure(instance, look, null, null, seed: 4);
        return (rig, look);
    }

    [UnityTest]
    public IEnumerator SeedSanLooksWithHerLookExpressions()
    {
        Vrm10Instance instance = null!;
        yield return Load(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"), i => instance = i);
        var (rig, look) = Rig(instance);
        Assert.IsFalse(rig.UsesEyeBones, "Seed-san's VRM uses expressions for her eyes");
        var origin = instance.Runtime.LookAt.LookAtOriginTransform;
        var side = origin.position + Quaternion.AngleAxis(25, Vector3.up) * instance.transform.forward;
        look.LookAtWorldPoint(side);
        for (var i = 0; i < 40; i++) yield return null;
        var (expectedYaw, _) = instance.Runtime.LookAt.CalculateYawPitchFromLookAtPosition(side);
        Assert.AreEqual(Mathf.Sign(expectedYaw), Mathf.Sign(rig.EyeYaw));
        Assert.Greater(Mathf.Abs(rig.EyeYaw), 18f);
        Assert.AreEqual(Mathf.Sign(rig.EyeYaw), Mathf.Sign(instance.Runtime.LookAt.Yaw), "UniVRM received it");
        var weights = instance.Runtime.Expression.ActualWeights;
        weights.TryGetValue(ExpressionKey.LookLeft, out var left);
        weights.TryGetValue(ExpressionKey.LookRight, out var right);
        var sideways = Mathf.Max(left, right);
        Assert.Greater(sideways, 0.3f, "a look expression is applied");
        Object.Destroy(look.gameObject);
        Object.Destroy(instance.gameObject);
    }

    [UnityTest]
    public IEnumerator AlicesEyesStayOnTargetWhileHerHeadTurns()
    {
        var alice = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.local/avatars/Alice.vrm"));
        if (!File.Exists(alice)) Assert.Ignore("Alice.vrm isn't in .local/avatars (kept out of git)");
        Vrm10Instance instance = null!;
        yield return Load(alice, i => instance = i);
        var (rig, look) = Rig(instance);
        Assert.IsTrue(rig.UsesEyeBones, "Alice's VRM turns eye bones");
        var animator = instance.GetComponent<Animator>();
        var head = animator.GetBoneTransform(HumanBodyBones.Head);
        var leftEye = animator.GetBoneTransform(HumanBodyBones.LeftEye);
        var headRest = head.rotation;
        var eyeRestInHead = Quaternion.Inverse(head.rotation) * leftEye.rotation;
        var origin = instance.Runtime.LookAt.LookAtOriginTransform;
        var ahead = origin.position + instance.transform.forward;
        look.LookAtWorldPoint(ahead);
        for (var i = 0; i < 30; i++) yield return null;

        // Swing her head ±15° (as the test, not the rig, would see a walk or a turn).
        var eyeYaw = new List<float>();
        var headYaw = new List<float>();
        var eyeTurn = 0f;
        for (var i = 0; i < 180; i++)
        {
            var swing = 15f * Mathf.Sin(i * Dt * Mathf.PI); // one full swing in 2 s
            head.rotation = Quaternion.AngleAxis(swing, instance.transform.up) * headRest;
            yield return null;
            eyeYaw.Add(rig.EyeYaw);
            headYaw.Add(swing);
            var eyeInHead = Quaternion.Inverse(head.rotation) * leftEye.rotation;
            eyeTurn = Mathf.Max(eyeTurn, Quaternion.Angle(eyeRestInHead, eyeInHead));
        }
        float Spread(IEnumerable<float> values) => values.Max() - values.Min();
        var compensated = Mathf.Min(Spread(eyeYaw.Zip(headYaw, (e, h) => e + h)),
                                    Spread(eyeYaw.Zip(headYaw, (e, h) => e - h)));
        Debug.Log($"P17 VOR: eye yaw spread {Spread(eyeYaw):0.0}°, gaze spread {compensated:0.0}°, eye bone turn up to {eyeTurn:0.0}°");
        Assert.Greater(Spread(eyeYaw), 20f, "the eyes counter-rotate as the head swings 30°");
        Assert.Less(compensated, 7f, "so the gaze stays on the target");
        Assert.Greater(eyeTurn, 1f, "her eye bones move");
        Assert.Less(eyeTurn, 12f, "within her VRM's 10° eye range");
        Object.Destroy(look.gameObject);
        Object.Destroy(instance.gameObject);
    }

    [UnityTest]
    public IEnumerator SheBlinksOnAnAvatar()
    {
        Vrm10Instance instance = null!;
        yield return Load(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"), i => instance = i);
        var (rig, look) = Rig(instance);
        var closed = 0f;
        var start = Time.time;
        while (Time.time - start < 30f && rig.Blink.Count == 0) yield return null;
        // Sample by time, not frames: the test player may run uncapped.
        start = Time.time;
        while (Time.time - start < 0.4f)
        {
            instance.Runtime.Expression.ActualWeights.TryGetValue(ExpressionKey.Blink, out var weight);
            closed = Mathf.Max(closed, weight);
            yield return null;
        }
        Assert.Greater(rig.Blink.Count, 0, "a blink within 30 s");
        Assert.Greater(closed, 0.8f, "her blink expression closes her eyes");
        Object.Destroy(look.gameObject);
        Object.Destroy(instance.gameObject);
    }
}
