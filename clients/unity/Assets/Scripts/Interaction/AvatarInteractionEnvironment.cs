using System;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Presentation;

namespace Sora.Embodiment.Interaction
{
    /// <summary>
    /// Avatar adapter for the generic lifecycle. Spatial targets may provide a
    /// separate safe standing point, so reach cannot begin before locomotion arrives.
    /// Semantic effects and authority remain outside this presentation environment.
    /// </summary>
    public sealed class AvatarInteractionEnvironment : IInteractionEnvironment
    {
        private readonly AvatarLookAt _gaze;
        private readonly AvatarReachController _reach;
        private readonly AvatarPresentationController _presentation;
        private readonly AvatarLocomotion? _locomotion;
        private string? _reachingInstance;
        private string? _navigatingInstance;

        public bool Connected { get; private set; }

        public AvatarInteractionEnvironment(
            AvatarLookAt gaze,
            AvatarReachController reach,
            AvatarPresentationController presentation,
            AvatarLocomotion? locomotion = null)
        {
            _gaze = gaze ?? throw new ArgumentNullException(nameof(gaze));
            _reach = reach ?? throw new ArgumentNullException(nameof(reach));
            _presentation = presentation ?? throw new ArgumentNullException(nameof(presentation));
            _locomotion = locomotion;
        }

        public void SetConnected(bool connected)
        {
            Connected = connected;
            if (!connected)
            {
                _reach.AbortImmediate();
                StopLocomotion();
                _gaze.ResetGaze();
                _presentation.ResetToIdle();
                _reachingInstance = null;
                _navigatingInstance = null;
            }
        }

        public bool IsTargetValid(InteractionContext context) => context.Target.IsValid();

        public InteractionStepResult Navigate(InteractionContext context)
        {
            if (!context.Target.NavigationX.HasValue) return InteractionStepResult.Succeeded;
            if (_locomotion == null) return InteractionStepResult.Failed;
            if (_navigatingInstance == null)
            {
                if (_locomotion.IsMoving) return InteractionStepResult.Failed;
                _locomotion.MoveTo(context.Target.NavigationX.Value,
                    context.Target.NavigationY!.Value);
                _navigatingInstance = context.InstanceId;
                return InteractionStepResult.Pending;
            }
            if (_navigatingInstance != context.InstanceId) return InteractionStepResult.Failed;
            if (_locomotion.IsMoving) return InteractionStepResult.Pending;
            _navigatingInstance = null;
            return InteractionStepResult.Succeeded;
        }

        public InteractionStepResult Align(InteractionContext context)
        {
            _gaze.LookAtWorldPoint(context.Target.WorldPoint);
            return InteractionStepResult.Succeeded;
        }

        public InteractionStepResult Reach(InteractionContext context)
        {
            if (_reach.State == ReachControllerState.Holding && _reachingInstance == context.InstanceId)
                return InteractionStepResult.Succeeded;
            if (_reach.State != ReachControllerState.Idle)
                return _reachingInstance == context.InstanceId ? InteractionStepResult.Pending :
                    InteractionStepResult.Failed;
            var profile = _presentation.PresentAction(context.ActionId);
            if (!_reach.BeginReach(context.Target.WorldPoint, profile)) return InteractionStepResult.Failed;
            _reachingInstance = context.InstanceId;
            return InteractionStepResult.Pending;
        }

        public InteractionStepResult Contact(InteractionContext context) =>
            _reachingInstance == context.InstanceId && _reach.State == ReachControllerState.Holding ?
                InteractionStepResult.Succeeded : InteractionStepResult.Failed;

        public InteractionStepResult Retract(InteractionContext context)
        {
            if (_reach.State == ReachControllerState.Idle)
            {
                _reachingInstance = null;
                return InteractionStepResult.Succeeded;
            }
            if (_reachingInstance != context.InstanceId) return InteractionStepResult.Failed;
            if (_reach.State == ReachControllerState.Holding ||
                _reach.State == ReachControllerState.BlendingIn)
                _reach.Retract();
            return InteractionStepResult.Pending;
        }

        public void Cleanup(InteractionContext context, InteractionStatus terminalStatus)
        {
            _reach.AbortImmediate();
            StopLocomotion();
            _gaze.ResetGaze();
            _presentation.ResetToIdle();
            _reachingInstance = null;
            _navigatingInstance = null;
        }

        private void StopLocomotion()
        {
            if (_locomotion == null || !_locomotion.IsMoving) return;
            var point = _locomotion.GetCurrentGlobalPixelPosition();
            _locomotion.TeleportTo(point.GlobalX, point.GlobalY);
        }
    }
}
