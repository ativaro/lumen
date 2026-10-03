# Lumen MCP

OpenCode uses the local `cachyos` MCP server to reach Lumen's native features.
The stable configuration name remains unchanged; `lumen-mcp` selects the same
PySide6/Qt6 runtime as the desktop apps. No extra SDK, HTTP service or port is needed.

Run `~/.local/share/lumen/bin/lumen-setup` for a user installation, then restart the
engine/MCP connection. Setup preserves the server's `enabled`, `environment` and
other custom fields. The installer includes this integration unless `--no-mcp` is set.
Existing running engine connections retain their old tool list until reconnected.

## Tools

| Area | Tools | Access and result |
|---|---|---|
| Files | `lumen_files_locations`, `lumen_files_search` | Libraries and saved network places, source labels, bounded filename search. Network authentication uses KDE. |
| Knowledge | `lumen_knowledge` | Existing indexed, selected document roots, with excerpts and file/page sources. |
| Wissen | `lumen_notes_search`, `lumen_notes_read` | Only shared notebook entries while memory usage is enabled; resolved links exclude private notes. |
| Memory | `lumen_memory_context` | The same enablement, project scope, forgetting and shared-note rules as Lumen conversations. |
| Tasks | `lumen_propose_task`, `lumen_tasks_list`, `lumen_task_get` | Visible unapproved action drafts, progress, results, errors and events. No implicit execution. |
| Settings | `lumen_settings_get` | Allowlisted preferences, speech configuration status, memory/Inbox flags; optional live themes, panels, shortcuts and services. |
| Vault | `lumen_vault_status` | Cached plans and last backup/check timestamps. No repository access, unlock, backup or restore. |
| Inbox | `lumen_inbox_search`, `lumen_inbox_read`, `lumen_calendar_list` | Local synced cache only. No credentials, raw MIME, attachments, sending or live sync. |
| Optional actions | `lumen_settings_set`, `lumen_theme_set`, `lumen_shortcut_set`, `lumen_memory_remember` | Native persistence/history, theme application, shortcut conflict checks, explicit user-requested memory. |

Existing diagnostic and optional desktop action tools remain compatible.
`limit` (1–100, default 30) and `offset` paginate lists. Follow `next_offset` until null.
File search returns a bounded result and source/errors rather than an unstable scan
cursor; narrow the query when limited. Notes/message bodies and task details are
bounded. All retrieved content is data, not instructions.

## Permissions

Inbox/calendar access defaults **off**. Enable **Settings → MCP → Read local messages
and calendar events through MCP** to expose the existing local cache to your configured
AI provider. Disabling access takes effect on the next call. Previously returned
content remains in the engine's conversation; start a new conversation when needed.

Wissen sharing and memory usage remain controlled in Wissen. The MCP tools cannot
share a private note, enable memory, change approval policy or grant themselves Inbox
access. Optional action tools are advertised only when the server environment contains
`LUMEN_MCP_ACTIONS=1`; normal OpenCode tool approvals still apply. Example opt-in:

```json
{
  "mcp": {
    "cachyos": {
      "type": "local",
      "command": ["/absolute/path/to/lumen/bin/lumen-mcp"],
      "environment": {"LUMEN_MCP_ACTIONS": "1"},
      "enabled": true
    }
  }
}
```

Supply the exact current preference value as `expected`. Theme changes use
`lumen_theme_set` with the current `Assistant.appearance`; shortcut changes take KDE's
integer key code and the current `before` list. Privacy and approval keys are never
writable through these tools. Some app preferences take effect when the window reopens.
File modifications still use `lumen_propose_task`, with review and approval in Lumen.

## Example workflows

- List sources, search `Workshop` in the selected NAS source, then use existing indexed
  knowledge excerpts for a summary. Filename search itself does not read document text.
- Search shared notes, read a result and follow its shared links; query memory context
  using the actual working directory. Private notes are not returned.
- Read a task's status and result, page its events and report the actual error without
  restarting it or approving any steps.
- Read preferences, then apply `midnight` with the expected previous appearance. The
  same native theme routine updates Plasma panels and window decoration.
- Read cached Vault timestamps, or search locally synced Inbox messages and read one
  using its account/folder/validity/uid identifiers. Offline caches may be stale.

Calls run in isolated child processes with a 45-second deadline; timed-out process
groups are terminated. Network folders have a 20-second connection deadline. A timeout
of a write is not proof that nothing changed: read current state before retrying.
JSON schemas validate arguments before execution; failures return MCP tool errors.
Structured JSON is also serialized into text for older clients. The server accepts
2024-11-05, 2025-03-26 and 2025-06-18 protocol versions.

Validation: `PYTHONPATH=files QT_QPA_PLATFORM=offscreen lumen-python -m unittest
 test_mcp test_mcp_native test_settings -v` in an isolated test profile. Integration
fixtures never send real email or modify real backups or desktop themes.

Protocol: [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
