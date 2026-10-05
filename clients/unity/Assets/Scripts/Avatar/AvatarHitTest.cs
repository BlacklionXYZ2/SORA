using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public class AvatarHitTest : MonoBehaviour
    {
        private static Camera? s_mainCamera;

        [SerializeField]
        private Camera? overlayCamera;

        private void Awake()
        {
            s_mainCamera = overlayCamera != null ? overlayCamera : Camera.main;
        }

        // Arguments are physical CLIENT pixels. Native callers must use ScreenToClient,
        // otherwise negative/global monitor offsets produce incorrect rays.
        public static bool IsCursorOverAvatar(int screenX, int screenY)
        {
            return TryGetAvatarHit(screenX, screenY, out _);
        }

        public static bool TryGetAvatarHit(int screenX, int screenY, out Vector3 hitPoint)
        {
            hitPoint = default;
            if (s_mainCamera == null)
                return false;

            // Invert Y for Unity Screen space
            var screenPoint = new Vector3(screenX, Screen.height - screenY, 0f);
            Ray ray = s_mainCamera.ScreenPointToRay(screenPoint);

            if (Physics.Raycast(ray, out RaycastHit hit, 100f))
            {
                if (hit.collider.GetComponentInParent<AvatarHitTest>() == null) return false;
                hitPoint = hit.point;
                return true;
            }

            return false;
        }
    }
}
