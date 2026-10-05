using System;
using System.Linq;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Network;
using UnityEngine;

namespace Sora.Embodiment.Native
{
    public sealed class OverlayViewport : MonoBehaviour
    {
        private Camera _camera = null!;
        private WindowPresentation _window = null!;
        private SoraEmbodimentBehaviour _bridge = null!;
        private DisplayTopology? _layout;
        private readonly TopologyTransitionTracker _transitions = new TopologyTransitionTracker();
        private float _nextPoll;
        private int _settleFrames;

        public void Configure(Camera camera, WindowPresentation window, SoraEmbodimentBehaviour bridge)
        {
            _camera = camera; _window = window; _bridge = bridge;
            ReadLayout();
        }
        private void Invalidate() { _nextPoll = 0; }
        private void OnApplicationPause(bool paused) { if (!paused) Invalidate(); }
        private void OnApplicationFocus(bool focused) { if (focused) Invalidate(); }
        private void Update()
        {
            if (Time.unscaledTime >= _nextPoll) ReadLayout();
            if (_settleFrames > 0 && _layout != null)
            {
                _settleFrames--;
                _window.SetWindowBounds(_layout.VirtualDesktop);
            }
        }
        private void ReadLayout()
        {
            _nextPoll = Time.unscaledTime + 1f;
            try
            {
                var layout = WindowsDisplayTopology.Read();
                var change = _transitions.Observe(layout);
                if (change == TopologyChangeKind.None) return;
                _layout = layout;
                var bounds = layout.VirtualDesktop;
                var primary = layout.Monitors.First(m => m.Primary).Rect;
                _camera.orthographic = true;
                _camera.orthographicSize = bounds.Height / 1000f;
                _camera.aspect = (float)bounds.Width / bounds.Height;
                _camera.transform.position = new Vector3((bounds.X + bounds.Width / 2f - primary.X) / 500f,
                    -(bounds.Y + bounds.Height / 2f - primary.Y) / 500f, -10f);
                _camera.transform.rotation = Quaternion.identity;
#if !UNITY_EDITOR
                Screen.SetResolution(bounds.Width, bounds.Height, FullScreenMode.Windowed);
#endif
                _settleFrames = 10; // Unity applies SetResolution at end of frame.
                _bridge.SetNativeTopology(layout);
                Debug.Log("Display topology transition: " + change);
            }
            catch (Exception e)
            {
                _layout = null;
                if (_transitions.MarkUnavailable())
                {
                    _bridge.SuspendPresentation();
                    Debug.LogWarning("Display discovery unavailable; presentation suspended: " +
                        e.GetType().Name);
                }
            }
        }
    }
}
