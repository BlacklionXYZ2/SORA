using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Presentation;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class P12RagdollRecoveryTests
{
    private sealed class Fixture
    {
        public readonly GameObject Avatar = new GameObject("P12.3 ragdoll fixture");
        public readonly AvatarPoseOwnership Ownership = new AvatarPoseOwnership();
        public readonly AvatarRagdollRecoveryController Controller;
        public readonly AvatarPresentationController Presentation;
        public readonly AvatarLookAt Gaze;
        public readonly AvatarReachController Reach;
        public readonly Transform Hips;
        public readonly Transform Spine;
        public readonly Transform Head;
        public readonly Quaternion HipsRest;

        public Fixture()
        {
            Hips = Bone(Avatar.transform, "hips", new Vector3(0, 0.3f, 0));
            Spine = Bone(Hips, "spine", new Vector3(0, 0.12f, 0));
            var chest = Bone(Spine, "chest", new Vector3(0, 0.12f, 0));
            Head = Bone(chest, "head", new Vector3(0, 0.16f, 0));
            var leftUpperArm = Bone(chest, "left upper arm", new Vector3(-0.12f, 0.08f, 0));
            var leftLowerArm = Bone(leftUpperArm, "left lower arm", new Vector3(-0.14f, 0, 0));
            var leftHand = Bone(leftLowerArm, "left hand", new Vector3(-0.13f, 0, 0));
            var rightUpperArm = Bone(chest, "right upper arm", new Vector3(0.12f, 0.08f, 0));
            var rightLowerArm = Bone(rightUpperArm, "right lower arm", new Vector3(0.14f, 0, 0));
            var rightHand = Bone(rightLowerArm, "right hand", new Vector3(0.13f, 0, 0));
            var leftUpperLeg = Bone(Hips, "left upper leg", new Vector3(-0.06f, -0.12f, 0));
            var leftLowerLeg = Bone(leftUpperLeg, "left lower leg", new Vector3(0, -0.18f, 0));
            var rightUpperLeg = Bone(Hips, "right upper leg", new Vector3(0.06f, -0.12f, 0));
            var rightLowerLeg = Bone(rightUpperLeg, "right lower leg", new Vector3(0, -0.18f, 0));
            var collider = Avatar.AddComponent<CapsuleCollider>();
            HipsRest = Hips.localRotation;

            Presentation = Avatar.AddComponent<AvatarPresentationController>();
            Presentation.ConfigurePoseTransform(Spine);
            Presentation.ConfigurePoseOwnership(Ownership);
            Gaze = Avatar.AddComponent<AvatarLookAt>();
            Gaze.ConfigureHead(Head);
            Gaze.ConfigurePoseOwnership(Ownership);
            Reach = Avatar.AddComponent<AvatarReachController>();
            Reach.ConfigureRig(leftUpperArm, leftLowerArm, leftHand,
                rightUpperArm, rightLowerArm, rightHand, Gaze);
            Reach.ConfigurePoseOwnership(Ownership);

            Controller = Avatar.AddComponent<AvatarRagdollRecoveryController>();
            Controller.ConfigureRig(Hips, Spine, chest, Head,
                leftUpperArm, leftLowerArm, rightUpperArm, rightLowerArm,
                leftUpperLeg, leftLowerLeg, rightUpperLeg, rightLowerLeg,
                Ownership, collider);
            Controller.ConfigureControllers(Reach, Gaze, Presentation, null, null);
            Controller.ConfigureTiming(0.12f, 0.08f, 0.18f, 1.2f);
        }

        public void Dispose() => Object.DestroyImmediate(Avatar);

        private static Transform Bone(Transform parent, string name, Vector3 localPosition)
        {
            var bone = new GameObject(name).transform;
            bone.SetParent(parent, false);
            bone.localPosition = localPosition;
            return bone;
        }
    }

    private static IEnumerable<RagdollOrientation> FallScenarios()
    {
        yield return RagdollOrientation.Front;
        yield return RagdollOrientation.Back;
        yield return RagdollOrientation.LeftSide;
        yield return RagdollOrientation.RightSide;
    }

    [TestCaseSource(nameof(FallScenarios))]
    public void FrontBackAndSidesSettleAndRecoverExactly(RagdollOrientation scenario)
    {
        var fixture = new Fixture();
        try
        {
            Assert.IsTrue(fixture.Controller.BeginRagdoll(scenario));
            Assert.AreEqual("ragdoll-recovery", fixture.Ownership.Owner);
            bool detected = false;
            float maximumHipsAngle = 0;
            for (int frame = 0; frame < 200 && fixture.Controller.IsActive; frame++)
            {
                fixture.Controller.Advance(1f / 120f);
                detected |= fixture.Controller.DetectedOrientation == scenario;
                maximumHipsAngle = Mathf.Max(maximumHipsAngle,
                    Quaternion.Angle(fixture.HipsRest, fixture.Hips.localRotation));
            }
            Assert.IsTrue(detected, $"orientation was never classified as {scenario}");
            Assert.IsFalse(fixture.Controller.IsActive);
            Assert.AreEqual(RagdollRecoveryOutcome.Recovered, fixture.Controller.LastOutcome);
            Assert.IsFalse(fixture.Ownership.IsOwned);
            Assert.Less(Quaternion.Angle(fixture.HipsRest, fixture.Hips.localRotation), 0.001f);
            Assert.LessOrEqual(maximumHipsAngle, 88.01f);
            Assert.IsTrue(fixture.Controller.HasBodyCollision);
        }
        finally
        {
            fixture.Dispose();
        }
    }

    [Test]
    public void ExclusivePoseLeaseInterruptsIkAndBlocksCompetingWriters()
    {
        var fixture = new Fixture();
        try
        {
            var profile = new PresentationProfile("fixture.reach", blendInSeconds: 0.1f,
                retractSeconds: 0.1f, reachScale: 1);
            Assert.IsTrue(fixture.Reach.BeginReach(new Vector3(-0.25f, 0.55f, 0), profile));
            Assert.IsTrue(fixture.Controller.BeginRagdoll(RagdollOrientation.Front));
            Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
            Assert.AreEqual(ReachPresentationOutcome.Interrupted, fixture.Reach.LastOutcome);
            Assert.IsFalse(fixture.Reach.BeginReach(new Vector3(-0.25f, 0.55f, 0), profile));

            for (int frame = 0; frame < 40 &&
                fixture.Controller.State != RagdollRecoveryState.Settling; frame++)
                fixture.Controller.Advance(1f / 120f);
            var ownedPose = fixture.Hips.localRotation;
            var ownedSpine = fixture.Spine.localRotation;
            var ownedHead = fixture.Head.localRotation;
            fixture.Presentation.Advance(1);
            fixture.Presentation.ApplyPose();
            fixture.Gaze.LookAtWorldPoint(new Vector3(2, 2, 2));
            fixture.Gaze.ApplyGaze(1);
            fixture.Reach.ApplyProceduralIk();
            Assert.Less(Quaternion.Angle(ownedPose, fixture.Hips.localRotation), 0.001f);
            Assert.Less(Quaternion.Angle(ownedSpine, fixture.Spine.localRotation), 0.001f);
            Assert.Less(Quaternion.Angle(ownedHead, fixture.Head.localRotation), 0.001f);
            fixture.Controller.Interrupt();
            Assert.AreEqual(RagdollRecoveryOutcome.Interrupted, fixture.Controller.LastOutcome);
            Assert.IsFalse(fixture.Ownership.IsOwned);
            Assert.Less(Quaternion.Angle(fixture.HipsRest, fixture.Hips.localRotation), 0.001f);
        }
        finally
        {
            fixture.Dispose();
        }
    }

    [Test]
    public void TimeoutRestoresPoseAndReleasesLease()
    {
        var fixture = new Fixture();
        try
        {
            fixture.Controller.ConfigureTiming(1f, 1f, 1f, 0.05f);
            Assert.IsTrue(fixture.Controller.BeginRagdoll(RagdollOrientation.Back));
            fixture.Controller.Advance(0.06f);
            Assert.AreEqual(RagdollRecoveryOutcome.TimeoutReset, fixture.Controller.LastOutcome);
            Assert.IsFalse(fixture.Controller.IsActive);
            Assert.IsFalse(fixture.Ownership.IsOwned);
            Assert.Less(Quaternion.Angle(fixture.HipsRest, fixture.Hips.localRotation), 0.001f);
        }
        finally
        {
            fixture.Dispose();
        }
    }

    [Test]
    public void HardLandingStartsRecoveryWithBoundedDirectionalClassification()
    {
        var fixture = new Fixture();
        try
        {
            Assert.IsFalse(fixture.Controller.TryBeginFromImpact(new Vector2(0, 999)));
            Assert.IsTrue(fixture.Controller.TryBeginFromImpact(new Vector2(500, 1200)));
            for (int frame = 0; frame < 40 &&
                fixture.Controller.DetectedOrientation == RagdollOrientation.Upright; frame++)
                fixture.Controller.Advance(1f / 120f);
            Assert.AreEqual(RagdollOrientation.RightSide,
                fixture.Controller.DetectedOrientation);
            fixture.Controller.Interrupt();

            Assert.IsTrue(fixture.Controller.TryBeginFromImpact(new Vector2(-500, 1200)));
            for (int frame = 0; frame < 40 &&
                fixture.Controller.DetectedOrientation == RagdollOrientation.Upright; frame++)
                fixture.Controller.Advance(1f / 120f);
            Assert.AreEqual(RagdollOrientation.LeftSide,
                fixture.Controller.DetectedOrientation);
            fixture.Controller.Interrupt();

            Assert.IsTrue(fixture.Controller.TryBeginFromImpact(new Vector2(0, 1200)));
            for (int frame = 0; frame < 40 &&
                fixture.Controller.DetectedOrientation == RagdollOrientation.Upright; frame++)
                fixture.Controller.Advance(1f / 120f);
            Assert.AreEqual(RagdollOrientation.Front,
                fixture.Controller.DetectedOrientation);
        }
        finally
        {
            fixture.Dispose();
        }
    }

    [Test]
    public void OrientationClassifierRejectsInvalidAndDistinguishesPlanes()
    {
        Assert.AreEqual(RagdollOrientation.Upright,
            AvatarRagdollRecoveryController.ClassifyOrientation(Vector3.up));
        Assert.AreEqual(RagdollOrientation.Front,
            AvatarRagdollRecoveryController.ClassifyOrientation(Vector3.forward));
        Assert.AreEqual(RagdollOrientation.Back,
            AvatarRagdollRecoveryController.ClassifyOrientation(Vector3.back));
        Assert.AreEqual(RagdollOrientation.RightSide,
            AvatarRagdollRecoveryController.ClassifyOrientation(Vector3.right));
        Assert.AreEqual(RagdollOrientation.LeftSide,
            AvatarRagdollRecoveryController.ClassifyOrientation(Vector3.left));
        Assert.AreEqual(RagdollOrientation.Upright,
            AvatarRagdollRecoveryController.ClassifyOrientation(
                new Vector3(float.NaN, float.PositiveInfinity, 0)));
    }

    [UnityTest]
    public IEnumerator BundledVrmRunsAllRecoveryPlanesWithConstrainedJoints()
    {
        var task = Vrm10.LoadPathAsync(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"),
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        var instance = task.Result;
        var ownership = new AvatarPoseOwnership();
        var collider = instance.gameObject.AddComponent<CapsuleCollider>();
        var controller = instance.gameObject.AddComponent<AvatarRagdollRecoveryController>();
        controller.Configure(instance.GetComponent<Animator>(), ownership, collider);
        controller.ConfigureTiming(0.04f, 0.04f, 0.06f, 0.8f);
        Assert.GreaterOrEqual(controller.JointCount, 11);
        foreach (var scenario in FallScenarios())
        {
            Assert.IsTrue(controller.BeginRagdoll(scenario));
            bool detected = false;
            for (int frame = 0; frame < 200 && controller.IsActive; frame++)
            {
                controller.Advance(1f / 120f);
                detected |= controller.DetectedOrientation == scenario;
            }
            Assert.IsTrue(detected);
            Assert.AreEqual(RagdollRecoveryOutcome.Recovered, controller.LastOutcome);
        }
        Object.Destroy(instance.gameObject);
        yield return null;
    }
}
