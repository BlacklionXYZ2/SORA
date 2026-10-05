# GUI-1b canonical Chat anchors and file-context verification — progress

Model/contributor **GPT-6.1 Sol**. Checkpoint **2026-10-04 01:03:57 +01:00** (Europe/London). **In progress**, not complete; no completion timestamp.

Added process-local `ChatDocument` measured-span/message-ID mapping and integrated it into native transcript replacement/restyle. Unchanged messages preserve selection identity after bounded history shifts/prepends; corrected/deleted/reordered/ambiguous selections clear rather than select unrelated records. Viewport fallback uses surviving canonical IDs. Append/no-change behavior retained. Added ten anchor cases, including Unicode/native newline boundaries.

Extended fresh `.local` GUI fixture with optional synthetic-file mode and provider-context observation assertion; default permissions unchanged. Actual isolated typed-path HTTP dialogue proved marker delivery to provider context, with marker absent from canonical message content. Added one Python test preventing a blind fixture success claim. No real LLM/private-file read or positive new-binary GUI attachment claim: Computer Use activation failed twice after recovery, so inputs stopped.

Changes: `clients/desktop_shell/{ChatDocument.cs,ChatControls.cs}`, linked C# project and `ChatDocumentTests.cs`, `scripts/verify-gui-shell.py`, `tests/scenarios/test_gui_shell_fixture.py`, root roadmapv1.12, desktop-shell runbook, [combined dated evidence](../docs/verification/GUI1_CHAT_ACTIVITY_GPT-6.1-Sol_2026-10-04.md) and this log. Concurrent GUI-1c source/tests have their [separate log](2026-10-04T010357+0100_GUI1c-ACTIVITY-PROGRESS_GPT-6.1-Sol.md).

Final joint verification: **148 C#**, **704 Python /25 opt-in skipped in85.77s**, **8 PWA**; mypy263/lint/schema/compile and launcher forwarding/AST pass; three zero-warning/error Windows builds. QA processes ended normally, owner Core/reference/overview/history preserved. No canonical migration/default switch/commit.

Native anchor/file/keyboard/IME/physical acceptance and full GUI delivery remain open. Next: finish these checks alongside retained workflow implementation; do not equate component/API evidence with user-side or real-model proof.
