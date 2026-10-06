[CmdletBinding()]
param(
    # Window title of the panel to capture, as SoraShell sets it.
    [string]$Title = "SORA · Chat",
    # Concept image to place beside it for review (docs/gui/reference).
    [string]$Concept = "02-chat.jpg",
    [string]$OutputRoot
)

# Captures a web panel exactly as it appears on screen, including the blurred desktop behind
# it (PrintWindow cannot see DWM's backdrop), and copies the matching concept image next to it
# so the two can be compared side by side. Windows PowerShell 5.1 compatible. Nothing is uploaded.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $projectRoot ".local/panels-review" }
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class SoraCaptureNative {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out Rect rect, int size);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][SoraCaptureNative]::SetProcessDPIAware()
$window = [SoraCaptureNative]::FindWindow($null, $Title)
if ($window -eq [IntPtr]::Zero) { throw "No open window titled '$Title'. Open the panel first." }
[void][SoraCaptureNative]::SetForegroundWindow($window)
Start-Sleep -Milliseconds 400
$rect = New-Object SoraCaptureNative+Rect
# DWMWA_EXTENDED_FRAME_BOUNDS (9): the visible window, without the invisible resize border.
[void][SoraCaptureNative]::DwmGetWindowAttribute($window, 9, [ref]$rect, 16)
$width = $rect.Right - $rect.Left; $height = $rect.Bottom - $rect.Top
# A margin of desktop around the window shows how the glass sits on it.
$margin = 40
$bitmap = New-Object System.Drawing.Bitmap ($width + 2 * $margin), ($height + 2 * $margin)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Left - $margin, $rect.Top - $margin, 0, 0, $bitmap.Size)
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$name = ($Title -replace '[^A-Za-z0-9]+', '-').Trim('-').ToLowerInvariant()
$shot = Join-Path $OutputRoot "$name-$stamp.png"
$bitmap.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose(); $bitmap.Dispose()
$conceptSource = Join-Path $projectRoot "docs/gui/reference/$Concept"
if (Test-Path -LiteralPath $conceptSource) {
    Copy-Item -LiteralPath $conceptSource -Destination (Join-Path $OutputRoot "$name-$stamp-concept$([IO.Path]::GetExtension($Concept))")
}
Write-Host "Saved $shot ($width x $height at the screen's scale) beside the concept $Concept."
