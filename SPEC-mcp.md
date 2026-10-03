# Native Lumen tools over MCP

Extend the existing local stdio server without adding a second application engine.
Existing tool names and the `cachyos` OpenCode configuration key remain compatible.

## Contract

- Files: list libraries/sources and search names in a selected configured source,
  preserving source labels. Network connections use KDE authentication and KIO-FUSE.
  Search is bounded and runs outside the server process. File writes continue through
  the existing visible, unapproved `lumen_propose_task` workflow.
- Wissen: search/read only explicitly shared notebook entries while memory usage is
  enabled. Links resolve only against shared entries. Memory context reuses the same
  project scope, forgetting and enablement rules as conversations. Explicit remembering
  is an optional action; MCP cannot change privacy rules or enable learning.
- Tasks: paginated status summaries and bounded details/events/results; no implicit
  approval, execution or recovery of running tasks.
- Settings: allowlisted preferences, designs, feature enablement and native desktop
  state. Optional preference/theme/shortcut updates reuse native conflict checks and
  history. No arbitrary config keys, shell commands or credentials.
- Vault: cached plan/status metadata only, clearly distinguished from a live repository
  check. Inbox: bounded local message/calendar cache queries, separately enabled in
  native settings, default off. No network sync, sending or calendar mutation.
- Write tools require existing `LUMEN_MCP_ACTIONS=1`; read tools cannot turn this on.
  Per-call Inbox and memory permissions are checked afresh. Content is untrusted data.
- Native calls run in bounded child processes using the shared Qt6 interpreter. JSON
  schemas reject invalid arguments before execution. Responses have machine-readable
  data, pagination where applicable, and explicit tool errors. Old diagnostic tools stay.
- Setup points to the shared launcher and preserves existing enabled/environment fields.
  Running engines adopt changes when their MCP connection restarts.

## Validation

Isolated fixtures cover source provenance, unavailable network paths, timeout cleanup,
private/shared/revoked notes, project memory, action gating, settings conflicts/history,
Inbox opt-in, secret/raw-message exclusion, stable pagination, task details, Vault cache
semantics and JSON-RPC stdio recovery. No real emails, backups, themes or files modified
by tests. Smoke the installed server using an isolated profile.

Protocol reference: https://modelcontextprotocol.io/specification/2025-06-18/server/tools

## Acceptance (2026-10-04)

- 16 MCP regression checks passed, including real stdio exchanges, preserved setup
  configuration, write gating, shared/revoked notes, explicit memory, native settings
  history, cached Inbox/Vault access and process-group timeout cleanup.
- Full isolated regression run: 363 cases, five optional Restic/CalDAV skips. The only
  failing case required an absent desktop D-Bus environment; rerunning that real WebDAV
  navigation/preview/transfer case with the actual session bus passed. All other cases
  passed with the selected Qt6 interpreter available to child installers/launchers.
- German and English Settings/MCP renders checked; syntax and diff checks clean.
- Installed user launcher: initialize, 23 default tools and native settings retrieval
  passed in an isolated profile. Optional action configuration exposes 32 tools.
- Synthetic evaluation questions are provided under tests/mcp; no cloud/model-based
  evaluation or transmission of personal data was performed.
