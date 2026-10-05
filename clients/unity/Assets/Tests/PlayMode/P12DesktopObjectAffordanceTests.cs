using System;
using NUnit.Framework;
using Sora.Embodiment.Interaction;
using Sora.Embodiment.Network;
using Sora.Embodiment.Presentation;
using UnityEngine;

public sealed class P12DesktopObjectAffordanceTests
{
    private sealed class ImmediateEnvironment : IInteractionEnvironment
    {
        public bool Connected => true;
        public bool IsTargetValid(InteractionContext context) => context.Target.IsValid();
        public InteractionStepResult Navigate(InteractionContext context) =>
            InteractionStepResult.Succeeded;
        public InteractionStepResult Align(InteractionContext context) =>
            InteractionStepResult.Succeeded;
        public InteractionStepResult Reach(InteractionContext context) =>
            InteractionStepResult.Succeeded;
        public InteractionStepResult Contact(InteractionContext context) =>
            InteractionStepResult.Succeeded;
        public InteractionStepResult Retract(InteractionContext context) =>
            InteractionStepResult.Succeeded;
        public void Cleanup(InteractionContext context, InteractionStatus terminalStatus) { }
    }

    private const string Snapshot =
        "{\"type\":\"embodiment.snapshot\",\"projection\":{" +
        "\"topology\":{\"virtual_desktop\":{\"x\":0,\"y\":0,\"width\":1920,\"height\":1080}," +
        "\"monitors\":[{\"id\":\"primary\",\"primary\":true," +
        "\"rect\":{\"x\":0,\"y\":0,\"width\":1920,\"height\":1080}," +
        "\"work_area\":{\"x\":0,\"y\":0,\"width\":1920,\"height\":1040}," +
        "\"dpi_scale\":1.0,\"orientation\":\"landscape\"}],\"revision\":1}," +
        "\"revision\":1,\"embodiment_state\":null,\"connected\":true}}";

    private static string TouchCommand(bool includeRect = true)
    {
        string rectangle = includeRect
            ? "{\"x\":200,\"y\":180,\"width\":240,\"height\":160}"
            : "null";
        string commandId = includeRect ? "object-touch-valid" : "object-touch-invalid";
        return "{\"type\":\"embodiment.command\",\"command\":{" +
            "\"command_id\":\"" + commandId + "\",\"verb\":\"interaction_start\"," +
            "\"target_point\":{\"x\":320,\"y\":260},\"target_rect\":" + rectangle + "," +
            "\"target_id\":\"object-fixture\",\"semantic_action_id\":\"request-object-touch\"," +
            "\"semantic_action\":\"touch\",\"presentation_style\":\"gentle\"," +
            "\"support_surfaces\":[],\"marker_duration_seconds\":5.0," +
            "\"speed_px_per_sec\":1200.0,\"topology_revision\":1," +
            "\"created_at\":\"" + DateTime.UtcNow.ToString("O") + "\"}}";
    }

    [Test]
    public void TransportAcceptsBoundedTouchAndRejectsMalformedTouch()
    {
        using var client = new SoraCoreClient();
        EmbodimentCommandDto? received = null;
        int count = 0;
        client.OnCommandReceived += command => { received = command; count++; };
        client.ProcessIncomingMessage(Snapshot);
        client.ProcessIncomingMessage(TouchCommand());
        Assert.AreEqual(1, count);
        Assert.IsNotNull(received);
        Assert.AreEqual("touch", received!.SemanticAction);
        Assert.AreEqual("object-fixture", received.TargetId);
        Assert.AreEqual("gentle", received.PresentationStyle);

        client.ProcessIncomingMessage(TouchCommand(includeRect: false));
        Assert.AreEqual(1, count);
    }

    [Test]
    public void TouchUsesGenericLifecycleWithoutClaimingCanonicalSideEffect()
    {
        Assert.AreEqual("action.touch",
            PresentationProfileRegistry.CreateDefaults().ResolveAction("touch").ProfileId);
        int touches = 0;
        var touch = new DelegateEmbodimentAction(
            "touch",
            new[] { "locomotion", "gaze", "reach" },
            _ => { touches++; return InteractionStepResult.Succeeded; },
            _ => InteractionStepResult.Succeeded,
            effectMayChangeExternalState: false);
        var registry = new EmbodimentActionRegistry();
        registry.Register(touch);
        var controller = new EmbodimentInteractionController(
            registry,
            new ImmediateEnvironment(),
            new PresentationOwnershipArbiter(),
            () => 0);
        var target = new InteractionTarget("object-fixture", new Vector3(0.2f, 0.3f, 0),
            () => true, 320, 260, 260, 440);

        Assert.IsTrue(controller.Start("request-object-touch", "touch", target, 5));
        for (int step = 0; step < 8 && controller.IsActive; step++) controller.Tick();

        Assert.AreEqual(InteractionStatus.Completed, controller.Status);
        Assert.IsTrue(controller.Verified);
        Assert.IsFalse(controller.EffectAttempted);
        Assert.IsFalse(touch.EffectMayHaveOccurred);
        Assert.AreEqual(1, touches);
    }
}
