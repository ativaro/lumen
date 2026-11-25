# Lumen desktop service

`lumen-service` is Lumen's one desktop service: a user process per session that does the work the
Qt processes leave to Rust: the memory (`src/recall.rs`, its learning `src/learning.rs`, ranked by the
shared crate `native/memory`) and its meaning search (`src/memory.rs`), the conversations with
the OpenCode engines it runs for the Qt views (`src/engine.rs`, `src/turn.rs`, with the shared crate
`native/engine`) in the user's persona (`src/persona.rs`, with the shared crate `native/persona`),
the HTTPS connection to the user's Lumen Server (`src/bridge.rs`) and the notebook core of Lumen Notes
(`src/notebook.rs`). It takes no arguments; the Qt side's bindings `files/lumen_service.py`,
`files/assistant_backend.py`, `files/lumen_connect.py`, `files/wissen_data.py` and
`files/lumen_memory.py` start it on demand. `lumen-service learning-mcp <event.json>` is the learning
engine's tool server (below).

## Socket, lock and peers

- `$XDG_RUNTIME_DIR/lumen/service.sock`, socket 0600 in a folder 0700. The service refuses to start
  when `XDG_RUNTIME_DIR` is unset or not absolute, or when it or `lumen/` is a link, belongs to
  another user or is open to group or others; it never falls back to a shared place.
- `lumen/service.lock` keeps one service per user: a second one finds it locked and leaves at once.
  With the lock held, a socket left by a killed service is replaced.
- Every connection is checked with `SO_PEERCRED`; one from another user is closed unanswered. The
  binding checks the service's user the same way before it sends anything.

## Protocol

One JSON request per connection, ended by a newline or by the client closing its sending side; one
JSON answer (ended by a newline), then the service closes the connection. `notes.attach` sends the
bytes it names in `size` after its request's newline. `engine.turn` and
`bridge.receive` instead answer with one JSON line per event until their last; the client keeps its
side open (and may send lines of its own to a turn, below). Requests and answers carry `"v": 1`. A request without it or in
another version gets `{"v":1,"error":"unsupported_version"}` and nothing is done. Other errors:
`invalid_request` (no JSON object, or an `engine.*` request the service cannot read) and
`unknown_op`. A refusal the view shows is `{"v":1,"failed":"<text in the window's language>",
"reset":false}`; `reset: true` means the conversation must start anew (the server binding changed).

| Request | Answer |
|---|---|
| `{"v":1,"op":"hello"}` | `{"v":1,"build":"<SHA-256 of the running program>"}` |
| `{"v":1,"op":"quit"}` | `{"v":1}`; socket and lock are freed before the answer, then the service ends |
| `{"v":1,"op":"pairing.read","path":"/…/lumen-server/connection.json"}` | `{"v":1,"pairing":"<the file's text>"}`, `"pairing":null` without one, or `{"v":1,"failed":"unusable"}` |
| `{"v":1,"op":"memory.search","home":"/…/memory-search","checksums":["<model>","<tokenizer>","<runtime>"],"path":"/…/memory-index/<key>.sqlite3","query":"Wann war der Arzttermin?","entries":[{"id":"m3","revision":"1","title":"Arzttermin 3","text":"…","digest":"…"}]}` | `{"v":1,"ready":200,"total":200,"mode":"hybrid","reason":"","scores":[["m3","1",0.62]],"excerpts":[["m3","1","…"]]}`, or `{"v":1,"mode":"text","reason":"unavailable","scores":[]}` |

`pairing.read` is the only reader of a pairing (`files/lumen_connect.py`'s `read_config`, for every
profile of the connector, `--config-dir` included): the user's own regular file of at most 64 KiB, 0600,
not a link, with a plain `https://host[:port]` address, a device ID as the server issues it and a
token of printable characters. The answer carries the file's text, so the connector keeps its key
order when it saves the pairing again.

A later protocol version keeps answering `{"v":1,"op":"hello"}` and `{"v":1,"op":"quit"}`, so that an
older binding can still replace a newer service.

### Engine conversations

Every `engine.*` request names its engine and carries what only the Qt view knows:

- `engine`: `{"directory": "/abs", "env": {…the view's environment…}, "project_config": true,
  "research": false, "environment": {…}}` for an engine the service runs for this profile
  (`environment` is the short-lived learning engine's own profile), or `{"url":
  "http://127.0.0.1:<port>", "password": "…", "directory": "/abs", "env": {…}}` for an engine the
  caller runs. The persona reads the pairing from the configuration folder of `env`.
- `store`: the view's Store, `/…/lumen.sqlite3`.
- `policy`: the model policy (`modelPolicy` of the Store); a local-only policy pins its model.
- `texts`: `{"language": "de"|"en", "catalogue": "/…/files/translations/en"}`. The German source text
  is the key, English values come from that catalogue (`src/texts.rs`), `{0}` are its placeholders.
- QSettings values (model, auto-approval) arrive as fields of the request; the service reads no INI.

| Request | Answer |
|---|---|
| `engine.info` with `env` | `{"version":"1.18.34","managed":"/…/lumen/engine/1.18.34/opencode","binary":"<program it would start>"}` |
| `engine.start` | `{"engine":{"database":"lumen"\|"inherited"\|"default","binary":"…","startup":{"outcome":"ready","elapsed_ms":420}}}`; a failed start answers `failed` with `engine.startup` = `{"outcome","hint","elapsed_ms","captured_bytes","exit_code"?,"process_error"?}` (classes only, never output) |
| `engine.call` with `method`, `path`, `body` | `{"data":…,"diagnostic":{counts only},"facts":{"opencode_endpoint"\|"anonymous_opencode":bool}}`; only `GET /config`, `/config/providers`, `/provider`, `/provider/auth`, `/mcp`, `/skill` and `PUT /auth/<provider>` pass |
| `engine.sessions` | `{"sessions":[…]}`: this directory's Lumen conversations of the current server binding |
| `engine.conversation` with `session` | `{"messages":[…],"permissions":[…],"questions":[…],"busy":bool,"status":"…","reply_error":"…"\|null}` after checking the session belongs to this view |
| `engine.reply` with `kind` (`permission`\|`question`), `id`, `allow` or `answers` | `{}` |
| `engine.stop` | `{}`; the profile's engine ends once no turn uses it |
| `engine.turn` (below) | events |

The settings view and the conversations' preset menus use the persona operations:

| Request | Answer |
|---|---|
| `persona.catalog` with `texts` | `{"presets":[{"id","title","description"}],"fields":[{"id","title","options":[{"id","title"}]}]}` in the request's language |
| `persona.preview` with `texts`, `profile` (JSON text) and `choice` (a preset whose traits replace the profile's, or empty) | `{"profile":{…the profile it stands for…},"preview":"<illustrative answer>"}` |
| `persona.choose` with `store`, `session` and `choice` (a preset or empty) | `{}` once `persona/session/<session>` is written, or `failed` |

`engine.turn` carries `message` (`msg_…`, made by the view), `session` (empty for a new one), `text`,
`memory_text` (what the memory is searched with, else `text`), `files` (`[[path, mime], …]`), `agent`,
`title`, the mode flags `proposal`, `memory_context` (a proposal that still gets the memory),
`project_task`, `web_research`, `screen_guidance`, `read_only`, `background`, `presentation`,
`rich_results`, `context_data`, `screen_image` (base64 PNG up to 12 MiB), `model`, `auto_approve` and
`persona` (below). The service first prepares the memory (not for proposals without `memory_context`,
project tasks or the screen companion; below), checks the image, makes the persona of a conversation
in the user's style (not for proposals, project tasks or the screen companion), writes the mode's
system text followed by the persona's style text and the memory's context block, chooses the model
under the policy (`GET /config`, `/config/providers`, `/provider` as needed), checks an existing
session or creates one whose permissions match the mode, then sends the prompt exactly once
(`lumen_engine::response`). The learning engine's own turns (`learning`, below) are the service's.

`persona` carries the view's QSettings: `{"profile": "<personaProfile, JSON text, keys in any
order>", "override": <personaLocalOverride>, "choice": "<the conversation's preset or empty>"}`.
Without a pairing (`lumen-server/connection.json` of the view's configuration folder, read without
following links, only when private and valid), or with `override`, the local profile applies; else
the account persona the server answers on `/bridge/persona` (each step within 3 s, all within 5 s),
or, while it cannot be read, the default style with the event `persona` (`notice`: "Konto-Persona
nicht erreichbar · Lumen verwendet den Standardstil"). An unusable pairing fails the turn before any
engine starts ("Persona- oder Serverbindung nicht lesbar …"), one that changes while the account
persona is read fails it too ("… geändert …"). The service is the only writer of the conversations'
persona rows in the Store's `settings` table (nothing else is touched, a `user_version` above 3 is
refused, a lock is waited for up to 15 s): `persona/context/<session>` (the binding, revision and
preset the conversation was held with, as the earlier Python view wrote it) and
`persona/session/<session>` (its preset). A conversation whose row differs (another profile, account
persona, preset or pairing, or no row) continues in a new session: its `session` event then names
the new one with `created: true`.

Events: `memory` (`context`, the sources view's snapshot `{"version":1,"message_id","session_id","phase":
"loading"|"disabled"|"prepared"|"submitted","server_stamp","server_connection","sources":[…],"retrieval":
{…}}`, and the `notice` the view shows), `engine` (its facts), `persona` (`notice`), `session` (`id`,
`created`), `submitted`, `messages` (the newest hundred,
when they change), `requests` (`permissions` not yet answered, `questions`), `status` (`text`) and last
`end`: `{"ok":true,"answer":"…","status":"Bereit"}` (with `"learn":true` when the view is to ask
`memory.learn` for the message), `{"ok":false,"failed":"…","provider":true}` for a
reply the provider refused, `{"ok":false,"failed":"…","reset":…}` or `{"ok":false,"cancelled":true}`.
The view may send `{"op":"cancel"}` and `{"op":"auto_approve","enabled":bool}`. Cancelling, or the
view closing the connection (it ended or crashed), aborts the run (`POST …/abort`) and retires the
engine, which then ends with its tools; nothing is sent again. With auto-approval each open permission
of the session and of its agents' sessions is allowed once, never for proposals or the screen
companion. An engine that goes idle without a reply fails the turn after 30 seconds; the policy's
`timeout_seconds` (30 to 7200, default 900) bounds the reply. A changed or broken server pairing ends
the turn within half a second.

### Memory

The memory of the earlier `files/lumen_memory.py`, `memory_projects.py`, `knowledge_context.py`,
`memory_local.py`, `memory_index.py`, `memory_learning.py`, `memory_agent*.py` and `memory_bridge.py`,
once, in Rust (`src/recall.rs`, `src/learning.rs`). It is Lumen's own notebook `<state>/lumen-memory`
(through `src/notebook.rs`, locks `memory-state.lock` before `wissen.lock`) with the Store rows
`memory/namespace`, `records`, `tombstones`, `options`, `shares`, `forgotten`, `proposals`,
`project-folders`, `revision`, `privacy_revision`, `search_status` and `session/<id>`, the shares of the
user's notebook, the project folders (Lumen projects from `tools_data`' `workbench` library), the
paired server's mirror `~/.config/lumen-server/memory.sqlite3` (read only, for the stamp) and the
meaning search's index rows `memory-index/*.sqlite3`. Everything is written as the Python code wrote it:
the same keys in the same order, `json.dumps`' spelling, the same calls of the clock and the random
identifiers. Every request carries `store` (the state folder), `env` (the view's environment: its
configuration, data and tools folders, `LUMEN_MEMORY_HOME`) and `texts`; it runs on a thread of its own
and answers `{"result": …}` or a refusal as `notes.*` refuses (`kind`, `errno`, `filename`).

| Request | Result |
|---|---|
| `memory.options` / `memory.status` / `memory.model` | the options / the meaning search's state (`disabled`, `not_installed`, `ready`, `hybrid`, `indexing`, …) / `{"version","files":{path: SHA-256},"home"}` |
| `memory.stamp` | `{"stamp":[enabled, privacy revision, server mirror's stamp(, project folders)],"server":"<the mirror's stamp>"}` |
| `memory.open` / `memory.identity` with `path` / `memory.record` with `note` | `{"namespace","root","identity"}` / the portable ID / the note's record |
| `memory.configure` (`enabled`, `learn`, `expected`, `solutions`, `automatic`), `memory.scan`, `memory.migrate` (`dry_run`), `memory.remember`, `memory.write`, `memory.restore`, `memory.forget`, `memory.share`, `memory.allow`, `memory.eligible` (`directory`, `query`, `limit`), `memory.prepare` (`query`, `directory`), `memory.valid_prepared`, `memory.learn_account`, `memory.account_learning_status`, `memory.apply`, `memory.propose`, `memory.proposals`, `memory.review`, `memory.project_info`, `memory.project_configure`, `memory.shared` (`path`, the view's `root` and `identity`) | as the methods of `lumen_memory.Memory` returned them |
| `memory.changed` (`invalidate`), `memory.save_record` (`note`, `meta`, `records`) | for the replication (`files/memory_sync.py`) and the Notes' moves, which hold `memory-state.lock` themselves |
| `memory.verify` with `home` | the mode a search on an empty index answers (`hybrid` once the model works) |

A turn's memory: a conversation whose `memory/session/<id>` row names another stamp (or a server note
used earlier at another revision) begins anew. The context is prepared (up to three times while the
memory changes meanwhile): local memories (allowed, current, of the scope; three preferences reserved;
ranked by `native/memory` with the meaning search's scores; excerpts; 18000 characters) and, with a
pairing, the account memory (`/bridge/memories/context?q=` and `/validate`, 3 s each) and the shared
server notes (`/bridge/knowledge-context?q=` and `/validate`, 3 s). An account memory that no longer
validates begins the conversation anew; one that cannot be reached fails the turn ("Server-Gedächtnis
nicht erreichbar …"). Each prepared result is a `memory` event with its notice ("Gedächtnis · 2
passende Quellen", a warning, or "Gedächtnis nicht erreichbar …"); the conversation's row is written
once the session is known.

`memory.learn` with `message` (a turn that ended with `learn`), `view` (the view's name for its queue),
`model` and the view's `engine`, `store`, `policy` and `texts` answers `{"event":"memory","notice":…}`
lines and last `{"event":"end"}`. Each view learns one turn after the other, at most four waiting;
closing the connection ends it. Locally, the view's engine names its configuration (`GET /config`); under
a local-only policy the model's provider must be confirmed at a loopback address (as for a turn) before
any of its credentials (`opencode/auth.json` of the view's data folder) is copied into a private
profile in the view's `TMPDIR` (0700: the learning skill, `event.json`, the provider's credentials, an
engine configuration that allows only the skill and `lumen_learning_*`); a learning turn there (60 s)
lets the model read the event and submit at most three candidates, which the memory applies under its
current consent and revision. With account memory the server learns (`/bridge/memory-learning`, 4 s;
its receipt every two seconds for up to a minute). `lumen-service learning-mcp <event.json>` serves the
two tools (`lumen_memory_learning_context`, `lumen_memory_learn`) as `bin/lumen_mcp.py`'s transport
did: at most 20 lines of at most 32768 characters, the same JSON-RPC answers, `result.json` (0600)
beside the event, every call refused once learning was switched off or the stamp changed.

Not as before: a malformed server answer of the wrong type (a number where a text belongs) is a
warning like a missing field, where Python failed the preparation with a `TypeError`; urllib's error
texts of an unreachable server are the bridge's; a relative folder is resolved against `/`, the
service's folder, not the view's.

### Lumen Server

The bridge requests carry the connection the caller uses: `server` (`https://host[:port]`), `token`
(the device token, sent as `Authorization: Bearer`; none for a pairing) and `ca_file`. They are
answered on the engines' thread, so a slow server never holds up a search or a turn.

| Request | Answer |
|---|---|
| `bridge.request` with `path` (with its query), `body` (the JSON text to POST, or `null` for a GET) and `timeout` (seconds) | `{"status":200,"reason":"OK","headers":[["content-type","…"],…],"body":"<base64>"}` for every status, a redirect too (it is not followed) |
| `bridge.receive` with `path`, `file` (absolute, must not exist yet), `limit` (bytes) and `timeout` | `{"received":<bytes so far>}` after every part, then `{"status":200,…,"size":n,"sha256":"<hex>"}`; a refusal answers like `bridge.request` |
| `bridge.trust` with `ca_file` | `{"pem":"<certificates>","only":true}` (the CA file alone) or `{"pem":"<the NSS store's Lumen CAs>","only":false}` (besides the system's) |

A failure is `{"failure":"<kind>","reason":"…","errno":n|null}` with the kinds `url` (no plain HTTPS
address, user info included), `ca` (CA file unreadable or without a certificate), `connect` (name,
refusal, network, connect or TLS timeout, with the system's error number), `certificate`, `tls`,
`timeout` (no answer or no further part of it in time), `closed` (no answer at all), `incomplete`
(cut off), `too_large` and `file`. `lumen_connect.py` raises for each what urllib raised before:
`HTTPError` with status, reason, headers and body for a status outside 2xx, `URLError` for
`connect`, `certificate` and `tls`, `TimeoutError`, `http.client.RemoteDisconnected` and
`IncompleteRead`, `ValueError("Serverantwort ist zu groß.")`.

The rules are those of the earlier Python client: HTTPS only, HTTP/1.1 with one connection per
request, no redirects, at most 4 MiB per answer (a refusal's body is cut there), every step (connect,
TLS, answer, each read) within `timeout` and the whole request within four times it. A download is
written to `file` (0600, created anew, never through a link) as it arrives, synced, and checked
against `limit`; a refusal, a failure or a client that closes its side (a cancelled view) removes it.
TLS is rustls with ring, as on the server (TLS 1.2 and 1.3). A connection with `ca_file` trusts that
file's certificates alone; without one it trusts the system's certificates (`SSL_CERT_FILE`,
`SSL_CERT_DIR`, else the system bundle) and the Lumen Server CAs the user trusted in the NSS store
(`~/.pki/nssdb`, else `~/.local/share/pki/nssdb`): `certutil -L` entries named `Lumen Server Local
CA` with twelve hex digits and trust `C,,`, each exported with `certutil -a` (five seconds each).
A server whose own certificate is byte for byte one of the trusted certificates (a self-signed
server certificate named as `ca_file`, also one marked as a CA as `openssl req -x509` makes it) is
trusted as it is, as OpenSSL trusted it for the earlier Python client. It is still checked as OpenSSL
checked it: its validity period; the name (an alternative name, or for a host name without
alternative host names the common name, never for an address); and, where the certificate limits
them, key usage (digital signature, key encipherment or key agreement) and extended key usage (TLS
server). Other certificates need a chain to a trusted one, as webpki checks it.

Unlike the earlier urllib client, the bridge ignores the proxy variables (`https_proxy`, `all_proxy`
and the like) and always connects directly to the user's server, a deliberate choice.

### Lumen Notes

The notebook core of the earlier `files/wissen_data.py`, once, in Rust (`src/notebook.rs`, with
`src/notebook/text.rs`, `python.rs` and `yaml.rs`). A notebook is a folder of Markdown notes; its
private state lies in the Lumen state folder (`store`, absolute): `lumen.sqlite3` (the rows
`knowledge/notebook`, `knowledge/identity` and `knowledge/imports`; the service opens an existing
store and creates no tables), `wissen-history/` (`library.sqlite` and `assets/`, the earlier bytes of
every changed or removed note), `wissen-drafts/` and the lock files `wissen.lock` (every write) and
`wissen-import.lock`. Every request carries `store` and `texts`; those on a notebook also `root`
(absolute; the binding expands `~`), `identity` (as an earlier `notes.open` answered it) and `create`.
Each runs on a thread of its own, so a long scan or a held lock delays no other request.

| Request | Answer |
|---|---|
| `notes.open` | `{"root":"/…","identity":["fsid:<n>",<inode>]}` (`[st_dev, st_ino]` where the file system has no ID) |
| `notes.activate` with `root` or none | `{"root":"/…"}`: the notebook, its old memories imported, remembered with its identity |
| `notes.read` / `notes.raw` / `notes.image` with `path` | the note `{"id","path","note_id","title","text","source","legacy","created","tags","links","hash","raw_size","_properties_source","_properties","modified"}` / `{"raw":"<base64>"}` |
| `notes.write` with `path`, `text`, `expected`, and `source`, `legacy`, `created`, `note_id` (null keeps the note's) | the note as written |
| `notes.create` with `title`, `text`, `source`, `legacy`, `folder`, `note_id` | the new note |
| `notes.create_collection` with `name` / `notes.remove` with `path`, `expected` | `{"name"}` / `{"key"}` (the history entry) |
| `notes.versions` with `path` or none / `notes.restore` with `key`, `expected` | `{"versions":[…]}`, newest first / the note |
| `notes.capture` with `title`, `text`, `source`, `memory` / `notes.memory_path` with `memory` | `{"path"}` |
| `notes.migrate` / `notes.scan` with `migrate` and `known` (`{path:[hash, repr(modified)]}`) | `{"changed"}` / `{"notes","folders","errors","limited","root","identity"}`, with `known` also `"unchanged"` (paths left out of `notes`) |
| `notes.context` with `paths` (one to eight), `query` | `{"notes":[…]}`, each text cut to the excerpt around the query |
| `notes.attach` with `size`, the PNG's bytes after the line | `{"path":"attachments/<uuid>.png"}` |
| `notes.replace` with `path`, `before`, `after` (base64) | `{}`: the move's raw rewrite, history included |
| `notes.stat` with `path`, `folder` / `notes.relative` with `path` | `{"stat":[st_dev, st_ino]\|null}` / `{}` |
| `notes.draft` with `root`, `path`, `text` (none reads), `expected` / `notes.clear_draft` | `{"draft":{…}\|null}` / `{}` |
| `notes.parse` with `path`, `raw` / `notes.excerpt` with `text`, `query`, `limit` (no store) | the note without `modified` / `{"text"}` |
| `notes.tags` / `notes.targets` / `notes.mask` / `notes.properties` with `text` (no store) | `{"tags":[…]}` / `{"targets":[{"title","anchor","start","level"}]}` / `{"mask":"…"}` / `{"properties":{name:{"kind","value"}}}` |
| `notes.identity` with `value` / `notes.add_tag` with `text`, `tag` / `notes.rename_tag` with `text`, `old`, `new`, `descendants` / `notes.set_property` with `text`, `name`, `kind`, `value`, `remove` (no store) | `{"tag"}` / `{"text"}` |

A refusal is `{"failed":"<text in the window's language>","kind":"value"|"unicode"|"os","errno":n|null,
"filename":"…"|null,"path_object":bool}`; the binding raises `ValueError`, `UnicodeError` or
`OSError(errno, strerror, filename)` (`Path(filename)` where Python named a `Path`), as the Python
core did. Files are written as Python wrote them, byte for byte: the header `<!-- lumen: {"source": …,
"legacy": …, "note_id": …, "created": …} -->` with `json.dumps`' spelling (`repr` of floats), the
UUID as `uuid.UUID` read it, a temporary `.lumen-<uuid>` (0600) synced and renamed over the note, the
folder synced; history rows and assets, drafts and settings rows likewise. Reading follows the
earlier rules: UTF-8 with an optional BOM (refusals with Python's `UnicodeDecodeError` text), one
MiB per note, no links, the folder's identity checked on every access, and for a scan 30000
entries, 10000 notes and 128 MiB. Titles, tags, links and front-matter properties are derived as the
earlier Python `notes_structure`, `note_tags` and `notes_properties` derived them; the front matter is
read by a statement-for-statement port of PyYAML 6's safe composer (`src/notebook/yaml.rs`). The editor
asks for the same derivations of its unsaved text (`notes.tags`, `notes.targets`, `notes.mask`,
`notes.properties`, `notes.identity`) and has its tag and property edits made here
(`src/notebook/edit.rs`): only the YAML value or `#tag` concerned changes. Positions (`start`, the mask)
count code points. A call on a note of 1 MiB takes about 10 to 18 ms, one on a short note 0.1 ms; the
views ask after a pause in typing (120 ms for the tags, 250 ms for the live preview).

Not as before: names that are no UTF-8 are skipped (a note counts as unreadable), a lone surrogate
in a header or quoted YAML scalar reads as U+FFFD, a header nested deeper than 50000 levels or front
matter deeper than 450 reads as invalid (Python raised `RecursionError` there), and there is no parse
cache (`notes-index-*.sqlite` of the earlier code is no longer read).

## Lifecycle

The binding starts the service in its own session with `ORT_DISABLE_TELEMETRY=1`. A caller that runs
in a systemd service unit (the server connection `lumen-server-connector.service`, a timer's job, the
top bar) starts it through `systemd-run --user --scope`, so the unit's end does not end the service
the views share; without a user manager to ask, it starts as before. Before its first
request to an installed program (path, inode, size and modification time) it compares the program's
SHA-256 with the `build` of the running service. When an update has replaced the program, it sends
`quit`, starts the new one and checks its `build`. A killed service leaves its socket behind; the
next request finds it refused and starts a new service. The service runs until it is told to quit or
the session's processes end. Waiting for requests costs no processor time.

## Engines

The service starts `opencode serve --hostname 127.0.0.1 --port 0` for a profile (the view's
environment, directory, options and a local-only model; the program and its database are chosen from
the view's own environment, also for the learning engine, whose profile has folders of its own) the
first time it is asked, reads the port
from its output (25 s), and reuses it while it answers its health check; a dead or hung engine is
replaced. The engine gets a random password, the view's environment without `OPENCODE`/`OPENCODE_PID`,
`OPENCODE_DB` by the earlier rule (the managed engine keeps away from a foreign schema and then keeps
`lumen-v1.db`; nothing is migrated), and `OPENCODE_CONFIG_CONTENT` with the paired server's MCP entry
and skills (`lumen-server/connection.json`, read without following links and only when private) and
the crate's compaction plugin, written to `$XDG_RUNTIME_DIR/lumen/lumen-continuity.mjs`. The binding
stamp stored in session metadata is the SHA-256 of the same text Python's `json.dumps` wrote.

Each engine leads its own process group and is sent TERM when the service ends, also when it is killed
(`PR_SET_PDEATHSIG`). The group is ended (TERM, five seconds, KILL) when the engine was idle for ten
minutes, after `engine.stop` or a cancelled or failed turn once no turn uses it, after `quit` (the
answer comes first, so an update replaces the service at once), on TERM, INT or HUP, and when the
session's runtime folder or the socket is gone.

## Memory search

`memory.search` (also asked by the memory's operations on their threads) loads the model of `home` once `<home>/model/model.onnx`,
`<home>/model/tokenizer.json` and `<home>/runtime/libonnxruntime.so.1.30.0` match the three
checksums; another `home` or other checksums replace it. Ten minutes after the last question the model
is dropped and loads again with the next one. The memory (`src/recall.rs`) prepares the index rows and
their digests. The service fills in vectors only for rows it finds unchanged, scores only rows whose
revision and digest still match, and answers with the index state, the scores and up to twelve
excerpts. After an answer it goes on indexing in small steps for up to twenty seconds; a new request
comes first. Paths in the request are absolute: the service runs in `/`.

The model (`paraphrase-multilingual-MiniLM-L12-v2`, quantized ONNX) runs in Lumen's sentence encoder
(`native/sentence-encoder`), the same code the server uses: ONNX Runtime 1.30.0, loaded at run time
from the installation, and long notes split into overlapping windows of 126 tokens every 102 tokens.
`LUMEN_MEMORY_THREADS` (1 to 8, default 1) sets the runtime's threads for one window.

Measured with 200 short notes on one thread: the first answer after a cold start comes after about
0.8 s, all vectors are ready after 1.3 s, a question takes about 6 ms, and the service holds about
440 MB with the model loaded (about 285 MB of it the tokenizer), 5 MB before the first question and
21 MB once the model is dropped; the first question after that takes about 0.5 s. The vectors are
bit-identical with the earlier Python worker's on its 56 reference texts.

## Checks

```bash
python3 ../document-core/check-licenses.py .
cargo fmt --check
cargo clippy --locked --offline --release --all-targets -- -D warnings
cargo test --locked --offline --release
```

The memory's tests replay the recorded Python domain (`tests/memory-golden.json`, made by
`make_golden.py` of the R10 measurements, `measure/memory/`, from the memory modules of d0b9ea9d on the
Python notebook core of ee2046ca; `LUMEN_MEMORY_GOLDEN` names another corpus): answers and refusals,
server requests, the calls of the clock and the identifiers, Store rows, files with their modes,
history and index rows, byte for byte; and interruptions of a new memory, an edit, a migration and a
project copy, and edits during a search.
`files/test_lumen_service.py` runs the built program (`LUMEN_BIN_DIR`) in a private runtime folder;
`files/test_server_mcp_binding.py`, `test_assistant.py`, `test_setup.py`, `test_model_default.py`
and `test_persona.py` run the engine conversations through it against engine stand-ins (the
persona's account persona against a local HTTPS server); `files/test_server_artifact.py`,
`test_server_file_import.py` and `test_server_app_window.py` run the bridge through it against local
HTTPS servers. The tests of `src/bridge.rs` run against a local rustls server with throwaway CAs made
by `openssl`. `files/test_i18n.py` checks that every `tr("…")` of `src/` has its English value.
The notebook's tests compare it with the recorded Python core (`tests/notebook-golden.json`, made
by `make_golden.py` of the R10 measurements from `files/wissen_data.py` at `ee2046ca`;
`LUMEN_NOTEBOOK_GOLDEN` names a larger corpus): parse and encode results, refusals, written bytes,
modes, history and settings rows; and the editor's derivations and edits with the recorded Python
modules (`tests/editor-golden.json`, made by `make_editor_golden.py` from `files/note_tags.py`,
`notes_properties.py` and `notes_structure.py` at `2ee18980` with PyYAML 6.0.3, 1021 texts;
`LUMEN_EDITOR_GOLDEN` names a larger one: all 20221 texts of the fuzz corpus matched). `files/test_wissen.py`, `test_notes_*.py` and `test_memory*.py`
run the Notes and the memory through the service.

## Unsafe code

The crate denies `unsafe`; the notebook uses rustix for its directory-relative file operations. Only
`mod sys` in `src/main.rs` allows it, for `geteuid`, the
`SO_PEERCRED` query that std offers only unstably (`UnixStream::peer_cred`), `malloc_trim` and the
`prctl(PR_SET_PDEATHSIG)` that ties an engine to the service.

## Frozen sources

`vendor/` holds the sources the build uses; the build never reaches the network. Packages that are
never compiled on Linux (Windows, WebAssembly) keep only their `Cargo.toml` and an empty
`src/lib.rs`, so the lockfile still resolves while the sources stay small. Only freely usable
licences are accepted.
