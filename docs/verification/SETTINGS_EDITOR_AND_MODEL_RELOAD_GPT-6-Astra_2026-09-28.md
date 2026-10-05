# Settings editor and model reload — verification

Final verification checkpoint: **2026-09-28 18:24:55 +01:00 (Europe/London)**.
Attribution label requested by owner: **GPT-6 Astra**.
Status: **implemented and verified within the bounds below**.

## Automated gates

- `scripts/verify.ps1`: **388 passed, 12 skipped**, 56.11 seconds. Ruff, strict mypy (199 source
  files), generated-contract freshness, compileall and **7 PWA tests** passed. Skips remain explicit
  native/Unity/hardware opt-ins, not silent passes.
- Desktop app and widget default-output builds: **0 warnings / 0 errors**.
- `dotnet test clients/csharp_tests/csharp_tests.csproj`: **34 passed**. Includes legacy/unified
  projection parsing; a default JsonElement serialization regression was found and fixed.
- Both launcher scripts parsed successfully. `scripts/start-manual-test.ps1` was then run against
  the QA state with the existing merged JSON and `-NoAvatar`; it built the clients/helper, selected
  GUI-managed settings, and brought the authenticated API/model up. No LM Studio probe was needed
  in this existing-store branch. It reused an existing owned fixture Git base; no commit was created.

Coverage added: every stored preference has a control/tier; immediate/next-boot edits do not create
false model pending; reload excludes boot-only edits; reverting values clears pending; revision and
external-file conflicts; malformed-file backup/repair; legacy migration preserves originals and
occurs once; missing model leaves Settings available; failed reload restores previous model; failed
rollback leaves a truthful down state; reload rejects concurrent edits/new dialogue; active turns
drain; cancelled load closes its child; command validation and projector discovery.

## Native full-app checks (Computer Use)

Isolated state: `.local/settings-qa-20260928`; API: loopback port 18773. No normal owner settings
were edited. Built QA client first, then checked the final default-output desktop build.

1. Opened Settings and inspected source/path/performance/cache/speculation/runtime controls.
2. Edited **Context length** 8192 → 4096 and clicked **Save settings**. One model change pending;
   no boot change pending. Clicked **Reload model**, confirmed, and observed ready with pending cleared.
3. Inspected the real child command line: explicit projector remained present and `--ctx-size 4096`.
4. Edited **Dialogue timeout** 90 → 85 and saved. Revision advanced but model revision did not;
   `model_reload_required=false`, `restart_required=false`, active timeout 85.
5. Restarted QA Core and client. Saved 4096 context / 85 timeout survived; boot/model revisions
   converged to the saved revision. Final GUI displayed timeout 85.0 and context 4096.
6. Initial native observation caught clipped action/Browse buttons. Reworked sizing/scrolling,
   used compact picker buttons with tooltips, and re-inspected the final build. Controls are scrollable;
   actions remain available. Multi-monitor/DPI acceptance remains a separate owner check.
7. Final GGUF picker opened in the installed model folder with the current file populated. Confirming
   selection returned to Settings with the matching `mmproj-F16.gguf` and explicit selection feedback.

The UI automation helper had stale modal element/geometry errors during an earlier picker attempt;
that attempt was not counted as a successful selection. The later final-build keyboard confirmation
and Core-backed discovery succeeded.

## Live reload / image inference

`SORA_TEST_LLAMA_CONFIG=.local/llama-server.json` with
`uv run --locked pytest tests/runtime/test_app_settings.py -k live_settings_reload -s -q`:
**1 passed in 23.27 seconds**.

The test started the real server, saved context 4096 / flash attention on / q8_0 K and V caches through
Core, received HTTP 202 for reload, waited for completion, verified the model API key rotated and the
old key returned 401, then sent neutral-filename red and blue PNG fixtures through SORA's actual
dialogue API. Responses: **Red**, **Blue**. No rollback was used; model pending cleared; no generated
key appeared in settings. The test cleaned up its API, runtime and model process.

## Live MTP check

The picker exposed an existing adjacent `mtp-gemma-4-E2B-it.gguf`. A bounded QA-only API edit selected
`draft-mtp` and this file, then reloaded revision 3. Result: ready, model revision 3, no rollback.
The inspected child command included `--spec-type draft-mtp`, the exact draft path, draft cache/GPU
flags and token bounds. A dialogue request returned **MTP dialogue works**.

The backend log showed the draft being loaded and **158 accepted / 222 generated draft tokens**
(acceptance 0.71171, mean length 3.14). A non-fatal draft-memory-estimation warning preceded successful
load/generation; no blanket memory-estimation correctness claim is made. This demonstrates active MTP,
not measured speedup or response-quality equivalence. No compatible DFlash execution was attempted.

## Acceptance limits

- No DFlash, multi-GPU, MoE, every cache type, arbitrary model pairing or acceleration benchmark claim.
- No repeat of Unity/phone/full-desktop vision/action gates; this follow-on does not close four-surface
  parity or unrelated roadmap gates.
- Boot-only settings still require restarting Core. Widget shows state but does not edit settings.
- Permission/credential/identity storage and client placement preferences remain separate.
- Owner's regular state/config was left for automatic migration on next normal start. All QA processes
  are stopped during cleanup; retained QA state/logs are local evidence, not the user's default config.
