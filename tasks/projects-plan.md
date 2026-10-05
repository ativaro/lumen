# Lumen Projekte implementation

Separate plan to preserve the other sessions' unfinished plans.

- [x] Hierarchy + native project/initiative/manual task flow. Verify migration,
  persistence, dependencies, archive and native selection.
- [x] Material, source links and contextual result actions. Verify incoming and
  outgoing handoffs, moved files and input snapshots.
- [x] Research/analysis and recurring runs. Verify cancellation, failure,
  duplicate prevention, retained results and timer invocation.
- [x] Review, focused and full regression checks, DE/EN native rendering,
  documentation and backed-up installation without restarting user windows.

Order follows the list. Owned tables avoid overwriting existing project JSON;
field-level transactions keep autosave from replacing runner state. Existing
global task workflows remain separate; project runs belong to their task.

## Verification and delivery

Independent review covered run reuse, cancellation, archive inheritance, retained
history, migration/undo, imports during editing and scheduled-claim races.
Eleven focused project tests and eight reference-focus tests pass. Native create
dialogs, persistence and 840×650 / 1320×850 layouts pass in German and English.
The installed OpenCode 1.18.34 accepts the restricted session permissions and
exposes websearch/webfetch; no paid/live model completion was submitted.

Full module-isolated regression: 505 tests, 500 passed, 3 optional skips, 2
failures reproduced on unchanged HEAD 1d3eb42 (cached Vision launcher JSON and
WebDAV connection timeout). A combined-process Qt run was interrupted after
repeated stale-window callbacks; the new Projects timer now stops on close.
The Vault module can still crash at interpreter shutdown after all 18 assertions
pass, as in the previously documented baseline. New fake-engine lifecycle
cleanup was corrected; the 19 project/reference checks pass together.

20 runtime/desktop files installed and byte-compared on 2026-10-05. Private
backup: ~/.local/state/lumen/manual-updates/projects-20261005-104223 (includes
consistent pre-migration workbench SQLite). Installed native dialogs, compact
layout, legacy launcher and the headless empty timer tick pass. No user windows
were restarted and no personal project or schedule was created.
