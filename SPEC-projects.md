# Lumen Projekte

Approved by the user: project structure, with projects → initiatives (Vorhaben) →
tasks. Native three-column UI, contextual actions, documents and notes at every
level. Task kinds: manual, research (including deep research), analysis and
automation. Each task owns its desired result, dependencies, timestamps and run
history. Automations reuse a task and keep individual results.

Keep the `workbench` storage/launcher identity and project IDs so existing links,
backups and imports survive. Add child records and run history to its SQLite
database; migrate old questions idempotently without deleting original content.
Reuse native Qt controls, existing document extraction, AI backend and interop.
No new dependencies, board view, collaboration server or general workflow DSL.

AI runs use explicitly attached context, record input revisions and results, and
are cancellable. Research may use web tools; analysis has no action tools.
Recurring tasks require an explicit enabled schedule and a working user timer.
Interrupted work is visible and is never silently replayed.

Acceptance: create/reopen all three levels; preserve old material and checked
questions; prevent cyclic dependencies and concurrent duplicate runs; inspect
input versions and every result; use Reader/Wissen/Vault contextually; verify
native UI and regressions before updating the installed runtime.


## Agent integration

The `lumen-projects` skill accompanies the read tools with create/update/start
MCP actions. They use the same Library/Projects/Runner as the native UI. Updates
and starts require the revision returned by a preceding read, checked in the
write transaction; archived parents and active runs are refused. Tasks start
as a detached native runner process and return its recorded run ID. Clients read
actual results with `lumen_project_runs` and never infer completion from start.
Project-only permission (`LUMEN_MCP_PROJECT_ACTIONS=1`) does not enable system
settings writes; normal engine tool approval still applies. Tool-driven creation
never attaches files, enables schedules, or fabricates task outcomes. Source and
schedule editing remain in the UI. New entries and clean editor fields refresh
without discarding local drafts.
