# Lumen interoperability contract

User approved implementation of the two motivating flows and the numbered 100 examples on 2026-10-03. Source apps retain ownership; transfers preserve provenance. No outbound mail or provider calls are performed by a handoff. Calendar writes are reviewed in the existing editor. Data and automation choices remain explicit.

## Modules and order

| Module | Responsibility | Depends on |
| --- | --- | --- |
| refs | bounded object references, handoff queue, history, tags | existing Library |
| transfers | destination adapters and common transfer UI | refs |
| sources | selected-object extraction and Files actions | transfers |
| backup | application-aware Vault sources and restoration | refs |
| audio | speech identity, routing, interruption coordination | existing audio |
| relations | backlinks, global discovery, project context | refs, sources |

Build complete transfer paths first, then relations, backup and audio. Retain existing native widgets, worker Jobs, SQLite records, Markdown notebooks and single-window activation. No new external dependencies.

## Shared Python interface

`interop_data.py` (root agent):
- `Registry(root=None)`: root is the parent of app Library directories, following LUMEN_TOOLS_DATA.
- `register(ref) -> str`: opaque `lumen://object/<32 hex>` URL. ref keys: app (files, wissen, reader, inbox, meetings, household, workbench, radio, vault, sound), id (existing record key or notebook-relative path), kind (record/note/message/task/event/file/draft), title, path (absolute physical path when applicable), position (dict page/time/note), locator (dict for inbox account/folder/validity/uid or notebook root). Identity excludes display title and position; position encoded in URL query.
- `resolve(url) -> dict`, `link(source_url, target_url, relation='reference')`, `related(url) -> list`, `search(query, limit=60)`, `history(limit=100)`.
- `enqueue(target, action, payload) -> token`, `request(token) -> dict`, `finish(token,result)`. Payload is bounded JSON <= 512 KiB, max 100 paths, max 120000 text characters, local absolute paths. Strict keys; never launch arbitrary executables.

`interop_sources.py` (source adapter):
- `capture(window) -> payload`, supports the nine existing ToolWindow names and Files window.
- `from_paths(paths) -> payload` for Files selection.
- payload = {title: str, text: str, paths: list[str], source: ref dict, url: optional HTTP(S) source, items: list[dict]}. All keys optional except title/source. Selection takes precedence over whole record. Credentials/raw mail/account settings never included. No network/model calls. Include useful structured snippets (due, agenda, tasks, decisions, attachments, sources) as `items`.

`interop_targets.py` (target adapter):
- `ACTIONS`: dict action id -> {target, label (German string), modes: list ('copy','link'), description (German)}.
- `available(payload) -> list[str]` filtered to supported actions.
- `choices(action, root=None) -> list[dict]` records with `id`, `title` for destination selection; no secrets.
- `apply(action, payload, choice, job, root=None, store=None) -> ref dict`. `choice`: {id: str optional, title: str, mode: copy/link, due: ISO date optional, token: transfer id}. Called on target worker only, after target saves current record. Use library root arg. `store` is a Lumen Store for Wissen and optional app settings. Metadata on new/updated library records: `interop_sources` list of URLs, `interop_token` for replay handling. Source URL supplied as payload['source_url'] by shared UI. Result contains app/kind/id/title/path as applicable.
- Actions must have real complete outcomes, not placeholder buttons. Core targets: Wissen import text/Markdown and attachments; Workbench create/add resource/notes/questions; Household new/add document; Radio new/add sources; Reader import; Meetings audio import/agenda; Inbox draft/task/calendar proposal. Vault and audio handled by separate module.
- Target adapters must be idempotent for repeated `choice.token`. Never autosend, autocall AI, or overwrite originals. Worker cancellations clean new partial copies. Live target flushes pending changes before apply; root agent implements common receive/show.

`interop_vault.py`: application data source discovery, plan source merging, file status, contextual backup/restore utilities. UI entry functions should be callable from common menu. Do not change shared UI/core files without coordination.

`interop_ui.py` (root agent): send menu, target review dialog, relationship/history UI, receive/open ref helpers. Common ToolWindow and Wissen toolbar attachment, Files context menu and CLI activation are integrated by root after adapter completion.

## Verification

Tests: `QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de PYTHONPATH=files /usr/bin/python3 -m unittest test_interop_data test_interop_targets test_interop_sources test_interop_vault -v` then entire isolated native suite. All tests use temporary tools roots and Lumen Store roots; no user data/model/mail/backup target access. Test DE+EN visible strings with catalog checker, cold/warm dispatch, busy target preservation, provenance, replay/cancel, malformed links and path bounds. Test backups with synthetic local data and audio with private virtual devices.

## Scope ledger

The numbered ideas remain requirements. Mark implemented/partial/pending explicitly in COVERAGE.md with concrete tests; a generic menu alone does not fulfill specialized workflows. Never claim all 100 are done without evidence.
