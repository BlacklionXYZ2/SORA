using System.Collections;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class P12GrabTests
{
    private static DisplayTopology MixedDpiLayout() => new DisplayTopology(
        new ScreenRect(-1280, 0, 3200, 1080),
        new[]
        {
            new MonitorDescriptor("secondary", false, new ScreenRect(-1280, 0, 1280, 1024),
                1.5f, "landscape", new ScreenRect(-1280, 0, 1280, 984)),
            new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080),
                1f, "landscape", new ScreenRect(0, 0, 1920, 1040)),
        }, 7);

    [UnityTest]
    public IEnumerator GrabSpringCrossesMixedDpiMonitorsAndReleaseIsBounded()
    {
        var avatar = new GameObject("grab cross-monitor test");
        var motion = avatar.AddComponent<AvatarLocomotion>();
        motion.SetTopology(MixedDpiLayout());
        motion.TeleportTo(500, 700);
        var grab = avatar.AddComponent<AvatarGrabController>();
        grab.Configure(motion);
        var transformer = new CoordinateTransformer(motion.PixelsPerMeter);
        var hit = transformer.GlobalToWorld(500, 550, motion.Topology);
        Assert.IsTrue(grab.BeginGrab(500, 550, new Vector3(hit.X, hit.Y, hit.Z)));

        for (int i = 0; i < 90; i++)
            grab.DragTo(-600, 540, 1f / 60f);
        var dragged = motion.GetCurrentGlobalPixelPosition();
        Assert.Less(dragged.GlobalX, 0);
        Assert.IsNotNull(motion.Topology.FindMonitor(dragged.GlobalX, dragged.GlobalY));

        grab.EndGrab();
        Assert.LessOrEqual(grab.VelocityPixelsPerSecond.magnitude, 1400.01f);
        for (int i = 0; i < 180; i++) grab.TickRelease(1f / 60f);
        var released = motion.GetCurrentGlobalPixelPosition();
        Assert.IsFalse(grab.HasReleaseInertia);
        Assert.IsNotNull(motion.Topology.FindMonitor(released.GlobalX, released.GlobalY));
        yield return null;
        Object.Destroy(avatar);
    }

    [Test]
    public void CaptureLossStopsGrabAndDiscardsReleaseVelocity()
    {
        var avatar = new GameObject("grab capture-loss test");
        var motion = avatar.AddComponent<AvatarLocomotion>();
        motion.SetTopology(MixedDpiLayout());
        motion.TeleportTo(500, 700);
        var grab = avatar.AddComponent<AvatarGrabController>();
        grab.Configure(motion);
        var transformer = new CoordinateTransformer(motion.PixelsPerMeter);
        var hit = transformer.GlobalToWorld(500, 550, motion.Topology);
        Assert.IsTrue(grab.BeginGrab(500, 550, new Vector3(hit.X, hit.Y, hit.Z)));
        for (int i = 0; i < 15; i++) grab.DragTo(900, 550, 1f / 60f);
        grab.CancelForCaptureLoss();
        var stopped = motion.GetCurrentGlobalPixelPosition();
        grab.TickRelease(1f);
        Assert.IsFalse(grab.IsGrabbed);
        Assert.IsFalse(grab.HasReleaseInertia);
        Assert.AreEqual(Vector2.zero, grab.VelocityPixelsPerSecond);
        Assert.AreEqual(stopped, motion.GetCurrentGlobalPixelPosition());
        Object.DestroyImmediate(avatar);
    }

    [UnityTest]
    public IEnumerator GrabBeginsOnlyFromAvatarColliderRaycast()
    {
        var cameraObject = new GameObject("grab raycast camera");
        var camera = cameraObject.AddComponent<Camera>();
        camera.tag = "MainCamera";
        camera.orthographic = true;
        camera.orthographicSize = 1f;
        camera.transform.position = new Vector3(0, 0, -10);
        var avatar = new GameObject("grab raycast avatar");
        var collider = avatar.AddComponent<CapsuleCollider>();
        collider.height = 0.6f;
        collider.radius = 0.14f;
        collider.center = new Vector3(0, 0.3f, 0);
        avatar.AddComponent<AvatarHitTest>();
        Physics.SyncTransforms();
        yield return null;
        var projected = camera.WorldToScreenPoint(collider.bounds.center);
        Assert.IsTrue(AvatarHitTest.TryGetAvatarHit(
            Mathf.RoundToInt(projected.x), Mathf.RoundToInt(Screen.height - projected.y), out var hit));
        Assert.IsTrue(collider.bounds.Contains(hit));
        Assert.IsFalse(AvatarHitTest.TryGetAvatarHit(0, 0, out _));
        Object.Destroy(avatar);
        Object.Destroy(cameraObject);
    }
}
