using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Sora.Embodiment.Network;

namespace Sora.Embodiment.Interaction
{
    /// <summary>
    /// Registered logical TYPE component. Text, target authority, native UIA
    /// mutation and verification remain Core-owned; Unity receives only an attempt ID.
    /// </summary>
    public sealed class AuthorizedTypeAction : IEmbodimentActionComponent
    {
        private static readonly IReadOnlyCollection<string> Claims =
            new[] { "locomotion", "gaze", "reach" };
        private readonly Func<InteractionContext, CancellationToken, Task<DesktopActionResultDto>>
            _contact;
        private CancellationTokenSource? _requestLifetime;
        private Task<DesktopActionResultDto>? _request;
        private DesktopActionResultDto? _result;

        public string ActionId => "type";
        public IReadOnlyCollection<string> ControllerClaims => Claims;
        public bool EffectMayHaveOccurred { get; private set; }

        public AuthorizedTypeAction(
            Func<InteractionContext, CancellationToken, Task<DesktopActionResultDto>> contact)
        {
            _contact = contact ?? throw new ArgumentNullException(nameof(contact));
        }

        public InteractionStepResult BeginSemanticEffect(InteractionContext context)
        {
            if (_request != null) return InteractionStepResult.Failed;
            _requestLifetime = new CancellationTokenSource();
            EffectMayHaveOccurred = true;
            _request = _contact(context, _requestLifetime.Token);
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
