# SORA documentation map

Every document is kept; nothing is deleted. Each file has one of three roles, and the role
decides how you may edit it.

| Role | Meaning | Rule |
|---|---|---|
| **Living** | Describes the current state or the work still to do | Update in place; keep it short and current |
| **Record** | Dated evidence, contracts or decisions made by a named contributor | Never rewrite. Add a new dated record instead; fixing a broken link path is allowed |
| **History** | Earlier versions or logs moved out of a living document | Read-only, apart from appending to the logs named below |

## Where to start

1. [VISION.md](../VISION.md) (**living, owner-approved**) is the top authority. Every plan serves
   it, and conflicts go to the owner.
2. [V1.md](../V1.md) (**living**) is the current milestone and its acceptance test.
   [plans/V1_REALIGNMENT_2026-10-05.md](plans/V1_REALIGNMENT_2026-10-05.md) labels every open task
   as V1, after V1 or long term.
3. [SORA_GUI_IMPLEMENTATION_ROADMAP.md](../SORA_GUI_IMPLEMENTATION_ROADMAP.md) (**living**) holds
   the GUI stages. Read its §4.0 status table, then §12 for the stage you are working on.
4. [SORA_IMPLEMENTATION_PLAN.md](../SORA_IMPLEMENTATION_PLAN.md) (**living**) holds the
   architecture invariants (§2), contracts (§4), the P00–P15 checklist (§5) and risks (§8).
5. [SORA_OVERVIEW.md](../SORA_OVERVIEW.md) (**record**) is the original specification, verbatim.
   "Ava" in it means SORA. Where it differs from VISION.md, for example its hosted fast dialogue
   model, the vision wins.
6. [GUI design and concept images](gui/reference/README.md) (**record**) are the owner's approved
   visual baseline for Chat, Automations, Memory and Settings.

## Folders

| Folder | Role | Contents |
|---|---|---|
| [`gui/`](gui/) | Record | GUI stage contracts and baselines by GPT-6.1 Sol (`GUI<stage>_<TOPIC>_<model>_<date>.md`) |
| [`gui/reference/`](gui/reference/README.md) | Record | Original concept images (`02-chat.jpg` … `05-settings.jpg`), design document v0.1 and byte/hash manifest |
| [`gui/ROADMAP_CHECKPOINTS.md`](gui/ROADMAP_CHECKPOINTS.md) | History, append-only | Roadmap §4.3–§4.33 dated checkpoints, original numbering. Add new checkpoints at the end (§4.34 onward) |
| [`gui/ROADMAP_REVISION_HISTORY.md`](gui/ROADMAP_REVISION_HISTORY.md) | History, append-only | Roadmap revision entries, newest first |
| [`adr/`](adr/) | Record | Architecture decision records 0001–0012 |
| [`plans/`](plans/) | Living or record | Focused plans: vision alignment, native perception, motion, settings, memory/changelogs, earlier GUI draft |
| [`plans/archive/`](plans/archive/README.md) | History | Earlier implementation-plan snapshots and dated updates, plus superseded originals |
| [`runbooks/`](runbooks/) | Living | How to run, configure, back up, install and update SORA |
| [`verification/`](verification/README.md) | Record | Dated evidence per phase/stage, the owner's manual acceptance checklist and the independent-verification ledger |
| [`history/`](history/) | History | [Previous README](history/README_PHASE_HISTORY_2026-10-03.md) (phase-by-phase summaries P03–P15.8) and the [plan's dated progress log](history/IMPLEMENTATION_PLAN_PROGRESS_LOG.md) |

Also outside `docs/`: [`changelog/`](../changelog/README.md) (record, one file per change),
[`contracts/`](../contracts/README.md) (versioned schemas) and [`identity/`](../identity/)
(SORA's persona files).

## Naming

- Evidence and changelogs carry the contributing model's name and a timestamp, e.g.
  `GUI4_AUTOMATION_MANUAL_GPT-6.1-Sol_2026-10-04.md` and
  `changelog/2026-10-04T134405+0100_GUI4-AUTOMATION-MANUAL-PROGRESS_GPT-6.1-Sol.md`.
- Phase IDs (`P00`–`P15.12`) come from the implementation plan; GUI IDs (`GUI-0a`–`GUI-6d`)
  from the roadmap; `W1`–`W6` from the [vision-alignment plan](plans/VISION-ALIGNMENT_2026-10-01.md).
  Never renumber them.

## Keeping it maintainable

- A living document states the **current** position once. Dated narratives go to a log or
  record, not into another "historical handoff" section of the living document.
- Every claim of progress links its evidence and labels it as fixture, component, native,
  live-model, provider or hardware evidence. A green suite is not acceptance.
- Moving a file is allowed only when every link in the living documents is updated and the
  move is listed in the folder's README (see [plans/archive](plans/archive/README.md)).
