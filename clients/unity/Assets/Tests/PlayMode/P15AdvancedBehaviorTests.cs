using System;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Presentation;
using UnityEngine;

public sealed class P15AdvancedBehaviorTests
{
    private sealed class Fixture : IDisposable
    {
        public readonly GameObject Avatar = new GameObject("P15 behavior fixture");
        public readonly AvatarLocomotion Motion;
        public readonly AvatarPresentationController Presentation;
        public readonly AvatarIdlePose Pose;
        public readonly AvatarPoseOwnership Ownership = new AvatarPoseOwnership();
        public readonly Transform LeftArm, RightArm, LeftLeg, RightLeg;

        public Fixture()
        {
            Motion = Avatar.AddComponent<AvatarLocomotion>();
            Presentation = Avatar.AddComponent<AvatarPresentationController>();
            Pose = Avatar.AddComponent<AvatarIdlePose>();
            LeftArm = Bone("left arm"); RightArm = Bone("right arm");
            LeftLeg = Bone("left leg"); RightLeg = Bone("right leg");
            Pose.ConfigureRig(LeftArm, RightArm, LeftLeg, RightLeg, Motion,
                Ownership, Presentation);
        }

        private Transform Bone(string name)
        {
            var bone = new GameObject(name).transform;
            bone.SetParent(Avatar.transform, false);
            return bone;
        }

        public void Dispose() => UnityEngine.Object.DestroyImmediate(Avatar);
    }

    [Test]
    public void AdvancedStatesProduceDistinctBoundedPoseAndReset()
    {
        using var fixture = new Fixture();
        foreach (var state in new[] { "waving", "sitting", "leaning", "climbing" })
        {
            var profile = fixture.Presentation.SetState(state);
            Assert.That(profile.ProfileId, Does.StartWith("state."));
            fixture.Pose.ApplyPose(0.25f);
            if (state == "waving")
                Assert.Greater(Quaternion.Angle(Quaternion.identity,
                    fixture.RightArm.localRotation), 65);
            if (state == "sitting")
                Assert.Greater(Quaternion.Angle(Quaternion.identity,
                    fixture.LeftLeg.localRotation), 50);
            if (state == "climbing")
                Assert.Greater(Quaternion.Angle(Quaternion.identity,
                    fixture.LeftArm.localRotation), 65);
        }
        fixture.Presentation.ResetToIdle();
        fixture.Pose.ConfigureBehavior(AvatarProactivityMode.Quiet);
        fixture.Pose.ApplyPose(0.25f);
        Assert.Less(Quaternion.Angle(Quaternion.identity,
            fixture.LeftLeg.localRotation), 0.01f);
    }

    [Test]
    public void QuietAndDistractionLimitSuppressOnlyPassiveMotion()
    {
        using var fixture = new Fixture();
        fixture.Pose.ConfigureBehavior(AvatarProactivityMode.Ambient, 1);
        fixture.Pose.ApplyPose(1);
        var ambient = fixture.LeftArm.localRotation;
        fixture.Pose.ConfigureBehavior(AvatarProactivityMode.Quiet);
        fixture.Pose.ApplyPose(1);
        var quiet = fixture.LeftArm.localRotation;
        Assert.Greater(Quaternion.Angle(ambient, quiet), 1);
        fixture.Pose.ConfigureBehavior(AvatarProactivityMode.Ambient, 0);
        fixture.Pose.ApplyPose(1);
        Assert.Less(Quaternion.Angle(quiet, fixture.LeftArm.localRotation), 0.01f);
        fixture.Presentation.SetState("waving");
        fixture.Pose.ApplyPose(1);
        Assert.Greater(Quaternion.Angle(quiet, fixture.RightArm.localRotation), 40);
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            fixture.Pose.ConfigureBehavior(AvatarProactivityMode.Ambient, 2));
    }

    [Test]
    public void FastMovementUsesRunningGaitButExclusivePoseOwnerWins()
    {
        using var fixture = new Fixture();
        fixture.Motion.TeleportTo(400, 400);
        fixture.Motion.MoveTo(600, 400, 200);
        fixture.Pose.ApplyPose(0.2f);
        var walk = fixture.LeftLeg.localRotation;
        fixture.Motion.MoveTo(600, 400, 800);
        fixture.Pose.ApplyPose(0.2f);
        var run = fixture.LeftLeg.localRotation;
        Assert.Greater(Quaternion.Angle(walk, run), 5);
        Assert.IsTrue(fixture.Ownership.TryAcquire("ragdoll"));
        fixture.Presentation.ConfigurePoseOwnership(fixture.Ownership);
        Assert.IsTrue(fixture.Presentation.IsPoseOwned);
        fixture.LeftLeg.localRotation = Quaternion.Euler(12, 0, 0);
        fixture.Pose.ApplyPose(0.3f);
        Assert.Less(Quaternion.Angle(Quaternion.Euler(12, 0, 0),
            fixture.LeftLeg.localRotation), 0.01f);
        fixture.Ownership.Release("ragdoll");
        Assert.IsFalse(fixture.Presentation.IsPoseOwned);
    }

    [Test]
    public void PhysicalAttentionWeightIsClampedAndNeverMovesTheAvatar()
    {
        using var fixture = new Fixture();
        var head = new GameObject("head").transform;
        head.SetParent(fixture.Avatar.transform, false);
        head.localPosition = new Vector3(0, 0.5f, 0);
        var gaze = fixture.Avatar.AddComponent<AvatarLookAt>();
        gaze.ConfigureHead(head);
        var originalPosition = fixture.Avatar.transform.position;
        var target = new Vector3(2, 0.5f, 0.1f);
        gaze.LookAtWorldPoint(target, 0.25f);
        gaze.ApplyGaze(1);
        var subtle = Quaternion.Angle(Quaternion.identity, head.localRotation);
        head.localRotation = Quaternion.identity;
        gaze.LookAtWorldPoint(target, 1);
        gaze.ApplyGaze(1);
        var full = Quaternion.Angle(Quaternion.identity, head.localRotation);
        Assert.That(subtle, Is.InRange(5, 20));
        Assert.Greater(full, subtle * 2);
        Assert.AreEqual(originalPosition, fixture.Avatar.transform.position);
        Assert.Throws<ArgumentOutOfRangeException>(() => gaze.LookAtWorldPoint(target, 1.1f));
    }
}
