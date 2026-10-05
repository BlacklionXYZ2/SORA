# Windows-native perception implementation plan

Model: **GPT-6 Astra**  
Planning completed: **2026-09-29 08:54:34 +01:00 (Europe/London)**  
Status: **Planning complete; implementation not started.**

## Changes

- Added [the native-perception and read-tools plan](../docs/plans/WINDOWS-NATIVE-PERCEPTION-AND-READ-TOOLS_2026-09-29.md) with seven ordered follow-on stages, dependencies, implementation touchpoints and completion gates.
- Documented the source-inspected gap between existing process-scoped Windows observation/local-file reading and ordinary conversational discovery/tool use, including the normal launcher's missing observation-helper configuration.
- Specified native window metadata, bounded UIA selection/text extraction, actual user/Public Desktop resolution, transient references, directory listing and direct local-file reading before targeted vision fallback.
- Proposed a compact constrained read-tool schema for the configured low-cost model, bounded execution, private-data handling, exact Core-owned authorization and separation from motion/OS actions.
- Included unified GUI Settings, startup/release integration, cancellation, source/status presentation, staged rollout, regression coverage and concrete owner acceptance prompts.
- Preserved historical phase attribution and the baseline overview. No canonical roadmap phase was renumbered or marked complete.

## Verification and scope

- Inspected current bridge, observation contracts, runtime authorization/dialogue entry points, local-file reader, unified settings, startup wiring and existing roadmap/runbook documentation.
- Checked the new plan's local Markdown links and stage/status structure; both local link targets exist and all seven implementation stages remain planned.
- Consulted official Microsoft Known Folder and UI Automation text documentation, linked at the relevant design decisions in the plan.
- Documentation-only task: no application source/configuration changes, app launches, model calls, native acceptance tests or repository test suite runs. Existing dirty-tree work was preserved.

Future implementation stages must record their own actual completion timestamps, evidence and separate model-name-attributed changelogs; this planning timestamp is not implementation evidence.
