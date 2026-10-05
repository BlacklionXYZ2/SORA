using System.Collections;
using System.IO;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class P12SimplePhysicsTests
{
    private static DisplayTopology Layout() => new DisplayTopology(
        new ScreenRect(-1280, 0, 3200, 1080),
        new[]
        {
            new MonitorDescriptor("secondary", false, new ScreenRect(-1280, 0, 1280, 1024),
                1.5f, "landscape", new ScreenRect(-1280, 0, 1280, 984)),
            new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080),
                1f, "landscape", new ScreenRect(0, 0, 1920, 1040)),
        }, 8);

    private static (GameObject Object, AvatarLocomotion Motion,
        AvatarSimplePhysicsController Physics) Fixture()
    {
        var avatar = new GameObject("simple physics test");
        var motion = avatar.AddComponent<AvatarLocomotion>();
        motion.SetTopology(Layout());
        motion.TeleportTo(500, 500);
        var physics = avatar.AddComponent<AvatarSimplePhysicsController>();
        physics.Configure(motion);
        return (avatar, motion, physics);
    }

    [Test]
    public void RepeatedMixedVelocityDropsSettleWithoutInvalidState()
    {
        var fixture = Fixture();
        for (int drop = 0; drop < 100; drop++)
        {
            int x = drop % 2 == 0 ? 400 : -600;
            int y = 320 + drop % 180;
            fixture.Motion.TeleportTo(x, y);
            fixture.Physics.SuspendForGrab();
            Assert.IsTrue(fixture.Physics.Release(new Vector2(
                drop % 3 == 0 ? 1400 : -1400, -900 + drop * 7)));
            int frames = 0;
            while (fixture.Physics.IsActive && frames++ < 1000)
                fixture.Physics.Tick(1f / 240f);
            Assert.Less(frames, 1000, "drop did not settle");
            Assert.AreEqual(SimplePhysicsState.Inactive, fixture.Physics.State);
            Assert.AreEqual(Vector2.zero, fixture.Physics.VelocityPixelsPerSecond);
            var position = fixture.Motion.GetCurrentGlobalPixelPosition();
            var monitor = fixture.Motion.Topology.FindMonitor(position.GlobalX, position.GlobalY);
            Assert.IsNotNull(monitor);
            Assert.AreEqual(monitor!.WorkArea.Bottom - 1, position.GlobalY);
            Assert.IsFalse(float.IsNaN(fixture.Motion.transform.position.x));
            Assert.IsFalse(float.IsInfinity(fixture.Motion.transform.position.y));
        }
        Object.DestroyImmediate(fixture.Object);
    }

    [Test]
    public void NonFiniteReleaseAndLargeFramesRemainSafe()
    {
        var fixture = Fixture();
        fixture.Motion.TeleportTo(500, 400);
        Assert.IsFalse(fixture.Physics.Release(new Vector2(float.NaN, float.PositiveInfinity)));
        Assert.AreEqual("non_finite_release_velocity", fixture.Physics.LastSafetyResetReason);
        var reset = fixture.Motion.GetCurrentGlobalPixelPosition();
        Assert.AreEqual(1039, reset.GlobalY);

        fixture.Motion.TeleportTo(500, 350);
        Assert.IsTrue(fixture.Physics.LoseSupport());
        for (int frame = 0; frame < 100 && fixture.Physics.IsActive; frame++)
            fixture.Physics.Tick(1000f);
        Assert.IsFalse(fixture.Physics.IsActive);
        Assert.AreEqual(1039, fixture.Motion.GetCurrentGlobalPixelPosition().GlobalY);
        Assert.IsFalse(float.IsNaN(fixture.Motion.transform.position.y));
        Object.DestroyImmediate(fixture.Object);
    }

    [Test]
    public void GrabReleaseVelocityTransfersToSinglePhysicsOwner()
    {
        var fixture = Fixture();
        var grab = fixture.Object.AddComponent<AvatarGrabController>();
        grab.Configure(fixture.Motion);
        var transformer = new CoordinateTransformer(fixture.Motion.PixelsPerMeter);
        var hit = transformer.GlobalToWorld(500, 350, fixture.Motion.Topology);
        Assert.IsTrue(grab.BeginGrab(500, 350, new Vector3(hit.X, hit.Y, hit.Z)));
        fixture.Physics.SuspendForGrab();
        for (int frame = 0; frame < 20; frame++) grab.DragTo(700, 250, 1f / 60f);
        grab.EndGrab();
        var release = grab.TakeReleaseVelocity();
        Assert.IsFalse(grab.HasReleaseInertia);
        Assert.AreNotEqual(Vector2.zero, release);
        Assert.IsTrue(fixture.Physics.Release(release));
        for (int frame = 0; frame < 1000 && fixture.Physics.IsActive; frame++)
            fixture.Physics.Tick(1f / 240f);
        Assert.IsFalse(fixture.Physics.IsActive);
        Assert.AreEqual(Vector2.zero, fixture.Physics.VelocityPixelsPerSecond);
        Object.DestroyImmediate(fixture.Object);
    }

    [Test]
    public void SpringBoneSettingsClampInvalidAndExplosiveValues()
    {
        var stable = AvatarSecondaryMotionTuner.Stabilize(
            float.PositiveInfinity, float.NaN,
            new Vector3(float.NaN, float.PositiveInfinity, 0), -10, float.NaN);
        Assert.AreEqual(1f, stable.Stiffness);
        Assert.AreEqual(0f, stable.GravityPower);
        Assert.AreEqual(Vector3.down, stable.GravityDirection);
        Assert.AreEqual(0.35f, stable.Drag);
        Assert.AreEqual(0.02f, stable.Radius);

        stable = AvatarSecondaryMotionTuner.Stabilize(100, 100, Vector3.one, 100, 100);
        Assert.AreEqual(4f, stable.Stiffness);
        Assert.AreEqual(1.5f, stable.GravityPower);
        Assert.That(stable.GravityDirection.magnitude, Is.EqualTo(1).Within(0.0001));
        Assert.AreEqual(0.9f, stable.Drag);
        Assert.AreEqual(0.2f, stable.Radius);
    }

    [UnityTest]
    public IEnumerator BundledVrmSpringBonesAcceptStableRuntimeTuning()
    {
        var task = Vrm10.LoadPathAsync(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"),
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        var instance = task.Result;
        var tuner = instance.gameObject.AddComponent<AvatarSecondaryMotionTuner>();
        Assert.Greater(tuner.Configure(instance), 0);
        tuner.ResetSimulation();
        Object.Destroy(instance.gameObject);
        yield return null;
    }
}
