# One-command local SORA launch — GPT-6

Model name: GPT-6

Status: **complete at 2026-09-26 17:54:03 +01:00 (Europe/London)** for the local launcher.

- Added root-level `Start-SORA.ps1`. One command starts the existing build-and-Core workflow in a visible PowerShell window, waits for authenticated API readiness, then opens the full desktop client. It supports alternate ports, widget/browser clients and an optional LM Studio dialogue model.
- Reused the isolated, persistent `.local/manual-test` state and existing owner-token workflow. The launcher refuses an occupied port and does not print the token.
- Updated the local tryout guide and README with the single-command path while retaining the separate scripts for troubleshooting and multiple-client use.
- Verified PowerShell parsing and ran the launcher on port 18765: Core listened on loopback and the full desktop app had a responsive window. Stopped the temporary test processes afterward; retained the test state.

This launcher is a developer/manual-test workflow, not a packaged installer or proof of live vision-model inference.
