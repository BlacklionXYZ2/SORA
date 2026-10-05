# Conversation Stop evidence — GPT-6 Astra

Slice completed: **2026-10-02 23:52:13 +01:00**, Europe/London.
Overall frontend alignment remains active; no workstream is closed by this document.

## Implemented behavior

The Core registry admits each request before asynchronous capture/model work. IDs are optional
for compatibility; clients with Stop generate a new nonce for every request. Local and remote
keys are separate. Terminal IDs are retained in a 256-entry/10-minute transient cache; Stop can
overtake a POST by recording only its exact nonce. This is not a durable retry/idempotency ledger.

Stop is authenticated owner-local and is forbidden to remote sessions. Model/capture/read
awaits are cancelled, and guard checks reject late results even if a provider suppresses
CancelledError. Settings/desktop invalidation stop local precommit work. Dialogue deadline
checks prevent a late result bypassing the normal timeout. Commit starts without an intervening
await after its final guard, then appends the existing atomic user/assistant pair. A Stop at that
point returns `already-finishing`; already dispatched actions are explicitly not undone.

Both Windows clients keep an independent Stop control enabled during dialogue, not during
specialist delegation. They restore an unsent draft only if the composer remains empty; attachments
are retained on cancellation. A new draft entered while an explicit-screen reply is pending is
not cleared on success. The PWA uses the same nonce endpoint only in owner mode, rejects duplicate
submit while pending, and refreshes its app-shell cache version. Remote Stop is deliberately absent.

## Evidence matrix

| Check | Result | Evidence boundary |
|---|---|---|
| Full regression | 546 passed / 18 opt-in skipped, 84.01s; 8 PWA tests; lint/types/schema/compile passed | Opt-in native/Unity/device cases not implied |
| Final targeted checks | 57 passed / 1 skipped, 3.81s | Runtime/provider/read/capture fixtures and authenticated HTTP |
| C# / builds | 37 tests; full app/widget zero warnings/errors | Payload/error-code and build compatibility; final widget rebuilt/reviewed |
| Request races | Before-start Stop, pre-first-instruction cancellation, duplicate/reused ID, local/remote key isolation, stubborn late return, deadline, commit fence, shutdown | Deterministic asynchronous tests |
| HTTP | Anonymous 401; owner Stop 200; request result 409; zero cancelled history; new request 201 | Actual local server transport, fixture model |
| Full-app GUI | Long prompt stopped; draft restored; zero history; ready status; next reply `READY AFTER STOP.` | Actual local Gemma model and Windows client |
| Compact GUI | Second long request stopped; draft restored; no 5000-word prompt/reply persisted | First compact long response finished before Stop; not counted as cancelled |
| Layout | Full-app button row fit at inspected width; final compact Stop/Look/Delegate/Send labels readable | One current monitor/DPI, not mixed-DPI matrix |
| Cleanup | Owned QA Core/model/apps absent; 18784/18785 clear | State retained under isolated `.local/dialogue-cancel-qa-20261003` |

Test model: `gemma-4-E2B-it-IQ4_XS.gguf`, matching `mmproj-F16.gguf`, managed llama.cpp,
context 8192, GPU offload auto, existing local weights. No paid provider, installation or download.
GUI prompts requested fictional prose or an exact recovery string, not desktop effects or memory.
Native-only automatic context remained as configured. No GUI privacy/security control was changed.

The initial broad run failed one older revocation expectation; the targeted run also identified
the matching capture expectation. They now expect the new `DialogueCancelledError` while retaining
their rejection assertions. The first new HTTP test passed behavior checks but used the wrong
cleanup method (`stop`); corrected to `close` and rerun successfully. The PWA source-presence
assertion was updated for the added nonce argument, and a payload/error-code test was added.

## Reproduction

```powershell
./scripts/verify.ps1
dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore
uv run --locked pytest tests/runtime/test_dialogue_turns.py -q
```

For manual GUI acceptance, run an isolated Core with the existing model configuration, open the
full app/widget pointing to that isolated token/port, request a long harmless response and press
Stop while thinking. Confirm draft preservation, no new transcript pair, Ready to talk and a
successful fresh request. Do not re-send a stopped action prompt without checking prior effects.

## Still open

Live explicit-screen cancellation/helper process-drain checks; actual lock/unlock; PWA GUI and
reconnect/session-change races; new-draft/attachment GUI matrices; cancellation-resistant provider
shutdown beyond the bounded drain; mixed DPI; voice shared orchestration; adaptive/image GUI
acceptance; every other requirement in the [active tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md).
