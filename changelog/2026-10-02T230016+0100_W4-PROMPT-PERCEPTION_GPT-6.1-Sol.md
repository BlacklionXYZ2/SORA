# W4 passive prompt perception — GPT-6.1 Sol

Implementation/verification slice completed **2026-10-02 23:00:16 +01:00** (Europe/London).
Status: **implemented; native/model and selected-text GUI checks verified**.
Passive perception, W4 and the overall frontend goal remain **in progress**.

## Changes implemented

- Added version 4 unified settings for native-only/image-on-prompt mode, automatic-perception
  pause and independent window/Desktop metadata additions. All four controls apply immediately
  and appear directly after Companion access in the Settings GUI.
- Migrated valid version 2/3 stores with unique original-file backups. Version 4 requires complete
  access/perception flags; malformed refresh retains the prior active preferences. Updated the
  shipped example and contract schemas. Older edit versions remain accepted.
- Seeded bounded native inventory and Desktop file metadata before the local model's read-tool
  decision, without automatically reading every window or file. Explicit tools remain available
  when automatic perception is paused; remote requests do not inherit owner-local additions.
- Added transient prompt-time window images using the recent application's PID/HWND/start identity.
  No whole-display fallback, focus change or insertion into the desktop frame store. Validated
  helper result, identity, timestamp, byte/pixel budgets and PNG dimensions.
- Rechecked policy/settings generation around capture and response delivery. Pause stops the
  foreground watcher; changed policy or invalidated foreground discards automatic evidence.
  Images never become action authority. Attachments/explicit images take precedence.
- Removed redundant per-look capture approval dialogs from both Windows clients. Core's static
  capture switch remains authoritative; unrelated consequential-action confirmations remain.
- Preserved the actual GGUF display name when live settings recreate the dialogue provider.
- Compacted Settings status by omitting empty warning/error lines; replaced the untested image
  readiness claim with configuration wording that requires an actual model test.
- Added mode/pause/migration/revocation tests and an opt-in actual native-window image/local-model
  test. Updated Settings, local tryout and motion runbooks and the acceptance tracker.

## Verification

- Full regression before final status/example polish: **528 passed, 16 opt-in skipped**, 67.97s;
  **7 PWA checks**; Ruff, mypy 226 source files, contract freshness and compile checks passed.
- After final changes: focused settings/policy/perception **31 passed, 2 opt-in skipped**;
  final perception-only **7 passed, 1 opt-in skipped**; Ruff, targeted mypy and schema freshness
  passed. **36 C# tests passed**; full-app build: zero warnings/errors.
- GUI local Gemma 4 E2B: switched from selected fixture to SORA, sent unnamed prior-application
  question, and read correct `bef` answer with fresh native inventory/selection evidence. This
  closes that specific prior GUI rerun gate. Settings showed the new controls/Immediate badges.
  No access/privacy switch was manipulated through Computer Use.
- Actual native window capture + local model/projector: **1 passed in 8.01s**; answered `before`
  from the fixture image in **2.84s**, with zero clicks/text changes. Component test, not automatic
  image-mode GUI acceptance or a general performance benchmark.
- Compact-status rebuild passed; the second GUI launch was rejected by execution policy, so no
  post-polish screenshot is claimed. Earlier Settings/Chat GUI evidence remains valid.
- Owned QA app/fixture/Core stopped and ports 18784/18785 cleared. QA state/logs retained; no
  personal SORA settings/history edited and no paid provider used.

## Remaining work

Adaptive/interval scheduling, conversation-priority inference, complete lock/in-flight cancellation,
image-on-prompt GUI acceptance, widget/real-editor coverage, and remaining W1/W2/W3/W5/W6 gates.
No broad phase or goal completion.

[Detailed evidence](../docs/verification/W4_PROMPT_PERCEPTION_GPT-6-Astra_2026-10-02.md).
