using System;

namespace Sora.Embodiment.Interaction
{
    /// <summary>
    /// Executes every registered action through one deterministic phase machine.
    /// The switch below is over lifecycle phases only; it never enumerates actions.
    /// </summary>
    public sealed class EmbodimentInteractionController
    {
        private readonly EmbodimentActionRegistry _registry;
        private readonly IInteractionEnvironment _environment;
        private readonly PresentationOwnershipArbiter _ownership;
        private readonly Func<double> _clock;
        private IEmbodimentActionComponent? _action;
        private InteractionContext? _context;
        private InteractionStatus _terminalAfterRetract;
        private string _terminalReason = string.Empty;
        private bool _effectAttempted;
        private bool _effectStarted;
        private bool _verified;
        private bool _cancelRequested;

        public InteractionPhase Phase { get; private set; } = InteractionPhase.None;
        public InteractionStatus Status { get; private set; } = InteractionStatus.Idle;
        public string Reason { get; private set; } = "idle";
        public bool IsActive => _context != null;
        public string? ActiveActionId => _action?.ActionId;
        public string? ActiveInstanceId => _context?.InstanceId;
        public bool EffectAttempted => _effectAttempted;
        public bool Verified => _verified;

        public event Action<InteractionContext, InteractionPhase>? OnPhaseChanged;

        public EmbodimentInteractionController(
            EmbodimentActionRegistry registry,
            IInteractionEnvironment environment,
            PresentationOwnershipArbiter ownership,
            Func<double> clock)
        {
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _environment = environment ?? throw new ArgumentNullException(nameof(environment));
            _ownership = ownership ?? throw new ArgumentNullException(nameof(ownership));
            _clock = clock ?? throw new ArgumentNullException(nameof(clock));
        }

        public bool Start(string instanceId, string actionId, InteractionTarget target,
            double timeoutSeconds)
        {
            if (IsActive) throw new InvalidOperationException("An interaction is already active");
            if (string.IsNullOrWhiteSpace(instanceId)) throw new ArgumentException("Instance ID is required", nameof(instanceId));
            if (timeoutSeconds <= 0 || double.IsNaN(timeoutSeconds) || double.IsInfinity(timeoutSeconds))
                throw new ArgumentOutOfRangeException(nameof(timeoutSeconds));
            var action = _registry.Resolve(actionId);
            var now = _clock();
            var context = new InteractionContext(instanceId, action.ActionId,
                target ?? throw new ArgumentNullException(nameof(target)), now, now + timeoutSeconds);
            if (!_environment.Connected)
            {
                Status = InteractionStatus.Failed;
                Reason = "disconnected";
                return false;
            }
            bool targetValid;
            try
            {
                targetValid = _environment.IsTargetValid(context);
            }
            catch (Exception)
            {
                Status = InteractionStatus.Failed;
                Reason = "target_validation_exception";
                return false;
            }
            if (!targetValid)
            {
                Status = InteractionStatus.Failed;
                Reason = "target_invalid";
                return false;
            }
            if (!_ownership.TryAcquire(instanceId, action.ControllerClaims))
            {
                Status = InteractionStatus.Failed;
                Reason = "controllers_busy";
                return false;
            }
            _action = action;
            _context = context;
            _terminalAfterRetract = InteractionStatus.Completed;
            _terminalReason = "completed";
            _effectAttempted = false;
            _effectStarted = false;
            _verified = false;
            _cancelRequested = false;
            Status = InteractionStatus.Running;
            Reason = "running";
            SetPhase(InteractionPhase.Navigate);
            return true;
        }

        public void Cancel()
        {
            if (IsActive) _cancelRequested = true;
        }

        public void Tick()
        {
            if (_context == null || _action == null) return;
            if (!_environment.Connected)
            {
                var status = _verified ? InteractionStatus.Completed :
                    OutcomeBeforeVerification(InteractionStatus.Failed);
                var reason = _verified ? "disconnected_after_verified_effect" :
                    (_effectAttempted ? "disconnected_after_effect_attempt" : "disconnected");
                FinalizeImmediately(status, reason);
                return;
            }
            if (Phase == InteractionPhase.Retract && _clock() >= _context.Deadline)
            {
                Finalize(_terminalAfterRetract, _terminalReason + ":retract_timeout");
                return;
            }
            if (Phase != InteractionPhase.Retract)
            {
                if (_cancelRequested)
                {
                    BeginTermination(OutcomeBeforeVerification(InteractionStatus.Cancelled),
                        _effectAttempted ? "cancelled_after_effect_attempt" : "cancelled");
                }
                else if (_clock() >= _context.Deadline)
                {
                    BeginTermination(OutcomeBeforeVerification(InteractionStatus.Failed),
                        _effectAttempted ? "timeout_after_effect_attempt" : "timeout");
                }
                else if (!TargetRemainsValid(_context))
                {
                    BeginTermination(OutcomeBeforeVerification(InteractionStatus.Failed),
                        _effectAttempted ? "target_lost_after_effect_attempt" :
                        (_targetValidationFailed ? "target_validation_exception" : "target_lost"));
                }
            }

            if (_context == null || _action == null) return;
            InteractionStepResult step;
            try
            {
                step = ExecuteCurrentPhase(_context, _action);
            }
            catch (Exception)
            {
                if (Phase == InteractionPhase.Retract)
                {
                    Finalize(_terminalAfterRetract, _terminalReason + ":retract_exception");
                    return;
                }
                BeginTermination(OutcomeBeforeVerification(InteractionStatus.Failed),
                    _effectAttempted ? "phase_exception_after_effect_attempt" : "phase_exception");
                return;
            }
            if (step == InteractionStepResult.Pending) return;
            if (step == InteractionStepResult.Failed)
            {
                if (Phase == InteractionPhase.Retract)
                {
                    Finalize(_terminalAfterRetract, _terminalReason + ":retract_failed");
                    return;
                }
                BeginTermination(OutcomeBeforeVerification(InteractionStatus.Failed),
                    _effectAttempted ? "phase_failed_after_effect_attempt" : "phase_failed");
                return;
            }
            AdvancePhase();
        }

        private InteractionStepResult ExecuteCurrentPhase(
            InteractionContext context,
            IEmbodimentActionComponent action)
        {
            switch (Phase)
            {
                case InteractionPhase.Navigate:
                    return _environment.Navigate(context);
                case InteractionPhase.Align:
                    return _environment.Align(context);
                case InteractionPhase.Reach:
                    return _environment.Reach(context);
                case InteractionPhase.Contact:
                    return _environment.Contact(context);
                case InteractionPhase.SemanticEffect:
                    if (!_effectStarted)
                    {
                        _effectStarted = true;
                        var started = action.BeginSemanticEffect(context);
                        _effectAttempted = action.EffectMayHaveOccurred;
                        return started;
                    }
                    var polled = action.PollSemanticEffect(context);
                    _effectAttempted = action.EffectMayHaveOccurred;
                    return polled;
                case InteractionPhase.Verify:
                    var result = action.Verify(context);
                    if (result == InteractionStepResult.Succeeded) _verified = true;
                    return result;
                case InteractionPhase.Retract:
                    return _environment.Retract(context);
                default:
                    return InteractionStepResult.Failed;
            }
        }

        private void AdvancePhase()
        {
            switch (Phase)
            {
                case InteractionPhase.Navigate:
                    SetPhase(InteractionPhase.Align);
                    break;
                case InteractionPhase.Align:
                    SetPhase(InteractionPhase.Reach);
                    break;
                case InteractionPhase.Reach:
                    SetPhase(InteractionPhase.Contact);
                    break;
                case InteractionPhase.Contact:
                    SetPhase(InteractionPhase.SemanticEffect);
                    break;
                case InteractionPhase.SemanticEffect:
                    SetPhase(InteractionPhase.Verify);
                    break;
                case InteractionPhase.Verify:
                    BeginTermination(InteractionStatus.Completed, "completed");
                    break;
                case InteractionPhase.Retract:
                    Finalize(_terminalAfterRetract, _terminalReason);
                    break;
                default:
                    BeginTermination(InteractionStatus.Failed, "invalid_phase");
                    break;
            }
        }

        private InteractionStatus OutcomeBeforeVerification(InteractionStatus fallback) =>
            _effectAttempted && !_verified ? InteractionStatus.UnknownOutcome : fallback;

        private bool _targetValidationFailed;

        private bool TargetRemainsValid(InteractionContext context)
        {
            _targetValidationFailed = false;
            try
            {
                return _environment.IsTargetValid(context);
            }
            catch (Exception)
            {
                _targetValidationFailed = true;
                return false;
            }
        }

        private void BeginTermination(InteractionStatus status, string reason)
        {
            if (_context == null) return;
            _terminalAfterRetract = status;
            _terminalReason = reason;
            SetPhase(InteractionPhase.Retract);
        }

        private void SetPhase(InteractionPhase phase)
        {
            Phase = phase;
            if (_context != null) OnPhaseChanged?.Invoke(_context, phase);
        }

        private void FinalizeImmediately(InteractionStatus status, string reason)
        {
            if (_context == null || _action == null) return;
            var cleanupFailed = false;
            try
            {
                _environment.Cleanup(_context, status);
            }
            catch (Exception)
            {
                cleanupFailed = true;
            }
            finally
            {
                try
                {
                    _action.Cleanup(_context, status);
                }
                catch (Exception)
                {
                    cleanupFailed = true;
                }
                finally
                {
                    _ownership.Release(_context.InstanceId);
                    _context = null;
                    _action = null;
                    Phase = InteractionPhase.None;
                    Status = status;
                    Reason = cleanupFailed ? reason + ":cleanup_failed" : reason;
                }
            }
        }

        private void Finalize(InteractionStatus status, string reason) =>
            FinalizeImmediately(status, reason);
    }
}
