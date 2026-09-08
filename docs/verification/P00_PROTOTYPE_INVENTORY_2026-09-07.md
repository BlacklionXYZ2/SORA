# P00 prototype inventory and reuse/gap map

- Inspection date: 2026-09-07 (Europe/London)
- Source: `C:\Users\oscar\Desktop\agent-workspace\Hermes`
- Destination at inspection: two planning Markdown files and an empty `changelog` directory
- Source control: neither source nor destination was a Git repository at initial inspection

## Discovered prototype

The source is a 28-file local Python prototype (excluding Git metadata, virtual environments, and
`node_modules`; caches and bytecode account for several files). Seventeen non-cache files were
selected for backup. Its declared package is
`ava-runtime` 0.1.0 with Python `>=3.11`, no runtime dependencies, and optional pytest tooling.

Documented entry points are `python -m ava` and the `ava` console script. Default dialogue and
reasoning providers are deterministic offline mocks. Setting `AVA_REASONING_PROVIDER=hermes`
selects an unversioned CLI invocation of `hermes -z`; `AVA_HERMES_COMMAND` overrides the executable.
The installed CLI reported Hermes Agent 0.21.0 (2026.8.31), Python 3.11.16, and an available update.
That version observation is inventory evidence, not P04 interface validation.

The prototype contains:

- `ava/`: dataclass records, SQLite storage, context compilation, mock/Hermes providers, async
  orchestration, and CLI entry point.
- `tests/`: three files covering context labels, persistence/revision behavior, task updates, stale
  result rejection, and non-blocking mock delegation.
- `identity/`: `persona.md` and `behaviour.md`; three identity files required by the SORA design are
  absent.
- `data/ava.db`: private mutable SQLite state; inspected structurally without recording row content.
- `.env.example` and `.gitignore`; no lock file, bootstrap script, verification script, migrations,
  API, Windows bridge, Unity client, or web client.

The prototype is not a Git working tree, so no commit, branch, or dirty-state comparison exists. A
fresh editable install currently fails because setuptools discovers `ava`, `data`, and `identity` as
multiple top-level packages. The six tests pass when their declared test dependencies are installed
and the source root is supplied explicitly through `PYTHONPATH`. These are separate baseline facts:
the observed tests pass, but the source does not satisfy its documented fresh-install workflow.

## Reuse and gap map

| Prototype element | Disposition | Evidence / gap |
|---|---|---|
| Async dialogue versus reasoning split | Reuse concept after contract tests | Demonstrates non-blocking mock delegation, but lacks scheduler leases, cancellation, retry, and recovery. |
| SQLite store and revision counter | Reference implementation only | Useful baseline; schema has no migration versioning, foreign keys, owner/project/session/run separation, outbox, or entity-level conflict checks. |
| Stale-result rejection | Reuse behavior, redesign contract | Protects all changes with one global revision; SORA requires entity preconditions and independent safe appends. |
| Context labels | Reuse fixture ideas | Context is unbounded string concatenation and has no manifest, scope, token budget, provenance records, or injection boundary enforcement. |
| Provider interfaces and mocks | Reuse test seam | Interfaces lack capabilities, sessions, normalized events/errors, deadlines, grants, cancellation, and result validation. |
| Hermes CLI adapter | Do not migrate as verified integration | Uses `hermes -z` and JSON parsing without a supported-interface probe, timeout, cancellation, output bound, or schema validation. P04 must verify it independently. |
| Identity files | Preserve as legacy inputs | Only two of five required files exist and they use the placeholder name. P02 must import through a recorded identity revision. |
| SQLite data | Preserve; do not edit in place | Private state exists. P00 creates a hashed ignored backup; P02 must build a tested importer and rollback. |
| Tests | Reuse scenarios, not historical results | Tests were re-run from a fresh environment for P00; future contracts require broader negative and concurrency coverage. |

## Naming map

| Legacy input | New canonical name | P00 treatment |
|---|---|---|
| Product/persona `Ava` | `SORA` | New code/text use SORA; preserved legacy text is not rewritten. |
| Python package `ava` | `sora` | New scaffold uses `src/sora`; importer/alias policy remains explicit. |
| Command `ava` | `sora` | New console command is `sora`; no silent replacement of an installed legacy command. |
| `AVA_*` variables | `SORA_*` | Future settings use SORA names; compatibility is deferred and must warn/deprecate. |
| `data/ava.db` and schema identifiers | Versioned SORA store | Original is archived byte-for-byte and remains migration input only. |

## Limitations

This inventory establishes what is present locally and what the prototype tests demonstrate. It does
not prove a supported Hermes integration, production-safe persistence, complete security controls,
live provider behavior, or compatibility with future SORA contracts.
