using System;
using UnityEngine;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Network;

namespace Sora.Embodiment.Debugging
{
    /// <summary>
    /// Developer Debug HUD toggled via F12.
    /// Renders real-time display topology, avatar world and screen coordinates,
    /// hit-test status, and connection health without impact on release builds.
    /// </summary>
    public class DebugOverlayHUD : MonoBehaviour
    {
        [Header("Keybindings")]
        [SerializeField]
        private KeyCode toggleKey = KeyCode.F12;

        [Header("Components")]
        [SerializeField]
        private AvatarLocomotion? locomotion;

        [SerializeField]
        private AvatarLookAt? lookAt;

        private bool _isVisible = false;
        private DisplayTopology _topology = null!;
        private CoordinateTransformer _transformer = null!;
        private bool _isConnected = false;
        private Texture2D? _boxTexture;
        private GUIStyle? _labelStyle;
        private GUIStyle? _headerStyle;
        private AttentionMarker? _marker;
        private float _frameMs;

        public bool IsVisible
        {
            get => _isVisible;
            set => _isVisible = value;
        }

        private void Awake()
        {
            _transformer = new CoordinateTransformer(500.0f);
            _topology = new DisplayTopology(
                new ScreenRect(0, 0, 1920, 1080),
                new[] { new MonitorDescriptor("PRIMARY", true, new ScreenRect(0, 0, 1920, 1080)) },
                1
            );

            _boxTexture = new Texture2D(1, 1);
            _boxTexture.SetPixel(0, 0, new Color(0.1f, 0.1f, 0.15f, 0.85f));
            _boxTexture.Apply();
        }

        public void SetTopology(DisplayTopology topology)
        {
            _topology = topology ?? throw new ArgumentNullException(nameof(topology));
        }

        public void Configure(AvatarLocomotion motion, AvatarLookAt gaze, AttentionMarker marker)
        { locomotion = motion; lookAt = gaze; _marker = marker; }
        private void OnDestroy() { if (_boxTexture != null) Destroy(_boxTexture); }

        public void SetConnectionState(bool connected)
        {
            _isConnected = connected;
        }

        private void Update()
        {
            _frameMs = Mathf.Lerp(_frameMs, Time.unscaledDeltaTime * 1000, 0.05f);
            if (Input.GetKeyDown(toggleKey))
            {
                _isVisible = !_isVisible;
            }
        }

        private void OnGUI()
        {
            if (!_isVisible) return;

            if (_labelStyle == null)
            {
                _labelStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 13,
                    normal = { textColor = Color.white }
                };

                _headerStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 14,
                    fontStyle = FontStyle.Bold,
                    normal = { textColor = new Color(0.4f, 0.8f, 1.0f) }
                };
            }

            const float panelWidth = 420f;
            const float panelHeight = 470f;
            var panelRect = new Rect(20, 20, panelWidth, panelHeight);

            if (_boxTexture != null)
            {
                GUI.DrawTexture(panelRect, _boxTexture);
            }

            GUILayout.BeginArea(new Rect(30, 25, panelWidth - 20, panelHeight - 10));

            GUILayout.Label("=== SORA Embodiment Debug HUD [F12] ===", _headerStyle);
            GUILayout.Label($"Frame: {_frameMs:F2} ms; {1000 / Mathf.Max(_frameMs, 0.01f):F1} FPS", _labelStyle);
            GUILayout.Space(4);

            // Connection state
            string statusStr = _isConnected ? "<color=#00FF88>Connected</color>" : "<color=#FF5555>Disconnected</color>";
            GUILayout.Label($"Core Status: {statusStr}", _labelStyle);

            // Display Topology
            GUILayout.Space(4);
            GUILayout.Label($"Display Topology (Revision {_topology.Revision}):", _headerStyle);
            GUILayout.Label($"  Virtual Desktop: {_topology.VirtualDesktop.X},{_topology.VirtualDesktop.Y} {_topology.VirtualDesktop.Width}x{_topology.VirtualDesktop.Height}", _labelStyle);
            foreach (var m in _topology.Monitors)
            {
                string tag = m.Primary ? "[Primary]" : "";
                GUILayout.Label($"  Monitor {m.Id} {tag}: {m.Rect.X},{m.Rect.Y} {m.Rect.Width}x{m.Rect.Height} (DPI {m.DpiScale:F2}x, {m.Orientation})", _labelStyle);
            }

            // Avatar Coordinates
            GUILayout.Space(4);
            GUILayout.Label("Avatar Coordinates:", _headerStyle);
            if (locomotion != null)
            {
                var globalPos = locomotion.GetCurrentGlobalPixelPosition();
                var worldPos = locomotion.transform.position;
                var currentMon = _topology.FindMonitor(globalPos.GlobalX, globalPos.GlobalY);

                GUILayout.Label($"  World Pos: ({worldPos.x:F3}, {worldPos.y:F3}, {worldPos.z:F3})m", _labelStyle);
                GUILayout.Label($"  Global Desktop: ({globalPos.GlobalX}, {globalPos.GlobalY}) px", _labelStyle);
                GUILayout.Label($"  Containing Monitor: {(currentMon != null ? currentMon.Id : "NONE (Gap/Offscreen)")}", _labelStyle);
                GUILayout.Label($"  Moving: {locomotion.IsMoving}", _labelStyle);
            }

            if (lookAt != null)
            {
                GUILayout.Label($"  Looking: {lookAt.IsLooking} -> Target: ({lookAt.TargetWorldPoint.x:F2}, {lookAt.TargetWorldPoint.y:F2})m", _labelStyle);
            }
            if (_marker != null)
                GUILayout.Label($"Interpreted target: {_marker.TargetId ?? "none"}; phase: {_marker.LastPhase ?? "none"}", _labelStyle);
            GUILayout.Label("World/reach plane z=0m; marker z=-1m; camera z=-10m. IK solver deferred to P11.", _labelStyle);
            if (locomotion != null)
            {
                var nav = locomotion.TargetWorldPosition;
                var screen = _transformer.WorldToGlobal(new UnityWorldPoint(nav.x, nav.y, nav.z), _topology);
                GUILayout.Label($"Nav target: ({screen.GlobalX}, {screen.GlobalY})px / ({nav.x:F3}, {nav.y:F3}, {nav.z:F3})m", _labelStyle);
            }

            // Hit test state
            GUILayout.Space(4);
            Vector3 mousePos = Input.mousePosition;
            int screenX = (int)mousePos.x;
            int screenY = (int)(Screen.height - mousePos.y);
            bool isOverAvatar = AvatarHitTest.IsCursorOverAvatar(screenX, screenY);
            string hitStr = isOverAvatar ? "<color=#FFCC00>CAPTURED (Avatar)</color>" : "<color=#AAAAAA>TRANSPARENT (Desktop Pass-through)</color>";
            GUILayout.Label($"Hit-Test: {hitStr}", _labelStyle);

            GUILayout.EndArea();
            if (locomotion != null)
            {
                DrawCross(locomotion.transform.position, Color.green);
                DrawCross(locomotion.TargetWorldPosition, Color.yellow);
            }
            if (lookAt != null && lookAt.IsLooking) DrawCross(lookAt.TargetWorldPoint, Color.magenta);
        }

        private static void DrawCross(Vector3 world, Color color)
        {
            if (Camera.main == null) return;
            var point = Camera.main.WorldToScreenPoint(world);
            var old = GUI.color;
            GUI.color = color;
            GUI.DrawTexture(new Rect(point.x - 6, Screen.height - point.y - 1, 13, 2), Texture2D.whiteTexture);
            GUI.DrawTexture(new Rect(point.x - 1, Screen.height - point.y - 6, 2, 13), Texture2D.whiteTexture);
            GUI.color = old;
        }
    }
}
