using System;
using System.Collections.Generic;

namespace Sora.Embodiment.Interaction
{
    /// <summary>Bounded action-component registry; registration never grants authority.</summary>
    public sealed class EmbodimentActionRegistry
    {
        private readonly Dictionary<string, IEmbodimentActionComponent> _actions =
            new Dictionary<string, IEmbodimentActionComponent>(StringComparer.Ordinal);

        public int Count => _actions.Count;

        public void RegisterPointPresentation()
        {
            Register(new DelegateEmbodimentAction(
                "point", new[] { "locomotion", "gaze", "reach" },
                _ => InteractionStepResult.Succeeded,
                _ => InteractionStepResult.Succeeded,
                effectMayChangeExternalState: false));
        }

        public void Register(IEmbodimentActionComponent action)
        {
            if (action == null) throw new ArgumentNullException(nameof(action));
            var key = Normalize(action.ActionId);
            if (_actions.ContainsKey(key)) throw new InvalidOperationException("Action is already registered");
            _actions.Add(key, action);
        }

        public IEmbodimentActionComponent Resolve(string actionId)
        {
            if (!_actions.TryGetValue(Normalize(actionId), out var action))
                throw new KeyNotFoundException("Action is not registered");
            return action;
        }

        private static string Normalize(string actionId)
        {
            if (string.IsNullOrWhiteSpace(actionId)) throw new ArgumentException("Action ID is required", nameof(actionId));
            return actionId.Trim().ToLowerInvariant();
        }
    }
}
