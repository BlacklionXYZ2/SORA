# SORA bounded Windows capture helper

This helper performs exactly one requested capture and exits. `region` uses a DPI-aware GDI screen copy of the exact rectangle (with `output_max_edge`, the rectangle may span every monitor and is scaled down so its longest edge fits; the reply then gives `image_width` and `image_height`); `window` uses `PrintWindow(PW_RENDERFULLCONTENT)` against an existing Core-scoped desktop target. It writes one JSON reply containing an in-memory PNG and never writes captured pixels to disk.

Core owns authorization, topology checks, TTL/capacity/byte retention, timeout, cancellation, protocol validation, and helper termination. The helper validates process start identity for window capture and rejects elevated, hidden, minimized, mismatched, oversized, or unavailable targets.
