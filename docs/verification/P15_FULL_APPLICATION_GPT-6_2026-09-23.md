# P15.7 full application/settings surfaces — GPT-6

Status: **implemented / in review at 2026-09-23 12:38:21 +01:00 (Europe/London)**.
The P15.7 acceptance checkbox remains open for the configuration and parity
gates below; this is not a completion claim.

## Implemented

- Added a self-contained Windows Forms `SoraDesktop` client and stable installed
  `bin/sora-desktop.ps1` launcher. It uses the same loopback owner token and
  canonical Core event/projection path as the P15.6 widget; the token is read
  on every request and not stored in app preferences.
- Chat is conversation-first. Specialist delegation is a separate confirmed
  action; Activity presents canonical tasks, provider provenance, explicit
  steer/cancel with confirmation and a fresh active-state recheck. Technical
  IDs and result IDs are hidden by default and locally collapsible.
- Content lists only live, exact-scope Core `ContentReference` entries. The
  Open/Show/Where buttons send a semantic request through Core with an
  ephemeral existing grant ID. The client does not shell-open paths, treat
  opaque task result IDs as files, or save grant IDs.
- Integrations shows registered extension type/version, declared capabilities,
  required grants, active state and provider availability. Raw extension
  configuration and credential references are not displayed. P15.10 remains
  the separate extension-management gate.
- Settings displays redacted Core provider/worker/context/handler settings,
  configured content/editor roots, and owner-local grant scope metadata.
  Grant and approval IDs are omitted. Only local tab/technical-detail
  preferences are editable; Core configuration is labeled read-only.
- Added owner-local content-reference and permission projections. The remote
  allowlist still excludes both; paired remote clients are tested as denied.
  The one-request Core HTTP response now advertises `Connection: close`, and
  the shared C# client closes each request, preventing stale keep-alive reuse.

## Verification

| Check | Result |
|---|---|
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1` | 346 Python tests passed; 10 explicit opt-in skips. Ruff, strict mypy across 186 source files, schemas, compileall and browser 7/7 passed. |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | 30/30 passed, including full-app projection redaction, exact action construction and convergence with widget state after reconnect. |
| `dotnet build clients/desktop_app/desktop_app.csproj --verbosity quiet` | Zero warnings/errors after final source changes. |
| `uv run --locked ruff check scripts/verify-full-app-content.py scripts/fixtures/full_app_content_handler.py` | Passed. |
| Native Windows UI, isolated deterministic Core | Chat turn and canonical reply rendered. A delegated task appeared in Activity with backend/status, later became completed and appeared in retained history. Integrations and Settings rendered. The Content tab displayed only registered references, not an opaque task result as a file. |
| Configured-handler fixture through packaged r1 app | Selected `content:file:p15-7-qa`, entered an existing exact-scope `desktop.navigate` fixture grant, clicked Open, and saw `configured_handler_launched`. The direct-argv handler recorded the exact fixture path, verb `open` and reference ID; the grant string was absent from persisted desktop preferences. Fixture output: `.local/p15.7-handler-qa/handler-observation.json`. |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1 -ReleaseId sora-p15.7-acceptance-20260923-r2 -ReuseVerifiedUnityBuild` | Built the final self-contained Core/widget/full-app release, reusing the previously verified Unity player rather than claiming a fresh Unity run. |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -Bundle .local/releases/sora-p15.7-acceptance-20260923-r2 -RequireWidget -RequireDesktop` | Passed clean install, update, rollback, data-retaining uninstall and reinstall. Both launchers/executables were present, and widget/full-app preferences survived. Machine record: `.local/p15.3-release-acceptance-e237fa31-d19a-4a6d-a11a-a209939e5e2c/acceptance.json`. |

Final archive: `.local/releases/sora-p15.7-acceptance-20260923-r2.zip`,
421,161,742 bytes, SHA-256
`338ceb1d8ec901e887a918606043b2f6b0fd81c406dde55bb99011d1674ecc52`.
The packaged `SoraDesktop.exe` is 116,136,216 bytes, SHA-256
`4f2147c4a5672ed1767c8e987720ce7b0039a52a411f23e8412192af28a7f04f`.

## Remaining P15.7 acceptance

- The Settings view is redacted and inspectable but does not yet edit the
  broader §4.12 validated configuration (reasoning-provider/routing,
  voice/barge-in, embodiment/proactivity, privacy/storage and credentials).
  These currently live in existing Core startup/client-local configuration;
  adding live mutation without a versioned validation and protected-secret
  boundary would be unsafe. The app must either implement that boundary or
  the plan must explicitly accept a read-only surface before P15.7 closes.
- Shared canonical widget/full-app projections and PWA browser convergence are
  tested, and the packaged avatar's Core transport has prior evidence, but a
  fresh simultaneous four-surface parity exercise has not been run. Do not
  infer pixel/UI parity or live-model quality from the deterministic fixture.
- P15.2 still separately needs a physical paired phone and trusted
  certificate. No commit, tag or staging operation was performed.
