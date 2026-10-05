using System;
using System.Collections.Generic;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Presentation;
using UnityEngine;

public sealed class P11PresentationTests
{
    private sealed class ReachFixture : IDisposable
    {
        public GameObject Avatar { get; }
        public AvatarLookAt Gaze { get; }
        public AvatarReachController Reach { get; }
        public Transform LeftUpper { get; }
        public Transform LeftFingertip { get; }
        public Transform RightUpper { get; }
        public Transform RightFingertip { get; }

        public ReachFixture()
        {
            Avatar = new GameObject("P11 reach fixture");
            var head = Bone(Avatar.transform, "head", new Vector3(0, 0.55f, 0));
            LeftUpper = Bone(Avatar.transform, "left upper", new Vector3(-0.12f, 0.4f, 0));
            var leftLower = Bone(LeftUpper, "left lower", new Vector3(-0.16f, 0, 0));
            LeftFingertip = Bone(leftLower, "left fingertip", new Vector3(-0.16f, 0, 0));
            RightUpper = Bone(Avatar.transform, "right upper", new Vector3(0.12f, 0.4f, 0));
            var rightLower = Bone(RightUpper, "right lower", new Vector3(0.16f, 0, 0));
            RightFingertip = Bone(rightLower, "right fingertip", new Vector3(0.16f, 0, 0));
            Gaze = Avatar.AddComponent<AvatarLookAt>();
            Gaze.ConfigureHead(head);
            Reach = Avatar.AddComponent<AvatarReachController>();
            Reach.ConfigureRig(LeftUpper, leftLower, LeftFingertip,
                RightUpper, rightLower, RightFingertip, Gaze);
        }

        private static Transform Bone(Transform parent, string name, Vector3 localPosition)
        {
            var bone = new GameObject(name).transform;
            bone.SetParent(parent, false);
            bone.localPosition = localPosition;
            return bone;
        }

        public void Dispose() => UnityEngine.Object.DestroyImmediate(Avatar);
    }

    private static PresentationProfile ReachProfile() =>
        new PresentationProfile("fixture.reach", blendInSeconds: 0.1f,
            retractSeconds: 0.1f, gazeWeight: 0.5f, reachScale: 1);

    [Test]
    public void ThinkingAndStylesAreRegistryDataNotControllerBranches()
    {
        var registry = new PresentationProfileRegistry();
        registry.RegisterState("idle", new PresentationProfile("fixture.idle"));
        registry.RegisterAction("point", new PresentationProfile("fixture.point"));
        registry.RegisterAction("point", new PresentationProfile("fixture.point.careful"), "careful");
        var go = new GameObject("P11 presentation fixture");
        try
        {
            var controller = go.AddComponent<AvatarPresentationController>();
            var torso = new GameObject("torso").transform;
            torso.SetParent(go.transform, false);
            controller.ConfigurePoseTransform(torso);
            controller.Configure(registry);
            Assert.Throws<KeyNotFoundException>(() => controller.SetState("thinking"));
            registry.RegisterState("thinking", new PresentationProfile("fixture.thinking",
                bodyLeanDegrees: 12, bodyTiltDegrees: -4));
            Assert.AreEqual("fixture.thinking", controller.SetState("thinking").ProfileId);
            controller.Advance(1);
            controller.ApplyPose();
            Assert.Greater(Quaternion.Angle(Quaternion.identity, torso.localRotation), 10);
            Assert.AreEqual("fixture.point.careful", controller.PresentAction("point", "careful").ProfileId);
            Assert.AreEqual("fixture.point", controller.PresentAction("point", "unknown-style").ProfileId);
            Assert.AreEqual("thinking", controller.CurrentState);
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(go);
        }
    }

    [Test]
    public void ReachChoosesLeftAndRightArmsAndRetractsToIdle()
    {
        using var fixture = new ReachFixture();
        var profile = ReachProfile();
        var leftTarget = new Vector3(-0.30f, 0.53f, 0);
        var initialLeftDistance = Vector3.Distance(fixture.LeftFingertip.position, leftTarget);
        Assert.IsTrue(fixture.Reach.BeginReach(leftTarget, profile));
        fixture.Reach.Advance(1);
        fixture.Reach.ApplyProceduralIk();
        Assert.AreEqual(ReachArm.Left, fixture.Reach.ActiveArm);
        Assert.AreEqual(ReachControllerState.Holding, fixture.Reach.State);
        Assert.IsTrue(fixture.Gaze.IsLooking);
        Assert.Less(Vector3.Distance(fixture.LeftFingertip.position, leftTarget), initialLeftDistance);
        fixture.Reach.Retract();
        fixture.Reach.Advance(1);
        Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
        Assert.AreEqual(ReachArm.None, fixture.Reach.ActiveArm);
        Assert.AreEqual(0, fixture.Reach.Weight);
        Assert.IsFalse(fixture.Gaze.IsLooking);

        var rightTarget = new Vector3(0.30f, 0.53f, 0);
        Assert.IsTrue(fixture.Reach.BeginReach(rightTarget, profile));
        fixture.Reach.Advance(1);
        Assert.AreEqual(ReachArm.Right, fixture.Reach.ActiveArm);
        fixture.Reach.Retract();
        fixture.Reach.Advance(1);
        Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
        Assert.AreEqual(ReachPresentationOutcome.Presented, fixture.Reach.LastOutcome);
    }

    [Test]
    public void OutsideReachAndInterruptedReachEndInValidIdleState()
    {
        using var fixture = new ReachFixture();
        var leftBase = fixture.LeftUpper.localRotation;
        Assert.IsFalse(fixture.Reach.BeginReach(new Vector3(-5, 5, 0), ReachProfile()));
        Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
        Assert.AreEqual(ReachPresentationOutcome.OutOfReach, fixture.Reach.LastOutcome);
        Assert.AreEqual(0, fixture.Reach.Weight);

        Assert.IsTrue(fixture.Reach.BeginReach(new Vector3(-0.30f, 0.53f, 0), ReachProfile()));
        fixture.Reach.Advance(0.05f);
        fixture.Reach.ApplyProceduralIk();
        fixture.Reach.Interrupt();
        Assert.AreEqual(ReachControllerState.Interrupted, fixture.Reach.State);
        fixture.Reach.Advance(1);
        Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
        Assert.AreEqual(ReachArm.None, fixture.Reach.ActiveArm);
        Assert.AreEqual(ReachPresentationOutcome.Interrupted, fixture.Reach.LastOutcome);
        Assert.Less(Quaternion.Angle(leftBase, fixture.LeftUpper.localRotation), 0.001f);
    }
}
