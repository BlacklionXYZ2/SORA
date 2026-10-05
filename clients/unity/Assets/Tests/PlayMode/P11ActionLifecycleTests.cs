using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Interaction;
using Sora.Embodiment.Network;
using Sora.Embodiment.Presentation;
using UnityEngine;

public sealed class P11ActionLifecycleTests
{
    private sealed class PressTransport : IDesktopPressTransport
    {
        private readonly DesktopActionResultDto _result;
        public int Calls { get; private set; }

        public PressTransport(string status, bool effectAttempted, bool verified)
        {
            _result = new DesktopActionResultDto {
                Status = status, EffectAttempted = effectAttempted, Verified = verified
            };
        }

        public Task<DesktopActionResultDto> PressDesktopTargetAsync(
            string targetId, string attemptId, string expectedNameAfter, string grantId,
            CancellationToken cancellationToken)
        {
            Calls++;
            Assert.AreEqual("target", targetId);
            Assert.AreEqual("authorized-press", attemptId);
            Assert.AreEqual("Confirmed once", expectedNameAfter);
            Assert.AreEqual("grant-press", grantId);
            return Task.FromResult(_result);
        }
    }

    private sealed class FakeEnvironment : IInteractionEnvironment
    {
        public bool Connected { get; set; } = true;
        public bool TargetValid { get; set; } = true;
        public int CleanupCalls { get; private set; }
        public bool ThrowOnCleanup { get; set; }
        public InteractionStepResult NavigateResult { get; set; } = InteractionStepResult.Succeeded;
        public InteractionStepResult AlignResult { get; set; } = InteractionStepResult.Succeeded;
        public InteractionStepResult ReachResult { get; set; } = InteractionStepResult.Succeeded;
        public InteractionStepResult ContactResult { get; set; } = InteractionStepResult.Succeeded;
        public InteractionStepResult RetractResult { get; set; } = InteractionStepResult.Succeeded;
        public bool IsTargetValid(InteractionContext context) => TargetValid && context.Target.IsValid();
        public InteractionStepResult Navigate(InteractionContext context) => NavigateResult;
        public InteractionStepResult Align(InteractionContext context) => AlignResult;
        public InteractionStepResult Reach(InteractionContext context) => ReachResult;
        public InteractionStepResult Contact(InteractionContext context) => ContactResult;
        public InteractionStepResult Retract(InteractionContext context) => RetractResult;
        public void Cleanup(InteractionContext context, InteractionStatus terminalStatus)
        {
            CleanupCalls++;
            if (ThrowOnCleanup) throw new InvalidOperationException("fixture cleanup failure");
        }
    }

    private sealed class AvatarFixture : IDisposable
    {
        public GameObject Avatar { get; }
        public AvatarLocomotion Motion { get; }
        public AvatarReachController Reach { get; }
        public AvatarInteractionEnvironment Environment { get; }

        public AvatarFixture()
        {
            Avatar = new GameObject("P11 action fixture");
            Motion = Avatar.AddComponent<AvatarLocomotion>();
            var head = Bone(Avatar.transform, "head", new Vector3(0, 0.55f, 0));
            var torso = Bone(Avatar.transform, "torso", new Vector3(0, 0.35f, 0));
            var leftUpper = Bone(Avatar.transform, "left upper", new Vector3(-0.12f, 0.4f, 0));
            var leftLower = Bone(leftUpper, "left lower", new Vector3(-0.16f, 0, 0));
            var leftHand = Bone(leftLower, "left hand", new Vector3(-0.16f, 0, 0));
            var rightUpper = Bone(Avatar.transform, "right upper", new Vector3(0.12f, 0.4f, 0));
            var rightLower = Bone(rightUpper, "right lower", new Vector3(0.16f, 0, 0));
            var rightHand = Bone(rightLower, "right hand", new Vector3(0.16f, 0, 0));
            var gaze = Avatar.AddComponent<AvatarLookAt>();
            gaze.ConfigureHead(head);
            var presentation = Avatar.AddComponent<AvatarPresentationController>();
            presentation.ConfigurePoseTransform(torso);
            Reach = Avatar.AddComponent<AvatarReachController>();
            Reach.ConfigureRig(leftUpper, leftLower, leftHand, rightUpper, rightLower, rightHand, gaze);
            Environment = new AvatarInteractionEnvironment(gaze, Reach, presentation, Motion);
            Environment.SetConnected(true);
        }

        private static Transform Bone(Transform parent, string name, Vector3 localPosition)
        {
            var transform = new GameObject(name).transform;
            transform.SetParent(parent, false);
            transform.localPosition = localPosition;
            return transform;
        }

        public void Dispose() => UnityEngine.Object.DestroyImmediate(Avatar);
    }

    private static DelegateEmbodimentAction Action(
        string id,
        Action<string>? effect = null,
        Func<InteractionContext, InteractionStepResult>? begin = null,
        Func<InteractionContext, InteractionStepResult>? poll = null,
        Action<InteractionContext, InteractionStatus>? cleanup = null) =>
        new DelegateEmbodimentAction(id, new[] { "locomotion", "gaze", "reach" },
            begin ?? (context => { effect?.Invoke(context.ActionId); return InteractionStepResult.Succeeded; }),
            _ => InteractionStepResult.Succeeded, poll, cleanup);

    private static InteractionTarget Target(Func<bool>? valid = null) =>
        new InteractionTarget("target", new Vector3(-0.30f, 0.53f, 0), valid);

    [Test]
    public void ProductionPointRegistrationHasNoDesktopSemanticEffect()
    {
        var registry = new EmbodimentActionRegistry();
        registry.RegisterPointPresentation();
        Assert.Throws<InvalidOperationException>(() => registry.RegisterPointPresentation());
        var point = registry.Resolve("point");
        var context = new InteractionContext("presentation", "point", Target(), 0, 20);
        Assert.That(point.BeginSemanticEffect(context), Is.EqualTo(InteractionStepResult.Succeeded));
        Assert.That(point.EffectMayHaveOccurred, Is.False);
        Assert.That(point.Verify(context), Is.EqualTo(InteractionStepResult.Succeeded));
        point.Cleanup(context, InteractionStatus.Completed);
        Assert.That(point.EffectMayHaveOccurred, Is.False);
    }

    [Test]
    public void PointAndPressUseTheSameGenericLifecycleAndReleaseControllers()
    {
        using var fixture = new AvatarFixture();
        var effects = new List<string>();
        var phases = new List<InteractionPhase>();
        var registry = new EmbodimentActionRegistry();
        registry.Register(Action("point", effects.Add));
        registry.Register(Action("press", effects.Add));
        var ownership = new PresentationOwnershipArbiter();
        double clock = 0;
        var controller = new EmbodimentInteractionController(registry, fixture.Environment,
            ownership, () => clock);
        controller.OnPhaseChanged += (_, phase) => phases.Add(phase);

        RunAvatarAction(controller, fixture.Reach, "point", "point-instance", Target());
        Assert.AreEqual(InteractionStatus.Completed, controller.Status);
        Assert.IsTrue(controller.Verified);
        Assert.IsFalse(ownership.IsOwned("reach"));
        RunAvatarAction(controller, fixture.Reach, "press", "press-instance", Target());
        Assert.AreEqual(InteractionStatus.Completed, controller.Status);
        Assert.IsFalse(ownership.IsOwned("locomotion"));
        CollectionAssert.AreEqual(new[] { "point", "press" }, effects);
        CollectionAssert.AreEqual(new[] {
            InteractionPhase.Navigate, InteractionPhase.Align, InteractionPhase.Reach,
            InteractionPhase.Contact, InteractionPhase.SemanticEffect, InteractionPhase.Verify,
            InteractionPhase.Retract,
            InteractionPhase.Navigate, InteractionPhase.Align, InteractionPhase.Reach,
            InteractionPhase.Contact, InteractionPhase.SemanticEffect, InteractionPhase.Verify,
            InteractionPhase.Retract
        }, phases);
    }

    [Test]
    public void SpatialNavigationMustArriveBeforeAlignReachAndContact()
    {
        using var fixture = new AvatarFixture();
        var phases = new List<InteractionPhase>();
        var registry = new EmbodimentActionRegistry();
        registry.Register(Action("press"));
        var controller = new EmbodimentInteractionController(registry, fixture.Environment,
            new PresentationOwnershipArbiter(), () => 0);
        controller.OnPhaseChanged += (_, phase) => phases.Add(phase);
        var target = new InteractionTarget("media-pause", new Vector3(-0.30f, 0.53f, 0),
            screenX: 220, screenY: 180, navigationX: 100, navigationY: 300);

        Assert.IsTrue(controller.Start("pause-navigation", "press", target, 5));
        controller.Tick();
        Assert.AreEqual(InteractionPhase.Navigate, controller.Phase);
        Assert.IsTrue(fixture.Motion.IsMoving);
        Assert.AreEqual(ReachControllerState.Idle, fixture.Reach.State);
        fixture.Motion.TeleportTo(100, 300);
        controller.Tick();
        Assert.AreEqual(InteractionPhase.Align, controller.Phase);
        controller.Cancel();
        controller.Tick();
        Assert.AreEqual(InteractionStatus.Cancelled, controller.Status);
        CollectionAssert.AreEqual(new[] {
            InteractionPhase.Navigate, InteractionPhase.Align, InteractionPhase.Retract
        }, phases);
    }

    [Test]
    public void CancellationTimeoutTargetLossDisconnectAndDoubleGrabAbortSafely()
    {
        foreach (var scenario in new[] { "cancel", "timeout", "target", "disconnect" })
        {
            var environment = new FakeEnvironment();
            var registry = new EmbodimentActionRegistry();
            int effects = 0;
            registry.Register(Action("press", _ => effects++));
            var ownership = new PresentationOwnershipArbiter();
            double clock = 0;
            var controller = new EmbodimentInteractionController(registry, environment,
                ownership, () => clock);
            Assert.IsTrue(controller.Start(scenario, "press", Target(), 1));
            if (scenario == "cancel") controller.Cancel();
            if (scenario == "timeout") clock = 2;
            if (scenario == "target") environment.TargetValid = false;
            if (scenario == "disconnect") environment.Connected = false;
            controller.Tick();
            Assert.IsFalse(controller.IsActive, scenario);
            Assert.AreEqual(0, effects, scenario);
            Assert.IsFalse(ownership.IsOwned("reach"), scenario);
            Assert.AreEqual(1, environment.CleanupCalls, scenario);
            Assert.AreEqual(scenario == "cancel" ? InteractionStatus.Cancelled :
                InteractionStatus.Failed, controller.Status, scenario);
        }

        var sharedEnvironment = new FakeEnvironment();
        var sharedRegistry = new EmbodimentActionRegistry();
        sharedRegistry.Register(Action("point"));
        var sharedOwnership = new PresentationOwnershipArbiter();
        var first = new EmbodimentInteractionController(sharedRegistry, sharedEnvironment,
            sharedOwnership, () => 0);
        var second = new EmbodimentInteractionController(sharedRegistry, sharedEnvironment,
            sharedOwnership, () => 0);
        Assert.IsTrue(first.Start("first", "point", Target(), 1));
        Assert.IsFalse(second.Start("second", "point", Target(), 1));
        Assert.AreEqual("controllers_busy", second.Reason);
        first.Cancel();
        first.Tick();
        Assert.IsTrue(second.Start("second", "point", Target(), 1));
    }

    [Test]
    public void PendingSemanticEffectBeginsOnceAndCancellationIsUnknownOutcome()
    {
        var environment = new FakeEnvironment();
        var registry = new EmbodimentActionRegistry();
        int begins = 0;
        int polls = 0;
        registry.Register(Action("press",
            begin: _ => { begins++; return InteractionStepResult.Pending; },
            poll: _ => { polls++; return InteractionStepResult.Pending; }));
        var ownership = new PresentationOwnershipArbiter();
        var controller = new EmbodimentInteractionController(registry, environment,
            ownership, () => 0);
        Assert.IsTrue(controller.Start("pending", "press", Target(), 5));
        for (int i = 0; i < 5; i++) controller.Tick();
        Assert.AreEqual(InteractionPhase.SemanticEffect, controller.Phase);
        Assert.AreEqual(1, begins);
        controller.Tick();
        Assert.AreEqual(1, begins);
        Assert.AreEqual(1, polls);
        controller.Cancel();
        controller.Tick();
        Assert.AreEqual(InteractionStatus.UnknownOutcome, controller.Status);
        Assert.IsFalse(controller.IsActive);
        Assert.AreEqual(1, begins);
        Assert.IsFalse(ownership.IsOwned("reach"));
    }

    [Test]
    public void NewlyRegisteredActionAndCleanupFailureNeedNoControllerChangeOrLeakedClaim()
    {
        var environment = new FakeEnvironment { ThrowOnCleanup = true };
        var registry = new EmbodimentActionRegistry();
        int effectCalls = 0;
        registry.Register(Action("wave", _ => effectCalls++,
            cleanup: (_, _) => throw new InvalidOperationException("action cleanup failure")));
        var ownership = new PresentationOwnershipArbiter();
        var controller = new EmbodimentInteractionController(registry, environment,
            ownership, () => 0);
        Assert.IsTrue(controller.Start("wave-instance", "wave", Target(), 5));
        for (int i = 0; i < 7; i++) controller.Tick();
        Assert.AreEqual(InteractionStatus.Completed, controller.Status);
        Assert.AreEqual("completed:cleanup_failed", controller.Reason);
        Assert.AreEqual(1, effectCalls);
        Assert.IsTrue(controller.Verified);
        Assert.IsFalse(ownership.IsOwned("locomotion"));
        Assert.IsFalse(controller.IsActive);
    }

    [Test]
    public void DisconnectDuringRetractionPreservesVerifiedOutcomeAndReleasesClaims()
    {
        var environment = new FakeEnvironment { RetractResult = InteractionStepResult.Pending };
        var registry = new EmbodimentActionRegistry();
        registry.Register(Action("press"));
        var ownership = new PresentationOwnershipArbiter();
        var controller = new EmbodimentInteractionController(registry, environment,
            ownership, () => 0);
        Assert.IsTrue(controller.Start("disconnect-retract", "press", Target(), 5));
        for (int i = 0; i < 6; i++) controller.Tick();
        Assert.AreEqual(InteractionPhase.Retract, controller.Phase);
        Assert.IsTrue(controller.Verified);
        environment.Connected = false;
        controller.Tick();
        Assert.AreEqual(InteractionStatus.Completed, controller.Status);
        Assert.AreEqual("disconnected_after_verified_effect", controller.Reason);
        Assert.IsFalse(controller.IsActive);
        Assert.IsFalse(ownership.IsOwned("reach"));
    }

    [TestCase("completed", true, true, InteractionStatus.Completed)]
    [TestCase("failed", false, false, InteractionStatus.Failed)]
    [TestCase("unknown_outcome", true, false, InteractionStatus.UnknownOutcome)]
    public void AuthorizedPressUsesCoreJournalEvidenceForTerminalOutcome(
        string remoteStatus, bool effectAttempted, bool verified, InteractionStatus expected)
    {
        var environment = new FakeEnvironment();
        var transport = new PressTransport(remoteStatus, effectAttempted, verified);
        var registry = new EmbodimentActionRegistry();
        registry.Register(new AuthorizedPressAction(transport, context =>
            new DesktopPressAuthorization(context.Target.TargetId, "grant-press", "Confirmed once")));
        var ownership = new PresentationOwnershipArbiter();
        var controller = new EmbodimentInteractionController(
            registry, environment, ownership, () => 0);
        Assert.IsTrue(controller.Start("authorized-press", "press", Target(), 5));
        for (int i = 0; i < 9 && controller.IsActive; i++) controller.Tick();

        Assert.AreEqual(expected, controller.Status);
        Assert.AreEqual(1, transport.Calls);
        Assert.IsFalse(controller.IsActive);
        Assert.IsFalse(ownership.IsOwned("reach"));
        Assert.AreEqual(verified, controller.Verified);
    }

    [TestCase("completed", true, true, InteractionStatus.Completed)]
    [TestCase("failed", false, false, InteractionStatus.Failed)]
    [TestCase("unknown_outcome", true, false, InteractionStatus.UnknownOutcome)]
    public void AuthorizedTypeRegistersWithoutChangingTheGenericController(
        string remoteStatus, bool effectAttempted, bool verified, InteractionStatus expected)
    {
        var environment = new FakeEnvironment();
        int contacts = 0;
        var registry = new EmbodimentActionRegistry();
        registry.Register(new AuthorizedTypeAction((context, cancellationToken) =>
        {
            contacts++;
            Assert.AreEqual("type-attempt", context.InstanceId);
            Assert.AreEqual("target", context.Target.TargetId);
            return Task.FromResult(new DesktopActionResultDto {
                Status = remoteStatus,
                EffectAttempted = effectAttempted,
                Verified = verified
            });
        }));
        var controller = new EmbodimentInteractionController(
            registry, environment, new PresentationOwnershipArbiter(), () => 0);
        Assert.IsTrue(controller.Start("type-attempt", "type", Target(), 5));
        for (int i = 0; i < 9 && controller.IsActive; i++) controller.Tick();

        Assert.AreEqual(expected, controller.Status);
        Assert.AreEqual(1, contacts);
        Assert.IsFalse(controller.IsActive);
        Assert.AreEqual(verified, controller.Verified);
    }

    private static void RunAvatarAction(EmbodimentInteractionController controller,
        AvatarReachController reach, string actionId, string instanceId, InteractionTarget target)
    {
        Assert.IsTrue(controller.Start(instanceId, actionId, target, 5));
        controller.Tick(); // Navigate -> Align
        controller.Tick(); // Align -> Reach
        controller.Tick(); // Starts reach and waits.
        reach.Advance(1);
        controller.Tick(); // Reach -> Contact
        controller.Tick(); // Contact -> SemanticEffect
        controller.Tick(); // Effect -> Verify
        controller.Tick(); // Verify -> Retract
        controller.Tick(); // Starts retraction and waits.
        reach.Advance(1);
        controller.Tick(); // Retract -> terminal result.
    }
}
