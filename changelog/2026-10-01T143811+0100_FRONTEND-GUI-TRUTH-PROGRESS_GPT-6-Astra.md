# Frontend GUI truth — progress

Model: **GPT-6 Astra**. Repair slice implemented/checked **2026-10-01 14:38:11 +01:00**.
Status: **W6a in progress; overall frontend goal active**.

Changes: canonical conversation/model state in runtime and API; separate renderer state; shared readable assistant transcript projection; truthful client model/status labels; full-app busy controls/footer; Send draft preservation; attachment/composer/reference/hint layout repairs. Added C#/API regressions and repaired three pre-existing provider-test typing errors.

Files: src/sora/runtime/service.py, src/sora/api/routes.py; clients/desktop_widget/WidgetCore.cs and WidgetForm.cs; clients/desktop_app/FullAppForm.cs; clients/csharp_tests/WidgetTests.cs; tests/api/test_companion_projections.py; tests/providers/test_antigravity.py and test_local_file_and_desktop_dialogue.py.

Added the full frontend goal tracker and incorporated the owner's agent/model roster and passive-awareness requirements into the alignment plan. This does not mark those capabilities implemented.

Verification: repository **471 passed/13 skipped**, browser **7**, C# **36**, final targeted API/settings **5**; both client builds clean. Computer Use checked the actual rebuilt full-app/widget chat, model labels and compact/expanded layout using an isolated offline Core. See [full evidence and limits](../docs/verification/FRONTEND_GUI_TRUTH_GPT-6-Astra_2026-10-01.md).

No owner runtime restart, paid model test, commit, or claim of whole-system completion. Further W1–W6 work remains in the active goal.
