# Source publication — 2026-10-13

147 selected Python/Qt tests passed in a disposable user profile, including bootstrap, localization, Notes/memory, pairing, native Vault/MCP, Studio and app routing. All 24 Plasma QML checks passed. Python source syntax and git whitespace checks passed.

Source candidates were inspected for credential patterns and known local secrets.
Matches were synthetic test fixtures; private account data, runtime environments,
backups, screenshots of personal data and signing material are excluded.

This publication updates private repositories only. It does not promote a server
image, install desktop packages, restart apps or submit a mobile build.
The complete cross-product regression matrix and fresh-system installation were
not rerun. Native learning still requires its separately documented engine/host
qualification; a source commit is not evidence of a deployed native learner.

## Lumen Compose · 2026-10-18

The text assistant is named Lumen Compose in window/catalog/settings/launcher,
inter-app handoffs, setup text and tool descriptions (German and English). Existing
`translate` commands, tool IDs and library/settings keys remain compatible. This
changes authored labels only; existing drafts/results and grants are preserved.

18 current synthetic tests pass in the source, installed-runtime candidate and
against the actual installed modules; DE/EN label smoke checks pass. Two stale
installed app-center fixture failures reproduce with pre-rename modules, and a
context test module is absent from that older installed test set. These legacy
fixture issues are retained separately; current test fixtures were used for the
runtime check. Fourteen selected installed files including the renamed test title
and the user launcher were updated, with 571 other runtime files unchanged and
source-only backups retained. No personal window was closed or used for UI tests.
No real model request or renewed dependency audit was performed for this rename.
