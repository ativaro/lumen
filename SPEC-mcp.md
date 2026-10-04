# Native Lumen tools over MCP

Extend the existing local stdio server without adding a second application engine.
Existing tool names and the `cachyos` OpenCode configuration key remain compatible.

## Contract

- Studio: `lumen_present_files(paths, title)` returns a bounded presentation manifest
  for the calling conversation. Validates up to 100 existing regular local/mounted
  files in the MCP worker; no writes, downloads or global-window activation. The UI
  reads only successful matching tool results, never user text or path heuristics.
  Empty paths clears results; repeated calls refresh edited files. Works with actions
  disabled. Chat history stores the result, providing session isolation and reopening.
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

## Interactive result views

`lumen_present_view(title, blocks, submit_label?)` returns a conversation-local
`lumen.view.v1` result. Types: table, slider, select, toggle, chart, progress, files.
12 blocks, 100 rows/table, 8 columns, 1200 table cells total and 400k serialized text
limit. Numeric values are finite, sliders have valid integer ranges/steps, choices
are enumerated, IDs unique, paths are explicit regular local/mounted files.
No model-supplied code or URLs. The tool runs with write actions disabled.

Only successful tool results render. Edits stay local until the user submits; submission
is a normal backend prompt with visible human summary and a synthetic structured data
part. Existing modes, tool permissions and task tracking apply. Repeated polls preserve
edits; new results reset them; recovery never replays submissions. Both Studio and Search
use the same renderer and controller. Search also exposes file-presentation results as
file cards; Studio keeps its image/PDF preview. Tests cover actual Qt interactions,
malformed input, numeric sorting, selection, safe export, session isolation and recovery.

### Lumen System

`lumen_system_snapshot` is read-only with an empty argument schema. It samples a
short CPU/network interval and optional local sensors, returning timestamps,
nullable CPU/GPU/RAM/root-storage values and up to twelve current-user processes.
It collects no argv/environment, retains no history, and does not alter the
system or open a window. Process names are untrusted data. Missing measurements
are not health verdicts; overall CPU and per-core process CPU have different scales.
