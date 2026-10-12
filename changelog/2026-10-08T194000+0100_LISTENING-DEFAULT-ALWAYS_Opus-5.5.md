# Always-on listening is the default and starts with SORA

Model name: **Opus 5.5**. Checkpoint **2026-10-08 19:40:00 +01:00**, Europe/London. Status:
**implemented and component-tested.** The launch path has not been run live (the owner's SORA is
running and its files are locked). The owner asked: "Could you change the default to always-on".

## Changes

- `VoiceSettings.listening` now defaults to `always`. Settings files without the key, including
  the owner's (saved before listening existed), load as `always`. Settings → Audio → Listening →
  `press` restores hold-to-talk.
- New Core flag `--listen-on-start`, passed by `scripts/start-manual-test.ps1`. That makes it part
  of every owner launch, including the Desktop shortcut and the shell's managed launch.
- `SoraRuntime.start_listening_on_launch()` starts local voice in the background, only when
  Settings allow voice and listening is `always`. A failure shows as the voice error state and
  never blocks startup. Tests and other launches don't pass the flag, so they start no voice
  worker.
- HOW_TO_USE.md: listening is the default and starts with SORA; clicking the blue microphone
  stops it until the next click or restart; turning voice off in Settings stops it starting.

## Verification

- **Fixture/component:** `.\scripts\verify.ps1` gave 1066 passed, 25 skipped and 4 xfailed, with
  exit 0. New test `test_owner_launch_starts_listening_only_when_settings_allow` covers 3 cases.
  The schemas and the panel settings fixture were regenerated.
- **Not run:** a real launch with listening starting automatically. It needs the owner's SORA
  restarted, which I left to the owner.

HOW_TO_USE.md: updated.
