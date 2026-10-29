# Avatar: she stands 1 unit (500 physical pixels) tall

Model name: **Opus 5.5**. Checkpoint **2026-10-16 17:25:00 +01:00**, Europe/London. Status:
**built and tested; not yet seen live**.

The owner: "could you make her model slightly bigger? … Maybe like a 30% height increase?",
then "Make her 1 unit tall then". She was 0.6 units (300 physical pixels); she is now 1 unit
(500 physical pixels, as the overlay maps 500 pixels to a unit), on every monitor whatever its
scaling.

## Changes

- `clients/unity/Assets/Scripts/Coordinates/OverlayPlacement.cs`: her size is one pair of
  constants, `AvatarHeightPixels` (500) and `AvatarHalfWidthPixels` (150, up from 90 in the
  same proportion). They are the defaults for the footprint kept clear of taskbars and screen
  edges, so she isn't cut off at her new size.
- `clients/unity/Assets/Scripts/SoraBootstrap.cs`: scales the avatar and her body capsule from
  that constant (the capsule was fixed at 0.6 tall).
- `clients/csharp_tests/WindowsPlacementTests.cs` and
  `clients/unity/Assets/Tests/PlayMode/P16SecondaryPartsTests.cs` (my own test) use the
  constants, so the hair settling test still measures her at SORA's real scale.
- `HOW_TO_USE.md`: her size.

**Unchanged on purpose:** walking and running speeds (300 and 800 px/s, set by Core). On a
taller body the same walk covers fewer body lengths a second, a calmer and more natural pace.
Reach and pointing use her own bone lengths, so they scale by themselves.

## Verification

- C# client tests: 420 passed / 0 failed.
- Unity PlayMode at 60 fps: 79 passed / 0 failed (at about 17:23). At the new scale her tuned
  hair still settles (fastest tip 0.1 mm a frame at life size), and 144 of 146 springs get
  colliders.
- The avatar player was rebuilt in place (SORA and Unity were not running).
- **Not run:** a live look at her new size in the real player; how she sits against windows and
  the taskbar at this size.

Nothing committed.
