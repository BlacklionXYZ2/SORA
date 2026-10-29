using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using MotionEnv.AvatarLayer;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Network;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// Her motion model's stream (2026-10-27): Core relays a model's poses; her player plays them
/// on her physics body, blends between engines and records her for a Reload's handover seed.
/// The chunks here are made up (fixture motion), so these cover the player's side only: the
/// model itself is tested in motion-lab (ardy-runtime/test_service.py) and Core's relay in
/// tests/embodiment/test_motion_service.py.
/// </summary>
public sealed class P19MotionStreamTests
{
    /// <summary>Her left arm raised straight up (Unity's frame), the rest at rest.</summary>
    private static readonly Quaternion ArmUp = Quaternion.Euler(0, 0, -90);

    private static MotionMessageDto Chunk(long seq, double t0, Quaternion leftUpperArm, int frames = 24,
        bool contacts = true)
    {
        var arm = Canonical.Index("leftUpperArm");
        var list = new List<MotionFrameDto>();
        for (var i = 0; i < frames; i++)
        {
            var rot = new float[Canonical.Count][];
            for (var j = 0; j < Canonical.Count; j++)
            {
                var q = Canonical.FromUnity(j == arm ? leftUpperArm : Quaternion.identity);
                rot[j] = new[] { q.x, q.y, q.z, q.w };
            }
            list.Add(new MotionFrameDto { Root = new[] { 0f, Canonical.HipsHeight, 0f }, Rot = rot,
                Contacts = new[] { contacts, contacts, contacts, contacts } });
        }
        return new MotionMessageDto { Op = "chunk", Chunk = new MotionChunkDto { Seq = seq, T0 = t0, Fps = 60,
            Prompt = "wave|-|-", Frames = list } };
    }

    private static MotionMessageDto Source(string source) => new() { Op = "source", Source = source };

    [Test]
    public void TheClockBuffersBlendsAndWaitsForLateChunks()
    {
        var stream = new AvatarMotionStream();
        var pose = new CanonicalPose();
        Assert.IsFalse(stream.Advance(0.1f, pose), "nothing to play before a chunk");
        stream.Accept(Chunk(0, 0, ArmUp));
        stream.Accept(Source("ardy"));
        Assert.IsTrue(stream.Advance(0.15f, pose));
        Assert.AreEqual(0.5f, stream.Weight, 1e-4f, "blends in over 0.3 s");
        Assert.AreEqual(0.73f, stream.Buffered, 0.03f, "about half a second of buffer beyond the chunk");
        for (var i = 0; i < 10; i++) stream.Advance(0.1f, pose); // 1 s: past the chunk's end
        Assert.AreEqual(1f, stream.Weight);
        Assert.AreEqual(0f, stream.Buffered, 1e-4f, "waits at the last frame");
        Assert.AreEqual(1, stream.Underruns);
        Assert.Less(Quaternion.Angle(pose.Local[Canonical.Index("leftUpperArm")], ArmUp), 0.5f);
        // A newer plan replaces what it overlaps.
        stream.Accept(Chunk(1, 0.3, Quaternion.identity));
        for (var i = 0; i < 10; i++) stream.Advance(0.1f, pose);
        Assert.Less(Quaternion.Angle(pose.Local[Canonical.Index("leftUpperArm")], Quaternion.identity), 0.5f);
        // Back to her own poses: blends out, then lets the stream go.
        stream.Accept(Source("algorithmic"));
        stream.Advance(0.15f, pose);
        Assert.AreEqual(0.5f, stream.Weight, 1e-4f);
        stream.Advance(0.2f, pose);
        Assert.IsFalse(stream.Advance(0.1f, pose));
        Assert.AreEqual(0f, stream.Weight);
    }

    [Test]
    public void TheModelsHeadingIsTakenOffHerHips()
    {
        var stream = new AvatarMotionStream();
        var chunk = Chunk(0, 0, Quaternion.identity);
        var turned = Canonical.FromUnity(Quaternion.Euler(0, 40, 0));
        foreach (var f in chunk.Chunk!.Frames) f.Rot[0] = new[] { turned.x, turned.y, turned.z, turned.w };
        stream.Accept(chunk);
        stream.Accept(Source("ardy"));
        var pose = new CanonicalPose();
        stream.Advance(0.02f, pose);
        Assert.Less(Quaternion.Angle(pose.Local[0], Quaternion.identity), 0.5f);
        // The way to ask it to travel is the way it faces (canonical x is Unity's −x).
        var forward = stream.CanonicalForward;
        Assert.AreEqual(-Mathf.Sin(40 * Mathf.Deg2Rad), forward.x, 1e-3f);
        Assert.AreEqual(Mathf.Cos(40 * Mathf.Deg2Rad), forward.y, 1e-3f);
    }

    [Test]
    public void TheRecordingKeepsTheLastThreeSecondsAsCanonicalFrames()
    {
        var stream = new AvatarMotionStream();
        var local = Enumerable.Repeat(Quaternion.identity, Canonical.Count).ToArray();
        local[Canonical.Index("leftUpperArm")] = ArmUp;
        for (var i = 0; i < 300; i++) stream.Record(1f / 60, local, Canonical.HipsHeight, 1.2f);
        var seed = stream.Seed();
        Assert.AreEqual(AvatarMotionStream.RecordSeconds * AvatarMotionStream.RecordFps, seed.Length);
        Assert.IsTrue(seed.All(f => f.IsValid()));
        Assert.AreEqual(0f, seed[0].Root[2], 1e-4f, "travel is measured from the first frame");
        Assert.AreEqual(1.2f * (seed.Length - 1) / AvatarMotionStream.RecordFps, seed[^1].Root[2], 0.05f);
        var arm = seed[^1].Rot[Canonical.Index("leftUpperArm")];
        var back = Canonical.ToUnity(new Quaternion(arm[0], arm[1], arm[2], arm[3]));
        Assert.Less(Quaternion.Angle(back, ArmUp), 0.5f, "rotations go back in motion-lab's frame");
    }

    // ---- On her physics body -------------------------------------------------------------------

    private static IEnumerator Build(System.Action<(GameObject avatar, Vrm10Instance instance, AvatarPhysicsBody body)> done)
    {
        var task = Vrm10.LoadPathAsync(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"), canLoadVrm0X: true,
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        var instance = task.Result;
        var avatar = new GameObject("SORA Avatar");
        var motion = avatar.AddComponent<AvatarLocomotion>();
        instance.transform.SetParent(avatar.transform, false);
        var bounds = instance.GetComponentsInChildren<Renderer>().Select(r => r.bounds).Aggregate((a, b) => { a.Encapsulate(b); return a; });
        instance.transform.localScale = Vector3.one * (1f / bounds.size.y);
        instance.transform.localPosition = new Vector3(0, -bounds.min.y / bounds.size.y, 0);
        var ownership = new AvatarPoseOwnership();
        motion.TeleportTo(900, 1000);
        var body = avatar.AddComponent<AvatarPhysicsBody>();
        body.Configure(instance, ownership, AvatarPhysicsBody.HelpFor(null), motion);
        avatar.AddComponent<AvatarPhysicsPoseRestore>().Body = body;
        var idle = avatar.AddComponent<AvatarIdlePose>();
        idle.Configure(instance.GetComponent<Animator>(), motion, ownership);
        avatar.transform.rotation = Quaternion.Euler(0, 180, 0);
        done((avatar, instance, body));
    }

    /// <summary>Sends chunks of a pose the way Core relays them: 0.4 s each, in real time.</summary>
    private static IEnumerator Stream(AvatarMotionStream stream, Quaternion arm, float seconds, long seq0 = 0)
    {
        var start = Time.time;
        var seq = seq0;
        while (Time.time - start < seconds)
        {
            stream.Accept(Chunk(seq, seq * 0.4, arm));
            seq++;
            var next = start + (seq - seq0) * 0.4f;
            while (Time.time < next) yield return null;
        }
    }

    [UnityTest]
    public IEnumerator TheModelMovesHerBodyAndSheGoesBackWhenItStops()
    {
        (GameObject avatar, Vrm10Instance instance, AvatarPhysicsBody body) rig = default;
        yield return Build(r => rig = r);
        var animator = rig.instance.GetComponent<Animator>();
        Transform Bone(HumanBodyBones b) => animator.GetBoneTransform(b);
        yield return new WaitForSeconds(1f);
        Assert.Less(Bone(HumanBodyBones.LeftHand).position.y, Bone(HumanBodyBones.Head).position.y,
            "her own idle pose: hands below her head");

        rig.body.MotionStream.Accept(Source("ardy"));
        yield return Stream(rig.body.MotionStream, ArmUp, 2.5f);
        Assert.AreEqual(1f, rig.body.MotionStream.Weight);
        Assert.Greater(Bone(HumanBodyBones.LeftHand).position.y, Bone(HumanBodyBones.Head).position.y,
            "the model's pose: her left hand raised above her head");
        Assert.IsFalse(rig.body.IsFalling);

        // The model's process dies: no more chunks. She blends back to her own poses.
        yield return new WaitForSeconds(AvatarMotionStream.StaleSeconds + AvatarMotionStream.BufferSeconds + 1.5f);
        Assert.AreEqual(0f, rig.body.MotionStream.Weight);
        Assert.Less(Bone(HumanBodyBones.LeftHand).position.y, Bone(HumanBodyBones.Head).position.y);
        Assert.IsFalse(rig.body.IsFalling);
        Object.Destroy(rig.avatar);
    }

    [UnityTest]
    public IEnumerator HerRecordingIsHerStandingPoseFacingTheModelsWay()
    {
        (GameObject avatar, Vrm10Instance instance, AvatarPhysicsBody body) rig = default;
        yield return Build(r => rig = r);
        yield return new WaitForSeconds(AvatarMotionStream.RecordSeconds + 0.5f);
        var seed = rig.body.MotionStream.Seed();
        Assert.AreEqual(AvatarMotionStream.RecordSeconds * AvatarMotionStream.RecordFps, seed.Length);
        Assert.IsTrue(seed.All(f => f.IsValid()));
        var last = seed[^1];
        Assert.AreEqual(Canonical.HipsHeight, last.Root[1], 0.08f, "standing hips height");
        // She faces the viewer on screen (turned 180°); the seed has that turn taken off.
        var hips = new Quaternion(last.Rot[0][0], last.Rot[0][1], last.Rot[0][2], last.Rot[0][3]);
        Assert.Less(Quaternion.Angle(hips, Quaternion.identity), 20f);
        Object.Destroy(rig.avatar);
    }
}
