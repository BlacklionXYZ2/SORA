using System;
using System.Collections;
using System.IO;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Network;
using Sora.Embodiment.Native;
using UniVRM10;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class PresentationTests
{
    [OneTimeSetUp]
    public void EnableAllocationEvidence()
    {
        Unity.Collections.NativeLeakDetection.Mode = Unity.Collections.NativeLeakDetectionMode.EnabledWithStackTrace;
    }

    private static DisplayTopology Layout() => new DisplayTopology(new ScreenRect(-1080, -400, 3000, 1920),
        new[] { new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080)),
            new MonitorDescriptor("portrait", false, new ScreenRect(-1080, -400, 1080, 1920), 1.5f, "portrait") });

    [UnityTest]
    public IEnumerator MarkerExpiresAndSemanticHookDoesNotRequireAnAnimation()
    {
        var go = new GameObject("marker test");
        var marker = go.AddComponent<AttentionMarker>();
        int phases = 0;
        marker.OnSemanticPhase += (action, phase) => { Assert.AreEqual("action", action); Assert.AreEqual("reach", phase); phases++; };
        marker.Show(new EmbodimentCommandDto { TargetId = "fixture", TargetPoint = new TargetPointDto(-500, 500),
            MarkerDurationSeconds = 0.05f }, Layout());
        Assert.IsTrue(go.GetComponent<LineRenderer>().enabled);
        Assert.IsNull(go.GetComponent<Collider>());
        marker.ConsumePhase(new EmbodimentCommandDto { SemanticActionId = "action", SemanticPhase = "reach" });
        Assert.AreEqual(1, phases);
        yield return new WaitForSecondsRealtime(0.1f);
        Assert.IsNull(marker.Point);
        Assert.IsFalse(go.GetComponent<LineRenderer>().enabled);
        UnityEngine.Object.Destroy(go);
    }

    [UnityTest]
    public IEnumerator MovementAndTopologyInvalidationUsePhysicalPixels()
    {
        var go = new GameObject("motion test");
        var motion = go.AddComponent<AvatarLocomotion>();
        motion.SetTopology(Layout());
        motion.TeleportTo(500, 500);
        motion.MoveTo(550, 500, 1000);
        yield return new WaitForSecondsRealtime(0.2f);
        Assert.IsFalse(motion.IsMoving);
        Assert.AreEqual(550, motion.GetCurrentGlobalPixelPosition().GlobalX);
        motion.MoveTo(-500, 500);
        motion.SetTopology(new DisplayTopology(new ScreenRect(0, 0, 800, 600),
            new[] { new MonitorDescriptor("small", true, new ScreenRect(0, 0, 800, 600)) }, 2));
        Assert.IsFalse(motion.IsMoving);
        var point = motion.GetCurrentGlobalPixelPosition();
        Assert.That(point.GlobalX, Is.InRange(90, 709));
        UnityEngine.Object.Destroy(go);
    }

    [Test]
    public void TopologyTransitionsClassifySyntheticCoveragePrecisely()
    {
        var tracker = new TopologyTransitionTracker();
        var initial = Layout();
        Assert.AreEqual(TopologyChangeKind.Initial, tracker.Observe(initial));
        Assert.AreEqual(TopologyChangeKind.None, tracker.Observe(Layout()));

        var resolutionAndDpi = new DisplayTopology(new ScreenRect(-1200, -400, 3120, 1920),
            new[] { new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080)),
                new MonitorDescriptor("portrait", false, new ScreenRect(-1200, -400, 1200, 1920),
                    2f, "portrait") }, 2);
        var changed = tracker.Observe(resolutionAndDpi);
        Assert.IsTrue(changed.HasFlag(TopologyChangeKind.Resolution));
        Assert.IsTrue(changed.HasFlag(TopologyChangeKind.Dpi));
        Assert.IsFalse(changed.HasFlag(TopologyChangeKind.Hotplug));

        var removed = new DisplayTopology(new ScreenRect(0, 0, 1920, 1080),
            new[] { new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1920, 1080),
                1f, "landscape", new ScreenRect(0, 0, 1920, 1040)) }, 3);
        changed = tracker.Observe(removed);
        Assert.IsTrue(changed.HasFlag(TopologyChangeKind.Hotplug));
        Assert.IsTrue(changed.HasFlag(TopologyChangeKind.Resolution));
        Assert.IsTrue(changed.HasFlag(TopologyChangeKind.WorkArea));

        Assert.IsTrue(tracker.MarkUnavailable());
        Assert.IsFalse(tracker.MarkUnavailable());
        changed = tracker.Observe(removed);
        Assert.AreEqual(TopologyChangeKind.Resume, changed);
        Assert.IsFalse(tracker.IsUnavailable);
    }

    [UnityTest]
    public IEnumerator SyntheticResolutionHotplugAndResumeRelocateOffscreenAvatar()
    {
        var go = new GameObject("topology transition relocation test");
        var motion = go.AddComponent<AvatarLocomotion>();
        var tracker = new TopologyTransitionTracker();
        var initial = Layout();
        tracker.Observe(initial);
        motion.SetTopology(initial);
        motion.TeleportTo(-500, 1400);

        var primaryOnly = new DisplayTopology(new ScreenRect(0, 0, 1280, 720),
            new[] { new MonitorDescriptor("primary", true, new ScreenRect(0, 0, 1280, 720),
                1.25f, "landscape", new ScreenRect(0, 0, 1280, 680)) }, 2);
        var change = tracker.Observe(primaryOnly);
        Assert.IsTrue(change.HasFlag(TopologyChangeKind.Hotplug));
        motion.SetTopology(primaryOnly);
        var relocated = motion.GetCurrentGlobalPixelPosition();
        Assert.That(relocated.GlobalX, Is.InRange(90, 1189));
        Assert.That(relocated.GlobalY, Is.InRange(300, 679));

        tracker.MarkUnavailable();
        change = tracker.Observe(primaryOnly);
        Assert.AreEqual(TopologyChangeKind.Resume, change);
        motion.SetTopology(primaryOnly);
        Assert.AreEqual(relocated, motion.GetCurrentGlobalPixelPosition());
        yield return null;
        UnityEngine.Object.Destroy(go);
    }

    [Test]
    public void CameraProjectionMatchesPhysicalClientPixels()
    {
        var go = new GameObject("camera test");
        var camera = go.AddComponent<Camera>();
        var layout = Layout();
        var bounds = layout.VirtualDesktop;
        camera.orthographic = true;
        camera.orthographicSize = bounds.Height / 1000f;
        camera.aspect = (float)bounds.Width / bounds.Height;
        camera.transform.position = new Vector3((bounds.X + bounds.Width / 2f) / 500f,
            -(bounds.Y + bounds.Height / 2f) / 500f, -10);
        foreach (var point in new[] { (-1079, -399), (-500, 1500), (0, 0), (1919, 1079) })
        {
            var world = new CoordinateTransformer().GlobalToWorld(point.Item1, point.Item2, layout);
            var viewport = camera.WorldToViewportPoint(new Vector3(world.X, world.Y, world.Z));
            Assert.That(viewport.x * bounds.Width, Is.EqualTo(point.Item1 - bounds.X).Within(1));
            Assert.That((1 - viewport.y) * bounds.Height, Is.EqualTo(point.Item2 - bounds.Y).Within(1));
        }
        UnityEngine.Object.DestroyImmediate(go);
    }

    [UnityTest]
    public IEnumerator BundledLicensedVrmLoadsWithHumanoidHeadAndMeshes()
    {
        var task = Vrm10.LoadPathAsync(Path.Combine(Application.streamingAssetsPath, "Seed-san.vrm"),
            springboneRuntime: new Vrm10FastSpringboneRuntimeStandalone(),
            controlRigGenerationOption: ControlRigGenerationOption.None);
        while (!task.IsCompleted) yield return null;
        if (task.IsFaulted) throw task.Exception!;
        var instance = task.Result;
        Assert.IsNotNull(instance.GetComponent<Animator>().GetBoneTransform(HumanBodyBones.Head));
        Assert.IsNotEmpty(instance.GetComponentsInChildren<Renderer>());
        UnityEngine.Object.Destroy(instance.gameObject);
        // Let destruction finish before the test runner tears down the PlayMode domain.
        yield return null;
    }
}
