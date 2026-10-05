# SORA Windows install, update, rollback and uninstall

P15.3 packages SORA as a versioned portable Windows bundle. Installation does not require a
pre-existing Python, .NET or Unity runtime: the bundle contains CPython 3.12.10, the locked Core
wheel/dependencies, self-contained .NET 10 Windows helpers and a Unity Windows player. The archive
is currently unsigned; inspect its recorded SHA-256 and source provenance before use.

## Build a release

From a source checkout with `uv`, .NET 10 SDK and Unity 6000.6.0f1 installed:

```powershell
.\scripts\build-release.ps1 -ReleaseId sora-2026.09.22-p15.3
```

The default build runs the Unity PlayMode suite and creates a fresh Windows player. It also publishes
the four one-shot Windows helpers as self-contained `win-x64` single-file applications, builds the
Core wheel, installs the locked runtime into a portable CPython distribution, hashes every shipped
file, verifies the manifest and writes both a directory and ZIP under `.local/releases`.

`-SkipUnityBuild` is only for debugging the Core packaging path. Its manifest says Unity was omitted
and it is not P15.3 acceptance evidence.

## Integrity and layout

`release-manifest.json` records the exact file set, byte counts and SHA-256 hashes. Install and update
verify it before copying anything. Links/reparse points, traversal paths, duplicate entries, missing
files, unexpected files and modified bytes are rejected.

The installed layout deliberately separates replaceable software from personal state:

```text
%LOCALAPPDATA%\SORA\app\
  current.json                 atomic active release/state pointer
  history.json                 rollback stack
  bin\sora.ps1                 stable launcher
  bin\sora-ops.ps1             backup/restore/verification launcher
  bin\sora-widget.ps1          companion widget launcher
  bin\sora-desktop.ps1         full application launcher
  bin\uninstall.ps1            copies its maintenance runtime before removal
  versions\<release-id>\       portable Core/helpers/Unity/resources

%LOCALAPPDATA%\SORA\state\
  .sora-state.json             destructive-operation containment marker
  private\                     local token/certificate configuration; never backed up implicitly
  slots\<state-id>\            versioned canonical database and registered artifacts
  backups\                     pre-upgrade integrity-checked snapshots
```

The active release and state slot always move together. Update never migrates the active slot in
place: it backs it up, restores a new slot, runs the new bundled Core's migrations and SQLite
integrity checks, and only then atomically replaces `current.json`. Failed migration leaves the old
pointer active. Rollback restores the previous release/state pair without trying to downgrade a
newer database.

## Clean per-user install

Extract the ZIP to a temporary directory and run:

```powershell
.\install.ps1
```

No administrator permission or system-wide registry change is required. Defaults are
`%LOCALAPPDATA%\SORA\app` and `%LOCALAPPDATA%\SORA\state`. Custom contained locations may be supplied
with `-InstallRoot` and `-StateRoot`.

Start Core locally with:

```powershell
& "$env:LOCALAPPDATA\SORA\app\bin\sora.ps1" --serve `
  --api-token-file "$env:LOCALAPPDATA\SORA\state\private\sora-api-token"
```

Open `http://127.0.0.1:8765/app`. External Hermes, Codex or Antigravity provider CLIs are not copied,
modified or logged in by the installer; install/configure the selected provider separately and pass
the same explicit provider arguments documented by the normal SORA CLI. Private remote access also
remains opt-in and requires the P15.2 certificate, private address and exact-origin configuration.

To use the P15.6 Windows companion widget after Core is serving, run:

```powershell
& "$env:LOCALAPPDATA\SORA\app\bin\sora-widget.ps1"
```

The widget reads the owner token from the private token file at request time. Its local settings
(anchor, monitor, compact/expanded state, quiet and detail preferences) live in the managed state
root under `widget\settings.json` without a token. Closing its window hides it in the
notification area; use its menu to reopen or exit. The widget talks only to the loopback owner API.

To use the P15.7 full Windows application, run:

```powershell
& "$env:LOCALAPPDATA\SORA\app\bin\sora-desktop.ps1"
```

The app shares Core's canonical conversation, task, extension and capability projections with the
widget/PWA. It offers explicit task steer/cancel and opens only registered content through Core's
configured handler with an existing exact-scope grant. Its local tab/technical-detail preferences
live under `desktop\settings.json`; credentials and grant IDs are not saved there. The Settings
page displays validated Core configuration and permission scopes in redacted read-only form;
provider credentials, content handlers and execution scopes remain Core startup configuration, not
live-editable values in this release. The full app also talks only to the loopback owner API.

## Optional startup

Pass `-EnableStartup` to `install.ps1` to create one per-user Startup-folder command. It contains
paths and the token-file location, not a token. Startup launches the stable `sora.ps1` pointer with a
hidden PowerShell window, loopback API and private token file. The installer never creates a service,
scheduled task, machine-wide autorun or firewall rule. Uninstall removes only the exact startup file
whose contents match the managed installation.

## Backup and restore

Stop Core or otherwise ensure no application process is using the target state before maintenance.
Create an online SQLite/registered-artifact backup with:

```powershell
& "$env:LOCALAPPDATA\SORA\app\bin\sora-ops.ps1" backup `
  --root <active-state-slot> --destination D:\SoraBackups\backup-2026-09-22
```

The backup manifest hashes the canonical database and `.local/artifacts`. Any artifact path with a
`secrets` component is excluded. Restore accepts only a missing or empty destination, rejects unsafe
paths and modified bytes, applies ordered migrations and requires SQLite `quick_check=ok` with no
foreign-key errors:

```powershell
& "$env:LOCALAPPDATA\SORA\app\bin\sora-ops.ps1" restore `
  --backup D:\SoraBackups\backup-2026-09-22 --destination D:\SoraRestore\state-slot
```

Use `current.json` to identify the active state slot. Do not manually overwrite an active slot.
Credentials, API tokens, TLS private keys, external-provider configuration, local model caches,
coding worktrees, widget/full-app preferences and arbitrary user files are not silently copied by this backup. Protect and
recover those separately according to their owners' policies.

## Update and rollback

Stop the running Core/player, extract the new verified bundle and run its updater:

```powershell
.\update.ps1
```

After checking the new version, keep the old version/state until the rollback window has elapsed.
To return to the immediately previous pair:

```powershell
.\rollback.ps1
```

Rollback never claims to reverse external provider operations, already performed OS actions or
changes in user-owned coding repositories. It changes only SORA's installed release and managed
canonical-state pointer.

## Uninstall and data deletion

Default uninstall removes the application, launchers and exact optional startup entry but retains
personal state and pre-upgrade backups:

```powershell
.\uninstall.ps1
```

Reinstalling into the same roots detects the retained marker, clones the last active state into a
new verified slot, migrates it and preserves conversations/tasks. Data removal is a separate,
explicit destructive choice:

```powershell
.\uninstall.ps1 -PurgeData
```

Purge succeeds only when both install and state marker files resolve to the exact requested roots.
Backups exported elsewhere, external model/provider caches and user repositories remain outside its
scope and must be removed separately if desired.

## Assets, models and licences

- The build bundles the five canonical SORA identity files and the PWA.
- A normal release bundles the freshly built Unity player, Seed-san VRM and its attribution/license.
- Silero VAD, faster-whisper and Kokoro model files are deliberately not embedded in the Core
  archive. They are large optional local assets and must be provisioned separately using the exact
  versions, sources, licences and SHA-256 values in
  [`P14_VOICE_BENCHMARK_GPT-5.6-Sol_2026-09-18.md`](../verification/P14_VOICE_BENCHMARK_GPT-5.6-Sol_2026-09-18.md).
- User avatars supplied with `SORA_VRM_PATH` remain user-owned files. Keep their attribution and do
  not copy them into a release unless their licence permits redistribution.

## Release verification

Run the clean-profile acceptance against an extracted release directory:

```powershell
.\scripts\verify-release.ps1 -Bundle .local\releases\sora-2026.09.22-p15.3
```

It uses isolated profile roots, installs with the portable runtime, creates a canonical sentinel,
performs a side-by-side state-preserving update, rolls back, uninstalls while retaining data, and
reinstalls to prove retained-state recovery. It never changes the actual user's Startup folder or
normal SORA state.
