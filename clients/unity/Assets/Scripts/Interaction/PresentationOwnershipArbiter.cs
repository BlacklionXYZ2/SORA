using System;
using System.Collections.Generic;

namespace Sora.Embodiment.Interaction
{
    /// <summary>Atomic exclusive ownership for locomotion/gaze/reach presentation controllers.</summary>
    public sealed class PresentationOwnershipArbiter
    {
        private readonly Dictionary<string, string> _owners =
            new Dictionary<string, string>(StringComparer.Ordinal);

        public bool TryAcquire(string ownerId, IReadOnlyCollection<string> controllerClaims)
        {
            if (string.IsNullOrWhiteSpace(ownerId)) throw new ArgumentException("Owner ID is required", nameof(ownerId));
            if (controllerClaims == null) throw new ArgumentNullException(nameof(controllerClaims));
            var normalized = new HashSet<string>(StringComparer.Ordinal);
            foreach (var claim in controllerClaims)
            {
                if (string.IsNullOrWhiteSpace(claim)) throw new ArgumentException("Controller claim cannot be blank", nameof(controllerClaims));
                normalized.Add(claim.Trim().ToLowerInvariant());
            }
            foreach (var claim in normalized)
                if (_owners.TryGetValue(claim, out var existing) && existing != ownerId) return false;
            foreach (var claim in normalized) _owners[claim] = ownerId;
            return true;
        }

        public void Release(string ownerId)
        {
            foreach (var pair in new List<KeyValuePair<string, string>>(_owners))
                if (pair.Value == ownerId) _owners.Remove(pair.Key);
        }

        public bool IsOwned(string controllerClaim) =>
            _owners.ContainsKey(controllerClaim.Trim().ToLowerInvariant());
    }
}
