using System;
using System.Collections.Generic;
using UnityEngine;

namespace Sora.Embodiment.Interaction
{
    public enum InteractionPhase
    {
        None,
        Navigate,
        Align,
        Reach,
        Contact,
        SemanticEffect,
        Verify,
        Retract
    }

    public enum InteractionStatus
    {
        Idle,
        Running,
        Completed,
        Cancelled,
        Failed,
        UnknownOutcome
    }

    public enum InteractionStepResult
    {
        Pending,
        Succeeded,
        Failed
    }

    public sealed class InteractionTarget
    {
        public string TargetId { get; }
        public Vector3 WorldPoint { get; }
        public int? ScreenX { get; }
        public int? ScreenY { get; }
        public int? NavigationX { get; }
        public int? NavigationY { get; }
        public Func<bool> IsValid { get; }

        public InteractionTarget(string targetId, Vector3 worldPoint, Func<bool>? isValid = null,
            int? screenX = null, int? screenY = null, int? navigationX = null,
            int? navigationY = null)
        {
            if (string.IsNullOrWhiteSpace(targetId)) throw new ArgumentException("Target ID is required", nameof(targetId));
            if (!Finite(worldPoint)) throw new ArgumentOutOfRangeException(nameof(worldPoint));
            if (screenX.HasValue != screenY.HasValue)
                throw new ArgumentException("Screen target coordinates must be supplied together");
            if (navigationX.HasValue != navigationY.HasValue)
                throw new ArgumentException("Navigation coordinates must be supplied together");
            TargetId = targetId;
            WorldPoint = worldPoint;
            ScreenX = screenX;
            ScreenY = screenY;
            NavigationX = navigationX;
            NavigationY = navigationY;
            IsValid = isValid ?? (() => true);
        }

        private static bool Finite(Vector3 point) =>
            !float.IsNaN(point.x) && !float.IsInfinity(point.x) &&
            !float.IsNaN(point.y) && !float.IsInfinity(point.y) &&
            !float.IsNaN(point.z) && !float.IsInfinity(point.z);
    }

    public sealed class InteractionContext
    {
        public string InstanceId { get; }
        public string ActionId { get; }
        public InteractionTarget Target { get; }
        public double StartedAt { get; }
        public double Deadline { get; }

        public InteractionContext(string instanceId, string actionId, InteractionTarget target,
            double startedAt, double deadline)
        {
            InstanceId = instanceId;
            ActionId = actionId;
            Target = target;
            StartedAt = startedAt;
            Deadline = deadline;
        }
    }

    public interface IEmbodimentActionComponent
    {
        string ActionId { get; }
        IReadOnlyCollection<string> ControllerClaims { get; }
        bool EffectMayHaveOccurred { get; }
        InteractionStepResult BeginSemanticEffect(InteractionContext context);
        InteractionStepResult PollSemanticEffect(InteractionContext context);
        InteractionStepResult Verify(InteractionContext context);
        void Cleanup(InteractionContext context, InteractionStatus terminalStatus);
    }

    public interface IInteractionEnvironment
    {
        bool Connected { get; }
        bool IsTargetValid(InteractionContext context);
        InteractionStepResult Navigate(InteractionContext context);
        InteractionStepResult Align(InteractionContext context);
        InteractionStepResult Reach(InteractionContext context);
        InteractionStepResult Contact(InteractionContext context);
        InteractionStepResult Retract(InteractionContext context);
        void Cleanup(InteractionContext context, InteractionStatus terminalStatus);
    }

    /// <summary>
    /// Reusable independently registered action component. Per-action effect,
    /// verification and cleanup stay outside the generic lifecycle controller.
    /// </summary>
    public sealed class DelegateEmbodimentAction : IEmbodimentActionComponent
    {
        private readonly Func<InteractionContext, InteractionStepResult> _effect;
        private readonly Func<InteractionContext, InteractionStepResult> _pollEffect;
        private readonly Func<InteractionContext, InteractionStepResult> _verify;
        private readonly Action<InteractionContext, InteractionStatus> _cleanup;
        private readonly bool _effectMayChangeExternalState;
        private bool _effectMayHaveOccurred;

        public string ActionId { get; }
        public IReadOnlyCollection<string> ControllerClaims { get; }
        public bool EffectMayHaveOccurred => _effectMayHaveOccurred;

        public DelegateEmbodimentAction(
            string actionId,
            IReadOnlyCollection<string> controllerClaims,
            Func<InteractionContext, InteractionStepResult> effect,
            Func<InteractionContext, InteractionStepResult> verify,
            Func<InteractionContext, InteractionStepResult>? pollEffect = null,
            Action<InteractionContext, InteractionStatus>? cleanup = null,
            bool effectMayChangeExternalState = true)
        {
            if (string.IsNullOrWhiteSpace(actionId)) throw new ArgumentException("Action ID is required", nameof(actionId));
            ActionId = actionId.Trim().ToLowerInvariant();
            ControllerClaims = controllerClaims ?? throw new ArgumentNullException(nameof(controllerClaims));
            _effect = effect ?? throw new ArgumentNullException(nameof(effect));
            _pollEffect = pollEffect ?? (_ => InteractionStepResult.Pending);
            _verify = verify ?? throw new ArgumentNullException(nameof(verify));
            _cleanup = cleanup ?? ((_, _) => { });
            _effectMayChangeExternalState = effectMayChangeExternalState;
        }

        public InteractionStepResult BeginSemanticEffect(InteractionContext context)
        {
            _effectMayHaveOccurred = _effectMayChangeExternalState;
            return _effect(context);
        }
        public InteractionStepResult PollSemanticEffect(InteractionContext context) => _pollEffect(context);
        public InteractionStepResult Verify(InteractionContext context) => _verify(context);
        public void Cleanup(InteractionContext context, InteractionStatus terminalStatus)
        {
            try { _cleanup(context, terminalStatus); }
            finally { _effectMayHaveOccurred = false; }
        }
    }
}
