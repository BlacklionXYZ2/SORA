using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Network;
using UnityEngine;

public sealed class P12FeedbackTests
{
    [Test]
    public void BufferDebouncesEdgesBoundsQueueAndDeduplicatesTerminals()
    {
        double clock = 10;
        var buffer = new EmbodimentFeedbackBuffer(() => clock);
        var point = new TargetPointDto(400, 500);
        Assert.IsTrue(buffer.TryEnqueue("poked", point, 1));
        Assert.IsFalse(buffer.TryEnqueue("poked", point, 1));
        clock += 0.51;
        Assert.IsTrue(buffer.TryEnqueue("poked", point, 1));
        Assert.IsFalse(buffer.TryEnqueue("support_removed", point, 1));
        Assert.IsTrue(buffer.TryEnqueue("support_removed", point, 1, "window:fixture"));
        Assert.IsTrue(buffer.TryEnqueue("completed", point, 1,
            correlationId: "interaction:one"));
        Assert.IsFalse(buffer.TryEnqueue("failed", point, 1,
            correlationId: "interaction:one"));

        for (int index = 0; index < 100; index++)
        {
            clock += 0.51;
            buffer.TryEnqueue("clicked", point, 1, subjectId: "target:" + index);
        }
        Assert.AreEqual(64, buffer.Count);
        int dequeued = 0;
        while (buffer.TryDequeue(out var item))
        {
            Assert.IsNotNull(item);
            dequeued++;
        }
        Assert.AreEqual(64, dequeued);
    }

    [Test]
    public void GrabFallLandAndSupportRemovalAreSingleEdgeEvents()
    {
        var avatar = new GameObject("P12.5 feedback fixture");
        try
        {
            var topology = new DisplayTopology(new ScreenRect(0, 0, 1920, 1080),
                new[] { new MonitorDescriptor("primary", true,
                    new ScreenRect(0, 0, 1920, 1080), 1f, "landscape",
                    new ScreenRect(0, 0, 1920, 1040)) }, 1);
            var motion = avatar.AddComponent<AvatarLocomotion>();
            motion.SetTopology(topology);
            motion.TeleportTo(500, 400);
            var grab = avatar.AddComponent<AvatarGrabController>();
            grab.Configure(motion);
            var physics = avatar.AddComponent<AvatarSimplePhysicsController>();
            physics.Configure(motion);
            var supports = avatar.AddComponent<AvatarSupportSurfaceController>();
            supports.Configure(motion, physics);
            int grabbed = 0, released = 0, clicked = 0, poked = 0;
            int fell = 0, landed = 0, removed = 0;
            grab.Grabbed += () => grabbed++;
            grab.Released += _ => released++;
            grab.Clicked += () => clicked++;
            grab.Poked += () => poked++;
            physics.Fell += _ => fell++;
            physics.LandedOnSupport += (_, _) => landed++;
            supports.SupportRemoved += (_, _) => removed++;

            var world = new CoordinateTransformer(motion.PixelsPerMeter).GlobalToWorld(
                500, 400, topology);
            Assert.IsTrue(grab.BeginGrab(500, 400, new Vector3(world.X, world.Y, world.Z)));
            grab.EndGrab();
            Assert.AreEqual((1, 1, 1, 1), (grabbed, released, clicked, poked));

            var window = new AvatarSupportSurface("window:fixture",
                new ScreenRect(300, 700, 400, 200), AvatarSupportSurfaceState.Active,
                System.DateTime.UtcNow.AddSeconds(10));
            Assert.IsTrue(supports.ApplySnapshot(new[] { window }, 1, System.DateTime.UtcNow));
            Assert.IsTrue(physics.LoseSupport());
            Assert.IsFalse(physics.LoseSupport());
            for (int frame = 0; frame < 2000 && physics.IsActive; frame++)
                physics.Tick(1f / 240f);
            Assert.AreEqual(1, fell);
            Assert.AreEqual(1, landed);
            Assert.IsTrue(supports.ApplySnapshot(System.Array.Empty<AvatarSupportSurface>(),
                1, System.DateTime.UtcNow));
            Assert.AreEqual(1, removed);
            Assert.AreEqual(2, fell);
        }
        finally
        {
            Object.DestroyImmediate(avatar);
        }
    }
}
