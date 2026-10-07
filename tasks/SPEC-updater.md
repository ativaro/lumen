# Lumen Updater

A native, theme-aware app reachable from Lumen Apps and Settings. A read-only
check fetches the private main branch into an updater-owned checkout and presents
installed components, the candidate revision and recent commit subjects. Apply
uses exactly the checked revision and the existing installers. No model prompts,
credentials or personal data are uploaded. No task, app or desktop is force-closed.

Default scope: installed Lumen bundles (user and system), panels/themes/launchers,
managed Qt/OpenCode, dictation and installed voices/models, image search, Inbox
calendar runtime, backup runtime, and the native Vault only if already installed.
Only Lumen-pinned dependency versions are applied, never arbitrary latest pip or
OpenCode releases. System packages and Flatpaks are separate opt-in choices.

Git authentication is reused; absent access reports an actionable failure. A
changed/dirty updater checkout is refused. Check and apply share one cross-process
lock. Package transactions cannot be cancelled by closing the UI. Each component
reports its result; successful components are retained on retry, and any failure
keeps the overall result unsuccessful. New components remain opt-in via setup.

Verification: synthetic Git update check/apply contract, invalid/stale plans and
failed installations, private data preservation, optional-component discovery,
no installation during check, native UI controls and existing installer/catalogue
regressions. Smoke-test read-only check against real private main and render UI.
