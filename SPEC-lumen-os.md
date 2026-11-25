# Lumen: AI-first CachyOS desktop

Approved scope: the user requested all eight proposed capabilities and one product
named **Lumen**, with file management as an integrated page and the separately
launchable **Lumen Files** window. The panel opens the assistant; both entry
points share settings and integrations. OpenCode remains the model/tool engine.
This is an extension of the existing PySide6 application.

## Capability map and build order

| Module | Responsibility | Dependencies |
|---|---|---|
| identity | Lumen package, repository, launchers, migration of old installation | — |
| actions | Validated desktop/file/system actions and reversible change history | identity |
| tasks | Durable task records, pause/resume/cancel, output files and verification | actions |
| knowledge | Explicitly shared folders, source-backed search, editable memories | identity |
| file actions | Personal actions saved from finished tasks, started from the file menu | tasks |
| models | Local/cloud selection, explicit privacy mode and resource budgets | tasks |
| context | Visible file/text/image context, optional local voice input | models |
| desktop | One application with conversation, files, tasks and knowledge | all |

## Observable acceptance criteria

- New packages/paths/repository use `lumen`. Existing settings and reports remain
  available; old package replacement and old launch commands are supported.
- The file manager is available as a page in Lumen and through its own Lumen Files
  launcher. Opening Lumen from the panel activates the assistant.
- Commands exposed as constrained tools never invoke a shell or accept arbitrary
  D-Bus methods. Inputs, target scope and action approval are enforced in code.
- Tasks survive application restarts; running tasks interrupted by shutdown are
  visibly interrupted and can be resumed explicitly. No success without an
  engine completion or verified action result. Cancellation does not claim undo.
- Changes made by native file actions retain preconditions and backups, and undo
  refuses to overwrite subsequent external edits. Non-reversible actions say so.
- Knowledge indexing only traverses selected roots, excludes secrets/hidden paths
  and symlink escapes, searches text/PDF content with file/page citations, and
  supports removal/re-indexing. Memories are editable and deletable.
- Successful tasks can become personal file actions that start only from the
  file menu and show the new selection before every run. The desktop has no
  saved workflows, schedules or directory triggers; automations run on Lumen
  Server. Unattended model operations cannot silently grant new tool permissions.
- Local-only model policy never falls back to a remote endpoint. Explicit model
  selection and optional GPU-load limits apply to background work. Resource and
  request limits stop work with a visible reason.
- Output creation produces real files that can be opened, with a protected output
  directory and previews. Existing engine-based artifact creation remains usable.
- Selected context is visible before sending. Local speech transcription is
  optional, uses configured installed software/model, and never uploads audio
  implicitly. Explanation mode teaches the performed steps on request.

## Implementation and conventions

Use Python stdlib (sqlite3, pathlib, subprocess with argv), existing PySide6 widgets
and OpenCode HTTP API. Keep new modules under `files/` so both installation paths
already include them. Reuse existing search, permission UI, assistant backend,
settings and native file operations. Integrate using direct calls/signals.

Data: private XDG state directory `lumen`, SQLite transactions, explicit schema
version and additive migrations; retain legacy data on conflicts. No secrets in
task exports/logs. Folder authorization is checked again at execution time.

## Verification

`scripts/test-desktop.sh`

Focused tests use temporary directories, isolated settings, a local fake engine
and mocked system mutation boundaries. Test actual persistence, traversal
rejection, interruption, cancellation, undo conflict, scheduling and model policy.
Check shell/Python syntax and build `./packaging/arch/build-package.sh` from a
committed tree. Inspect rendered native windows. Exercise real read-only desktop
actions; do not change unrelated desktop configuration to test writes.

Baseline: 47/48 tests passed before this work; the real WebDAV/KIO integration
test times out. Diagnose and report its environment rather than silently skip it.

## Boundaries

Preserve user's OpenCode credentials and providers, existing desktop choices,
service enable/disable choices and Git history. Model output and retrieved
documents are data, never authorization. No hidden monitoring, automatic model
downloads, invented application integrations, or unconditional root access.
