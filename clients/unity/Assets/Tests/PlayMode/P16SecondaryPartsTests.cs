using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>Motion roadmap MA, A1: hair, clothing and accessories classified and given their own physics.</summary>
public sealed class P16SecondaryPartsTests
{
    private const float SoraHeight = Sora.Embodiment.Coordinates.OverlayPlacement.AvatarHeightPixels / 500f;

    private static SecondaryClassification C(string name, HumanBodyBones? anchor) =>
        AvatarSecondaryParts.Classify(new[] { name }, anchor);

    [Test]
    public void NamesFromVRoidMmdAndConvertedModelsAreClassified()
    {
        // VRoid
        Assert.AreEqual(SecondaryPart.Hair, C("J_Sec_Hair1_03", HumanBodyBones.Head).Part);
        Assert.AreEqual("skirt", C("J_Sec_L_SkirtBack0_01", HumanBodyBones.Hips).Kind);
        Assert.AreEqual("soft", C("J_Sec_L_Bust1", HumanBodyBones.UpperChest).Kind);
        Assert.AreEqual("skirt", C("J_Sec_R_CoatSkirtSide2", HumanBodyBones.Hips).Kind);
        // MMD and Japanese
        Assert.AreEqual(SecondaryPart.Hair, C("前髪1", HumanBodyBones.Head).Part);
        Assert.AreEqual("skirt", C("スカート前", HumanBodyBones.Hips).Kind);
        // A "tail" on the head is a ponytail; on the spine it is a tail (Alice's is).
        var ponytail = C("joint_Skn_Tail_01", HumanBodyBones.Head);
        Assert.AreEqual(SecondaryPart.Hair, ponytail.Part);
        Assert.AreEqual("ponytail", ponytail.Kind);
        Assert.AreEqual("tail", C("41.joint_Skn_Tail_01", HumanBodyBones.Spine).Kind);
        // Carried things aren't clothing, even when they hang from the hips (Alice's weapons).
        Assert.AreEqual("prop", C("65.joint_Ctr_WeaponBox_03", HumanBodyBones.Spine).Kind);
        Assert.AreEqual("prop", C("63.joint_Ctr_R_BackupWpn_01", HumanBodyBones.Spine).Kind);
        Assert.AreEqual("ear", C("103.joint_migimimi_1", HumanBodyBones.Head).Kind);
        Assert.AreEqual("tie", C("100.joint_Ctr_Tie_01", HumanBodyBones.UpperChest).Kind);
        Assert.AreEqual("ornament", C("48.joint_Skn_Ornaments_05", HumanBodyBones.Hips).Kind);
        // No helpful name: where it hangs from decides.
        Assert.AreEqual(SecondaryPart.Hair, C("bone_17", HumanBodyBones.Head).Part);
        Assert.AreEqual(SecondaryPart.Clothing, C("bone_18", HumanBodyBones.LeftUpperLeg).Part);
        Assert.AreEqual(SecondaryPart.Accessory, C("bone_19", null).Part);
        // Words are matched as words where they are short: "hearing" is not an ear.
        Assert.AreNotEqual("ear", C("hearing_aid", HumanBodyBones.Chest).Kind);
    }

    [Test]
    public void OverrideFileIsReadAndBadLinesIgnored()
    {
        var path = Path.Combine(Application.temporaryCachePath, "p16.parts.txt");
        File.WriteAllText(path, "# Alice\n41.joint_Skn_Tail_01 = accessory\nnot a line\nx = nonsense\n 100.joint_Ctr_Tie_01=Hair # comment\n");
        var overrides = AvatarSecondaryParts.ReadOverrides(path);
        Assert.AreEqual(2, overrides.Count);
        Assert.AreEqual(SecondaryPart.Accessory, overrides["41.joint_Skn_Tail_01"]);
        Assert.AreEqual(SecondaryPart.Hair, overrides["100.joint_Ctr_Tie_01"]);
        Assert.AreEqual(0, AvatarSecondaryParts.ReadOverrides(Path.Combine(Application.temporaryCachePath, "missing.txt")).Count);
    }

    [Test]
    public void EachKindGetsItsOwnPhysics()
    {
        var weightless = new StableSpringBoneSettings(1f, 0f, Vector3.up, 0.4f, 0.02f);
        var hair = AvatarSecondaryParts.Shape(new SecondaryClassification(SecondaryPart.Hair, "ponytail", ""), weightless);
        var skirt = AvatarSecondaryParts.Shape(new SecondaryClassification(SecondaryPart.Clothing, "skirt", ""), weightless);
        var ear = AvatarSecondaryParts.Shape(new SecondaryClassification(SecondaryPart.Accessory, "ear", ""), weightless);
        Assert.Greater(hair.GravityPower, 0.1f);
        Assert.AreEqual(Vector3.down, hair.GravityDirection);
        Assert.Greater(skirt.GravityPower, hair.GravityPower);
        Assert.Greater(skirt.Drag, hair.Drag);
        Assert.GreaterOrEqual(ear.Stiffness, 3f);
        Assert.Less(ear.GravityPower, 0.05f);
        // Authored values above the floors are kept.
        var heavy = AvatarSecondaryParts.Shape(new SecondaryClassification(SecondaryPart.Hair, "hair", ""),
            new StableSpringBoneSettings(2f, 0.8f, Vector3.down, 0.7f, 0.02f));
        Assert.AreEqual(0.8f, heavy.GravityPower);
        Assert.AreEqual(0.7f, heavy.Drag);
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

    [UnityTest]
    public IEnumerator BundledSeedSanEveryChainIsClassified()
    {
        Vrm10Instance instance = null!;
        yield return Load(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"), i => instance = i);
        var tuner = instance.gameObject.AddComponent<AvatarSecondaryMotionTuner>();
        var count = tuner.Configure(instance);
        Assert.Greater(count, 0);
        Assert.AreEqual(count, tuner.Parts.Count, "every spring joint is classified");
        for (var frame = 0; frame < 60; frame++) yield return null;
        foreach (var joint in instance.GetComponentsInChildren<VRM10SpringBoneJoint>())
            Assert.IsFalse(float.IsNaN(joint.transform.position.y));
        Object.Destroy(instance.gameObject);
    }

    /// <summary>
    /// Owner report (2026-10-15): her hair tips flap violently all the time. Measured the way
    /// SORA runs her: scaled to her height in SORA (1 world unit from 2026-10-16; 0.6 before), turned 180°, at 60 frames a second. Each
    /// setup settles for 3 s, then the fastest spring tip is measured over 2 s.
    /// </summary>
    [UnityTest]
    [Category("Diagnostic")]
    public IEnumerator AliceHairSettlesAtSorasScaleAndFrameRate()
    {
        var alice = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.local/avatars/Alice.vrm"));
        if (!File.Exists(alice)) Assert.Ignore("Alice.vrm isn't in .local/avatars (kept out of git)");
        var frameRate = Application.targetFrameRate;
        Application.targetFrameRate = 60;
        QualitySettings.vSyncCount = 0;
        var worst = new Dictionary<string, float>();
        foreach (var (setup, fps) in new[] { ("file", 60), ("tuned without colliders", 60), ("tuned", 60),
                                               ("file", -1), ("tuned without colliders", -1), ("tuned", -1) })
        {
            Application.targetFrameRate = fps;
            Vrm10Instance instance = null!;
            yield return Load(alice, i => instance = i);
            var bounds = instance.GetComponentsInChildren<Renderer>().Select(r => r.bounds)
                .Aggregate((a, b) => { a.Encapsulate(b); return a; });
            instance.transform.localScale = Vector3.one * (SoraHeight / bounds.size.y);
            instance.transform.rotation = Quaternion.Euler(0, 180, 0);
            if (setup != "file")
                instance.gameObject.AddComponent<AvatarSecondaryMotionTuner>()
                    .Configure(instance, null, generateColliders: setup == "tuned");
            var tips = instance.SpringBone.Springs.Where(s => s.Joints.Count > 1)
                .Select(s => (name: s.Joints[0].name, tip: s.Joints[s.Joints.Count - 1].transform)).ToList();
            for (var frame = 0; frame < 180; frame++) yield return null;
            var last = tips.Select(t => t.tip.position).ToList();
            var fastest = 0f;
            var fastestName = "";
            for (var frame = 0; frame < 120; frame++)
            {
                yield return null;
                for (var i = 0; i < tips.Count; i++)
                {
                    var moved = Vector3.Distance(tips[i].tip.position, last[i]);
                    if (moved > fastest) { fastest = moved; fastestName = tips[i].name; }
                    last[i] = tips[i].tip.position;
                }
            }
            // As a fraction of her height per frame, then in mm per frame on a 1.4 m person.
            if (fps == 60) worst[setup] = fastest / SoraHeight;
            Debug.Log($"P16 jitter [{setup} @ {(fps > 0 ? fps + " fps" : "uncapped")}]: fastest tip {fastestName} moves {fastest / SoraHeight * 1400f:0.0} mm a frame " +
                      $"(frame time {Time.deltaTime * 1000f:0.0} ms)");
            Object.Destroy(instance.gameObject);
            yield return null;
        }
        Application.targetFrameRate = frameRate;
        Assert.Less(worst["tuned"] * 1400f, 2f, "standing still, no tip moves more than 2 mm a frame (at life size)");
    }

    [UnityTest]
    public IEnumerator AliceGetsCollidersGravityAndHerTailHangs()
    {
        var alice = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.local/avatars/Alice.vrm"));
        if (!File.Exists(alice)) Assert.Ignore("Alice.vrm isn't in .local/avatars (kept out of git)");
        Vrm10Instance instance = null!;
        yield return Load(alice, i => instance = i);
        Assert.IsTrue(instance.SpringBone.Springs.All(s => s.ColliderGroups.Count == 0), "Alice ships with no colliders");
        var frameRate = Application.targetFrameRate;
        Application.targetFrameRate = 60;  // SORA's player rate; her file is unstable at very short frames
        var tuner = instance.gameObject.AddComponent<AvatarSecondaryMotionTuner>();
        var count = tuner.Configure(instance);
        Assert.AreEqual(count, tuner.Parts.Count);
        // Chains clear of her body at rest get body colliders; chains already overlapping a capsule
        // (which would be shoved every frame) don't.
        var withColliders = instance.SpringBone.Springs.Count(s => s.ColliderGroups.Count > 0);
        Debug.Log($"P16 colliders: {withColliders} of {instance.SpringBone.Springs.Count} springs");
        Assert.Greater(withColliders, 0, "generated colliders");
        var simulated = instance.SpringBone.Springs.SelectMany(s => s.Joints.Select(j => j.transform)).ToList();
        Assert.AreEqual(simulated.Count, simulated.Distinct().Count(), "each bone is simulated by one spring");
        var kinds = tuner.Parts.Values.Select(p => p.Kind).Distinct().ToList();
        foreach (var kind in new[] { "hair", "tail", "ear", "tie", "prop" })
            CollectionAssert.Contains(kinds, kind);
        var tail = instance.SpringBone.Springs.First(s =>
            s.Joints.Count > 2 && tuner.Parts[s.Joints[0]].Kind == "tail");
        // Her tail curls upward by design; with gravity it now sags from that rest shape
        // instead of holding it weightlessly (the file's gravity is 0).
        var tipBone = tail.Joints[tail.Joints.Count - 1].transform;
        var rest = tipBone.position.y - tail.Joints[0].transform.position.y;
        for (var frame = 0; frame < 240; frame++) yield return null;
        var settled = tipBone.position.y - tail.Joints[0].transform.position.y;
        Assert.Less(settled, rest - 0.005f, "with gravity her tail sags from its rest shape");
        // Standing still, her hair settles: no tip keeps flapping (owner report, 2026-10-15).
        var tips = instance.SpringBone.Springs.Where(s => s.Joints.Count > 1)
            .Select(s => s.Joints[s.Joints.Count - 1].transform).ToList();
        var last = tips.Select(t => t.position).ToList();
        var worst = 0f;
        var worstName = "";
        for (var frame = 0; frame < 60; frame++)
        {
            yield return null;
            for (var i = 0; i < tips.Count; i++)
            {
                var moved = Vector3.Distance(tips[i].position, last[i]);
                if (moved > worst) { worst = moved; worstName = tips[i].name; }
                last[i] = tips[i].position;
            }
        }
        Debug.Log($"P16 settle (life size, frame {Time.deltaTime * 1000f:0.00} ms): fastest tip {worstName} {worst * 1000f:0.0} mm a frame");
        Application.targetFrameRate = frameRate;
        Assert.Less(worst, 0.002f, "no spring tip moves more than 2 mm a frame once she stands still");
        Object.Destroy(instance.gameObject);
    }
}
