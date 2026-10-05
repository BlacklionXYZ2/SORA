using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Avatar;

namespace Sora.Embodiment.Native
{
    /// <summary>
    /// Manages native Win32 window styles, DWM transparency, topmost positioning,
    /// and dynamic click-through / hit-testing for the SORA Unity overlay.
    /// </summary>
    public class WindowPresentation : MonoBehaviour
    {
        private const int GWL_STYLE = -16;
        private const int GWL_EXSTYLE = -20;

        private const int WS_POPUP = unchecked((int)0x80000000);
        private const int WS_VISIBLE = 0x10000000;

        private const int WS_EX_TOPMOST = 0x00000008;
        private const int WS_EX_LAYERED = 0x00080000;
        private const int WS_EX_TRANSPARENT = 0x00000020;
        private const int WS_EX_TOOLWINDOW = 0x00000080;
        private const int WS_EX_NOACTIVATE = 0x08000000;

        private const uint SWP_NOMOVE = 0x0002;
        private const uint SWP_NOSIZE = 0x0001;
        private const uint SWP_NOZORDER = 0x0004;
        private const uint SWP_FRAMECHANGED = 0x0020;
        private const uint SWP_NOACTIVATE = 0x0010;

        private const uint WM_NCHITTEST = 0x0084;
        private const uint WM_DISPLAYCHANGE = 0x007E;
        private const uint WM_DPICHANGED = 0x02E0;
        private const uint WM_SETTINGCHANGE = 0x001A;
        private const uint WM_POWERBROADCAST = 0x0218;

        private const int HTCLIENT = 1;
        private const int HTTRANSPARENT = -1;

        private static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

        [StructLayout(LayoutKind.Sequential)]
        public struct MARGINS
        {
            public int cxLeftWidth;
            public int cxRightWidth;
            public int cyTopHeight;
            public int cyBottomHeight;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }


        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr GetActiveWindow();

        [DllImport("user32.dll", EntryPoint = "GetWindowLong")]
        private static extern int GetWindowLong32(IntPtr hWnd, int nIndex);

        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr")]
        private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int nIndex);

        private static IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex)
        {
            return IntPtr.Size == 8 ? GetWindowLongPtr64(hWnd, nIndex) : new IntPtr(GetWindowLong32(hWnd, nIndex));
        }

        [DllImport("user32.dll", EntryPoint = "SetWindowLong")]
        private static extern int SetWindowLong32(IntPtr hWnd, int nIndex, int dwNewLong);

        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr")]
        private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        private static IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong)
        {
            return IntPtr.Size == 8 ? SetWindowLongPtr64(hWnd, nIndex, dwNewLong) : new IntPtr(SetWindowLong32(hWnd, nIndex, dwNewLong.ToInt32()));
        }

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);


        [DllImport("dwmapi.dll")]
        private static extern int DwmExtendFrameIntoClientArea(IntPtr hWnd, ref MARGINS pMarInset);


        private IntPtr _hWnd = IntPtr.Zero;
        private IntPtr _originalStyle, _originalExStyle;
        private bool _cursorOverAvatar;

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT { public int X; public int Y; }
        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out POINT point);
        [DllImport("user32.dll")]
        private static extern bool ScreenToClient(IntPtr window, ref POINT point);
        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")]
        private static extern IntPtr SetCapture(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool ReleaseCapture();
        [DllImport("user32.dll")]
        private static extern IntPtr GetCapture();

        private const int VK_LBUTTON = 0x01;
        private AvatarGrabController? _grab;
        private AvatarSimplePhysicsController? _simplePhysics;
        private AvatarRagdollRecoveryController? _ragdollRecovery;
        private bool _wasLeftDown;

        [SerializeField]
        private bool enableTransparencyOnStart = true;

        public void ConfigureGrab(AvatarGrabController grab,
            AvatarSimplePhysicsController? simplePhysics = null,
            AvatarRagdollRecoveryController? ragdollRecovery = null)
        {
            _grab = grab ?? throw new ArgumentNullException(nameof(grab));
            _simplePhysics = simplePhysics;
            _ragdollRecovery = ragdollRecovery;
        }


        private void Update()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (_hWnd == IntPtr.Zero && enableTransparencyOnStart) InitializeTransparentOverlay();
            if (_hWnd != IntPtr.Zero && GetCursorPos(out var globalPoint))
            {
                var point = globalPoint;
                if (!ScreenToClient(_hWnd, ref point))
                {
                    CancelNativeGrab();
                    return;
                }
                // Unity camera/physics APIs run only on the main thread, never inside WndProc.
                _cursorOverAvatar = AvatarHitTest.TryGetAvatarHit(point.X, point.Y, out var hit);
                bool leftDown = (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
                if (_grab != null)
                {
                    if (_ragdollRecovery?.IsActive == true)
                    {
                        if (_grab.IsGrabbed) _grab.CancelForCaptureLoss();
                        if (GetCapture() == _hWnd) ReleaseCapture();
                        _wasLeftDown = leftDown;
                    }
                    if (leftDown && !_wasLeftDown && _cursorOverAvatar &&
                        _grab.BeginGrab(globalPoint.X, globalPoint.Y, hit))
                    {
                        _simplePhysics?.SuspendForGrab();
                        SetCapture(_hWnd);
                    }
                    if (_grab.IsGrabbed)
                    {
                        if (!leftDown)
                        {
                            _grab.EndGrab();
                            if (_simplePhysics != null)
                                _simplePhysics.Release(_grab.TakeReleaseVelocity());
                            ReleaseCapture();
                        }
                        else if (GetCapture() != _hWnd)
                        {
                            _grab.CancelForCaptureLoss();
                        }
                        else
                        {
                            _grab.DragTo(globalPoint.X, globalPoint.Y, Time.unscaledDeltaTime);
                        }
                    }
                    else
                    {
                        if (_simplePhysics != null)
                            _simplePhysics.Tick(Time.unscaledDeltaTime);
                        else
                            _grab.TickRelease(Time.unscaledDeltaTime);
                    }
                }
                _wasLeftDown = leftDown;
                long style = GetWindowLongPtr(_hWnd, GWL_EXSTYLE).ToInt64();
                long desired = (_cursorOverAvatar || (_grab?.IsGrabbed ?? false)) ?
                    style & ~WS_EX_TRANSPARENT : style | WS_EX_TRANSPARENT;
                if (desired != style) SetWindowLongPtr(_hWnd, GWL_EXSTYLE, new IntPtr(desired));
            }
#endif
        }

        private void Start()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (enableTransparencyOnStart)
            {
                InitializeTransparentOverlay();
            }
#else
            Debug.Log("[WindowPresentation] Running in Editor or non-Windows standalone mode. Native overlay skipped.");
#endif
        }

        public void InitializeTransparentOverlay()
        {
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            if (_hWnd != IntPtr.Zero) return;
            using var process = System.Diagnostics.Process.GetCurrentProcess();
            _hWnd = process.MainWindowHandle;
            if (_hWnd == IntPtr.Zero) _hWnd = GetActiveWindow();
            if (_hWnd == IntPtr.Zero)
            {
                Debug.LogWarning("[WindowPresentation] Unable to acquire active window handle.");
                return;
            }

            _originalStyle = GetWindowLongPtr(_hWnd, GWL_STYLE);
            _originalExStyle = GetWindowLongPtr(_hWnd, GWL_EXSTYLE);

            // Set window borderless popup style
            SetWindowLongPtr(_hWnd, GWL_STYLE, new IntPtr(WS_POPUP | WS_VISIBLE));

            // Set layered and topmost extended style
            IntPtr exStyle = GetWindowLongPtr(_hWnd, GWL_EXSTYLE);
            long newExStyle = exStyle.ToInt64() | WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE;
            SetWindowLongPtr(_hWnd, GWL_EXSTYLE, new IntPtr(newExStyle));

            // Extend frame into client area for full DWM alpha channel transparency
            var margins = new MARGINS { cxLeftWidth = -1, cxRightWidth = -1, cyTopHeight = -1, cyBottomHeight = -1 };
            DwmExtendFrameIntoClientArea(_hWnd, ref margins);

            // Notify OS of frame changes and bring to top
            SetWindowPos(_hWnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED | SWP_NOACTIVATE);

            // Do not subclass Unity's WndProc with a managed delegate: Unity can unload
            // Mono while WM_CLOSE is still on that callback's stack. Poll layout instead.

            Debug.Log("[WindowPresentation] Native overlay configured; visual/input acceptance requires a packaged build.");
#endif
        }

        public void SetWindowBounds(ScreenRect rect)
        {
            if (_hWnd != IntPtr.Zero)
            {
                // Screen.SetResolution can restore Unity's decorated window style after Start.
                // Reassert the borderless client area when applying the final physical bounds.
                SetWindowLongPtr(_hWnd, GWL_STYLE, new IntPtr(WS_POPUP | WS_VISIBLE));
                SetWindowPos(_hWnd, HWND_TOPMOST, rect.X, rect.Y, rect.Width, rect.Height, SWP_FRAMECHANGED | SWP_NOACTIVATE);
            }
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused) CancelNativeGrab();
        }

        private void CancelNativeGrab()
        {
            if (_grab?.IsGrabbed == true)
            {
                _grab.CancelForCaptureLoss();
                ReleaseCapture();
            }
            if (_simplePhysics?.IsActive == true ||
                _simplePhysics?.State == SimplePhysicsState.Held)
                _simplePhysics.CancelToSafeSupport();
            _wasLeftDown = false;
        }

        private void OnDestroy()
        {
            CancelNativeGrab();
            if (_hWnd != IntPtr.Zero)
            {
                SetWindowLongPtr(_hWnd, GWL_STYLE, _originalStyle);
                SetWindowLongPtr(_hWnd, GWL_EXSTYLE, _originalExStyle);
                _hWnd = IntPtr.Zero;
            }
        }
    }
}
