using System;
using System.Collections.Generic;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using UnityEngine;

public sealed class P12SupportSurfaceTests
{
    private static DisplayTopology Layout(bool taskbar = true) => new DisplayTopology(
        new ScreenRect(0, 0, 1920, 1080),
        new[]
        {
            new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080),
                1f, "landscape", taskbar ? new ScreenRect(0, 0, 1920, 1040) : null),
        }, 12);

    private static (GameObject Object, AvatarLocomotion Motion,
        AvatarSimplePhysicsController Physics, AvatarSupportSurfaceController Supports) Fixture(
            bool taskbar = true)
    {
        var avatar = new GameObject("P12.4 support fixture");
        var motion = avatar.AddComponent<AvatarLocomotion>();
        motion.SetTopology(Layout(taskbar));
        motion.TeleportTo(500, 400);
        var physics = avatar.AddComponent<AvatarSimplePhysicsController>();
        physics.Configure(motion);
        var supports = avatar.AddComponent<AvatarSupportSurfaceController>();
        supports.Configure(motion, physics);
        return (avatar, motion, physics, supports);
    }

    private static AvatarSupportSurface Window(string state = "Active", int y = 700,
        DateTime? expiry = null) => new AvatarSupportSurface(
            "window:fixture", new ScreenRect(300, y, 400, 200),
            Enum.Parse<AvatarSupportSurfaceState>(state),
            expiry ?? DateTime.UtcNow.AddSeconds(10));

    private static void FallToRest(AvatarSimplePhysicsController physics)
    {
        Assert.IsTrue(physics.LoseSupport());
        for (int frame = 0; frame < 2000 && physics.IsActive; frame++)
            physics.Tick(1f / 240f);
        Assert.IsFalse(physics.IsActive);
    }

    [Test]
    public void SelectedWindowTopWinsBeforeTaskbarAndCarriesOnMove()
    {
        var fixture = Fixture();
        try
        {
            Assert.IsTrue(fixture.Supports.ApplySnapshot(new[] { Window() }, 12, DateTime.UtcNow));
            FallToRest(fixture.Physics);
            Assert.AreEqual(699, fixture.Motion.GetCurrentGlobalPixelPosition().GlobalY);
            Assert.AreEqual("window:fixture", fixture.Supports.CurrentSurfaceId);
            Assert.AreEqual("window_top", fixture.Supports.CurrentSurfaceKind);

            Assert.IsTrue(fixture.Supports.ApplySnapshot(
                new[] { Window(state: "Moving", y: 650) }, 12, DateTime.UtcNow));
            Assert.AreEqual(649, fixture.Motion.GetCurrentGlobalPixelPosition().GlobalY);
            Assert.IsFalse(fixture.Physics.IsActive);
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(fixture.Object);
        }
    }

    [TestCase("Minimized")]
    [TestCase("Closed")]
    [TestCase("Occluded")]
    public void UnavailableWindowRemovesSupportAndFallsToTaskbar(string state)
    {
        var fixture = Fixture();
        try
        {
            Assert.IsTrue(fixture.Supports.ApplySnapshot(new[] { Window() }, 12, DateTime.UtcNow));
            FallToRest(fixture.Physics);
            string? removedReason = null;
            fixture.Supports.SupportRemoved += (_, reason) => removedReason = reason;
            Assert.IsTrue(fixture.Supports.ApplySnapshot(
                new[] { Window(state) }, 12, DateTime.UtcNow));
            Assert.AreEqual(state.ToLowerInvariant(), removedReason);
            Assert.IsTrue(fixture.Physics.IsActive);
            for (int frame = 0; frame < 2000 && fixture.Physics.IsActive; frame++)
                fixture.Physics.Tick(1f / 240f);
            Assert.AreEqual(1039, fixture.Motion.GetCurrentGlobalPixelPosition().GlobalY);
            Assert.AreEqual("taskbar", fixture.Supports.CurrentSurfaceKind);
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(fixture.Object);
        }
    }

    [Test]
    public void MissingExpiredOrMovedAwaySurfaceResumesFalling()
    {
        foreach (var mode in new[] { "missing", "expired", "moved" })
        {
            var fixture = Fixture();
            try
            {
                Assert.IsTrue(fixture.Supports.ApplySnapshot(new[] { Window() }, 12,
                    DateTime.UtcNow));
                FallToRest(fixture.Physics);
                if (mode == "missing")
                    Assert.IsTrue(fixture.Supports.ApplySnapshot(
                        Array.Empty<AvatarSupportSurface>(), 12, DateTime.UtcNow));
                else if (mode == "expired")
                    fixture.Supports.Tick(DateTime.UtcNow.AddSeconds(20));
                else
                    Assert.IsTrue(fixture.Supports.ApplySnapshot(new[] {
                        new AvatarSupportSurface("window:fixture",
                            new ScreenRect(900, 700, 400, 200),
                            AvatarSupportSurfaceState.Moving, DateTime.UtcNow.AddSeconds(10))
                    }, 12, DateTime.UtcNow));
                Assert.IsTrue(fixture.Physics.IsActive, mode);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(fixture.Object);
            }
        }
    }

    [Test]
    public void SnapshotBoundsRevisionAndIdentityFailClosed()
    {
        var fixture = Fixture();
        try
        {
            Assert.IsFalse(fixture.Supports.ApplySnapshot(new[] { Window() }, 11,
                DateTime.UtcNow));
            var tooMany = new List<AvatarSupportSurface>();
            for (int index = 0; index < 33; index++)
                tooMany.Add(new AvatarSupportSurface("window:" + index,
                    new ScreenRect(300, 700, 400, 200), AvatarSupportSurfaceState.Active,
                    DateTime.UtcNow.AddSeconds(10)));
            Assert.IsFalse(fixture.Supports.ApplySnapshot(tooMany, 12, DateTime.UtcNow));
            Assert.IsFalse(fixture.Supports.ApplySnapshot(new[] { Window(), Window() }, 12,
                DateTime.UtcNow));
            Assert.AreEqual(0, fixture.Supports.SelectedWindowCount);
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(fixture.Object);
        }
    }

    [Test]
    public void ImplicitSupportDistinguishesTaskbarAndMonitorBottom()
    {
        foreach (bool taskbar in new[] { true, false })
        {
            var fixture = Fixture(taskbar);
            try
            {
                FallToRest(fixture.Physics);
                Assert.AreEqual(taskbar ? "taskbar" : "monitor_bottom",
                    fixture.Supports.CurrentSurfaceKind);
                Assert.AreEqual(taskbar ? 1039 : 1079,
                    fixture.Motion.GetCurrentGlobalPixelPosition().GlobalY);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(fixture.Object);
            }
        }
    }
}
