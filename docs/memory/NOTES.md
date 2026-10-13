# Lumen Notes and system memory — installed UI, 13 October 2026

User-facing product names are **Lumen Notes** and **Lumen Gedächtnis** (English:
Lumen Memory). Notes contains the user's notebook. Personal learning/memory is
opened through assistant settings. No additional Wissen app or area switch is
offered in Notes. Existing notes, collections, memory and permissions are retained.

Cross-app display text was updated in Projects, Inbox, meetings/radio, file
handoffs, live links, backup/restore, sync dialogs, source review, setup and
notifications. Memory-related explanations point to memory settings, not Notes.
The application launcher is named Lumen Notes. Historical user-authored content
is not rewritten.

56 selected UI/text/catalog files were installed against the current runtime;
414 other runtime files, including concurrent search UI changes, were hash-verified
unchanged. A concurrent translation update was merged without dropping its keys.
The existing learning implementation remains; the new native learner candidate
was not promoted. Running personal windows were not closed or restarted.

Notification source identities remain stable in storage so old mute preferences
and deduplication continue to apply. The displayed source is Lumen Notes. A
regression test checks the display, stable ID and retained mute together.

Verification: 52 focused tests; one additional notification identity/mute test;
actual Qt Notes → memory → Notes with temporary synthetic profiles, first on the
candidate and then the installed modules. No personal data used for tests.
Backup, hash manifest and evidence: `~/.local/state/lumen/notes-naming-20261013/`.

The UI changes take effect when existing apps next start normally. No Git push
or real-iPhone update was performed. The Server production UI is also installed;
its native Skill/MCP learner remains blocked by the recorded Talos boundary.
