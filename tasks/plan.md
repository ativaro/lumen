# Lumen implementation

The user approved the eight capabilities discussed in chat and the Lumen rename.
Contract and acceptance criteria: [SPEC-lumen-os.md](../SPEC-lumen-os.md).

Build identity/migration, validated actions, durable tasks, knowledge, workflows,
model/context controls, then integrate the native pages. Keep each layer runnable
and test its user-visible behavior before proceeding. Independent reproduction
tests and a separate final review follow the testing/review skills.

Task tracking: [todo.md](todo.md). No external tracker.

Risks: a persisted task must not duplicate already executed operations; external
file changes must block undo; path authorization must survive symlink changes;
model routing must fail closed in local-only mode; package replacement must not
erase state or change service preferences. UI remains responsive during I/O.
