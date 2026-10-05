using System;

namespace Sora.Embodiment.Avatar
{
    /// <summary>
    /// Process-local lease for writers that need exclusive access to the humanoid pose.
    /// This is presentation arbitration only; it grants no desktop authority.
    /// </summary>
    public sealed class AvatarPoseOwnership
    {
        public string? Owner { get; private set; }
        public bool IsOwned => Owner != null;

        public bool TryAcquire(string owner)
        {
            if (string.IsNullOrWhiteSpace(owner))
                throw new ArgumentException("Pose owner is required", nameof(owner));
            if (Owner != null && !string.Equals(Owner, owner, StringComparison.Ordinal))
                return false;
            Owner = owner;
            return true;
        }

        public bool IsOwnedByOther(string owner) =>
            Owner != null && !string.Equals(Owner, owner, StringComparison.Ordinal);

        public void Release(string owner)
        {
            if (string.Equals(Owner, owner, StringComparison.Ordinal)) Owner = null;
        }
    }
}
