# GUI-1a preference migration UTF-8 BOM addendum — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Checkpoint: **2026-10-03 21:04:55 +01:00**, Europe/London. Status: **implemented / preference slice in review; GUI-1a remains in progress**.

- Final migration review identified the existing widget writer's UTF-8 BOM format. Added BOM-aware parsing for UI/legacy preferences while fingerprinting/backing up the entire original byte sequence unchanged.
- Added two regression cases: byte-identical legacy BOM import/backup and reading a valid BOM UI file without recovery or silent replacement. Final C# suite **80 passed**, all three Windows builds **zero warnings/errors**.
- Native QA profile `.local/gui1-preferences-import-20261003`, host PID 50476: recognized BOM import, compact/detail settings reflected, old topmost not applied, quiet/tab provenance honest, retired-monitor/out-of-range placement clamped to a fully reachable Chat. No Core/inference/desktop helper/voice/agent was started.
- Original and backup SHA-256 both **820E2CB5DF67DA2869336FFB8E92F7A34CA4D1F07DE74D26E8085F77005CA9E8**, unchanged after native normal Quit. Final checks show zero QA hosts/listeners and unchanged owner Core PID 52000/start time. The earlier corrupt fixture hash also remains unchanged.
- Earlier fresh full regression remains **686 Python /25 skipped, 8 PWA**; no Python/PWA source changed in this BOM-only C# refinement, so those gates were not rerun a second time. No whole stage is closed, no ordinary-launch change, no owner data change, no force kill/commit/goal-status change.

[Main preference checkpoint](2026-10-03T205519+0100_GUI1-PREFERENCES-PROGRESS_GPT-6.1-Sol.md) · [Evidence/addendum](../docs/verification/GUI1_PREFERENCES_GPT-6.1-Sol_2026-10-03.md).
