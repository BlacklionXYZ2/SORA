using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Sora.Embodiment.Network;

namespace Sora.Embodiment.Interaction
{
    public sealed class DesktopPressAuthorization
    {
        public string TargetId { get; }
        public string GrantId { get; }
        public string ExpectedNameAfter { get; }

        public DesktopPressAuthorization(string targetId, string grantId, string expectedNameAfter)
        {
            if (string.IsNullOrWhiteSpace(targetId)) throw new ArgumentException("Target ID is required", nameof(targetId));
            if (string.IsNullOrWhiteSpace(grantId)) throw new ArgumentException("Grant ID is required", nameof(grantId));
            if (string.IsNullOrWhiteSpace(expectedNameAfter)) throw new ArgumentException("Expected postcondition is required", nameof(expectedNameAfter));
            TargetId = targetId;
            GrantId = grantId;
            ExpectedNameAfter = expectedNameAfter;
        }
    }

    /// <summary>
    /// Registered PRESS semantic component. Core, not Unity, owns target/grant
    /// revalidation, effect deduplication, native invocation and verification.
    /// </summary>
    public sealed class AuthorizedPressAction : IEmbodimentActionComponent
    {
        private static readonly IReadOnlyCollection<string> Claims =
            new[] { "locomotion", "gaze", "reach" };
        private readonly Func<InteractionContext, CancellationToken, Task<DesktopActionResultDto>>
            _invoke;
        private CancellationTokenSource? _requestLifetime;
        private Task<DesktopActionResultDto>? _request;
        private DesktopActionResultDto? _result;

        public string ActionId => "press";
        public IReadOnlyCollection<string> ControllerClaims => Claims;
        public bool EffectMayHaveOccurred { get; private set; }

        public AuthorizedPressAction(
            IDesktopPressTransport transport,
            Func<InteractionContext, DesktopPressAuthorization> authorization)
        {
            if (transport == null) throw new ArgumentNullException(nameof(transport));
            if (authorization == null) throw new ArgumentNullException(nameof(authorization));
            _invoke = (context, cancellationToken) =>
            {
                var authority = authorization(context);
                if (!string.Equals(authority.TargetId, context.Target.TargetId,
                    StringComparison.Ordinal))
                    throw new InvalidOperationException("PRESS authority target mismatch");
                return transport.PressDesktopTargetAsync(
                    authority.TargetId,
                    context.InstanceId,
                    authority.ExpectedNameAfter,
                    authority.GrantId,
                    cancellationToken);
            };
        }

        public AuthorizedPressAction(
            Func<InteractionContext, CancellationToken, Task<DesktopActionResultDto>>
                preparedContact)
        {
            _invoke = preparedContact ?? throw new ArgumentNullException(nameof(preparedContact));
        }

        public InteractionStepResult BeginSemanticEffect(InteractionContext context)
        {
            if (_request != null) return InteractionStepResult.Failed;
            _requestLifetime = new CancellationTokenSource();
            EffectMayHaveOccurred = true; // Network loss is uncertain until Core's journal replies.
            _request = _invoke(context, _requestLifetime.Token);
            return InteractionStepResult.Pending;
        }

        public InteractionStepResult PollSemanticEffect(InteractionContext context)
        {
            if (_request == null) return InteractionStepResult.Failed;
            if (!_request.IsCompleted) return InteractionStepResult.Pending;
            if (_request.IsCanceled || _request.IsFaulted) return InteractionStepResult.Failed;
            _result = _request.Result;
            EffectMayHaveOccurred = _result.EffectAttempted;
            return _result.Status == "completed" ? InteractionStepResult.Succeeded :
                InteractionStepResult.Failed;
        }

        public InteractionStepResult Verify(InteractionContext context) =>
            _result != null && _result.Status == "completed" && _result.Verified ?
                InteractionStepResult.Succeeded : InteractionStepResult.Failed;

        public void Cleanup(InteractionContext context, InteractionStatus terminalStatus)
        {
            if (_request != null && !_request.IsCompleted) _requestLifetime?.Cancel();
            _requestLifetime?.Dispose();
            _requestLifetime = null;
            _request = null;
            _result = null;
            EffectMayHaveOccurred = false;
        }
    }
}
