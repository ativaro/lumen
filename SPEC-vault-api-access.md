> **Geltungsbereich:** Diese Entwicklungs- und Prüfunterlagen betreffen die separat eingerichtete native Tresor-Vorabversion. Der reguläre Desktop-Starter öffnet heute die Server-Vault-App; `--lab` ist ausdrücklich getrennt, `--backups` führt zu Lumen System. Frühere UI-/Installationszustände sind historische Belege, keine neue Sicherheits- oder Releasefreigabe. [Aktuelle App-Zuordnung](docs/desktop-retirement.md).

# Vault: native credential intake and constrained credential use

Status: manually approved prerelease, 2026-10-05. The user explicitly accepts
trying the installed native Vault before production qualification. The primary
requirement is encrypted credential storage instead of passwords/tokens in
Markdown files. BookStack is the first read-only integration used to exercise it.
No personal hostname, token or vault data belongs in source or test fixtures.

## Native storage flow

The shared assistant instruction in Lumen, Search and Files offers Vault storage
once when the user actually supplies credentials, using semantic context in the
user's language. There is no keyword scanner. Discussion, examples and retrieved
content do not trigger this offer. A current native user-text source permits
`lumen_vault_store_from_chat(source, title, kind, fields)`: numeric field selectors
are resolved locally into a prefilled native editor. Save is the single consent;
there is no preliminary chat question or requirement to retype those values.
Decline or cancellation suppresses further offers for the same access. This is
model-directed behavior, not a deterministic detector. No flow removes prior chat
disclosure or grants permission for later API/MCP use.
When tools are unavailable, Lumen points the user to Vault without claiming a save.

The source channel captures only explicit raw UI input, before appended paths,
learning instructions or other generated context. It excludes file actions,
background work and read-only/proposal modes. A random per-backend Unix socket in
the private owned runtime directory has mode0600. Sources are random capabilities,
bounded to16 messages/16 KiB each and10-minute expiry, cleared on session switch or
shutdown. During a pending native request the selected text remains pinned until
completion (at most95 seconds); expired idle sources are removed periodically.
Sources are never written to files, telemetry, clipboard or MCP responses.
Python strings cannot guarantee physical erasure and same-user processes are not
isolated from one another. Existing original chat/engine/cloud history is unchanged.

Selectors use 1-based lines (including blank lines), optionally 1-based whitespace
words, and optional 0-based Unicode code-point start/end (end exclusive). Word
selection avoids counting long credential offsets; slices handle adjacent labels
and quotes without modifying the selected value. Native widgets allow review and
correction. Only username/token ID, password/token secret and URL can be prefilled;
native UTF-16 limits and control-character validation reject truncation. The
secret field is required. No arbitrary protected/custom fields or connection
grants are accepted. Token ID visibility/authentication uses existing profile rules.

One source permits one confirmation attempt, consumed before native dispatch even
on cancellation or an unknown outcome; equivalent selectors cannot replay it.
Explicit locked/busy responses allow local unlock/dialog completion and retry.
Multiple accesses in one message can use manual entry after the first attempt.
Disconnecting the MCP worker or closing the conversation cancels pending native
IPC. A Save already dispatched remains an unknown outcome until checked in Vault.
Only an opaque saved reference is returned. Numeric selectors are the sole new
tool arguments; resolved values travel directly from the local source service to
native Vault. This is a one-way intake from already supplied chat, not a Vault
credential export API.

The manual fallback remains available without an eligible source:

1. Lumen calls `lumen_vault_store(title, kind)` with a non-sensitive label and
   `login` or `token`. There is deliberately no password, token, username, raw
   field dictionary or secret export argument. The tool is discoverable even
   when general MCP writes are disabled: it only opens UI and cannot save without
   the native user clicking Save. No other writing tool gains that exception.
2. The installed native singleton opens. If locked, the user unlocks it locally
   and retries. A native credential editor opens with the suggested title/type.
3. The user enters credentials into protected native fields and clicks Save.
   The editor uses the existing inherited pipe to the Rust broker. The same
   encrypted KDBX write/history/recovery rules as manual Vault editing apply.
4. Only a successful save returns `{saved: true, reference: "vault:<uuid>"}`.
   This identifier is not a bearer capability, and cannot retrieve a secret.
5. Cancel before Save, caller disconnect, deadline or lock closes unsaved input.
   Writes are not queued behind a busy broker. Once the user clicks Save and the
   write is dispatched, a later interruption cannot undo it: the tool reports
   an uncertain outcome, or disconnects, rather than claiming the entry was not
   saved. Check Vault before retrying an interrupted save.

The assistant instruction applies in every language: use native intake, do not
request secrets in chat or save them to notes, memories, logs, scripts or Markdown.
This instruction is not a sandbox for general OpenCode tools. There is no keyword
filter, automatic scanning of arbitrary messages, or promise to undo disclosure
of a credential that a user has already submitted in chat.

## BookStack test connector

In an API-token entry, edit the optional BookStack HTTPS origin and protected
Token ID. Store the token secret in the existing Password/token field. Choose
**Für Lumen verfügbar machen / Make available to Lumen** to save availability
for that entry inside the encrypted KDBX. A second click disables it persistently.
Multiple entries may be available; only one request can be pending. Each unlock
restores valid enabled profiles. Lock and profile edits revoke pending requests;
trashing or restoring historical fields clears availability. The separate
five-minute grant timer is removed; the existing five-minute idle lock remains.

`lumen_bookstack_read` accepts fixed, validated operations:

| Operation | Fixed GET endpoint | Result |
| --- | --- | --- |
| `check` | `/api/books?count=1` | Connection success only |
| `list_books` | `/api/books?count=N&offset=N` | Up to 20 projected records |
| `search` | `/api/search?query=...&count=N&offset=N` | Up to 20 projected records |
| `read_page` | `/api/pages/<positive integer>` | IDs/name and bounded plain text |

There are no POST/PUT/DELETE methods, arbitrary URLs, headers or request bodies.
API-token creation/account permission changes are performed by the user in
BookStack. Use a dedicated account with read access only to intended documents.
Official API reference: https://demo.bookstackapp.com/api/docs.
Authentication: `Authorization: Token <token_id>:<token_secret>`; the account
requires Access System API permission in addition to document permissions.

Each request requires an independent native confirmation, showing the canonical
HTTPS origin and exact operation/arguments in plain text. Cancel has default
focus. It explicitly says the caller is a local program, **not authenticated as
Lumen**, and returned documentation can reach the requesting cloud model. Normal
Don't-ask settings do not approve this dialog. Nothing is automatically indexed,
stored in Lumen memory or sent to a model merely by enabling an entry.

## Boundaries and transport

- Credentials stay within native Qt/Rust and the approved HTTPS service. The
  Python/MCP adapter sends only operation arguments and receives projected data.
- Private owned runtime socket, one active client, 64 KiB input, 3-second framing
  deadline and 90-second total request deadline. Both native code and MCP schema
  validate input; native validation is authoritative.
- Every request is bound to one entry/origin and an epoch. Approval, credential
  retrieval, dispatch and completion recheck revocation. Credential retrieval also
  rechecks the stored permission and exact profile. A disconnected
  client invalidates callbacks; rearming cannot revive an old request.
- HTTPS with normal certificate verification; root origins only, no userinfo,
  query, fragment or subpath. No redirects, environment proxies, cookie load/save,
  persistent cache, reused HTTP authentication or SSL-error bypass.
- A fresh native network manager performs only the fixed GET, with 20-second
  network deadline and a streaming 1 MiB response cap. Encoded/compressed output
  is refused. Response projection strips unapproved fields and HTML resources;
  no remote or local images/scripts are fetched or executed.
- Errors are local categories, never raw headers, network exceptions or server
  error bodies. Plain and common encoded credential reflection is rejected in
  raw and final projected output. This is defense in depth, not a guarantee
  against a malicious authorized service that already receives the credential.
- Revocation stops pending work and discards late results. It cannot retract an
  HTTP request already transmitted or data already delivered to the caller.

## Remaining production gates

`PRODUCTION_READY`, engine qualification and independent expert-review indicators
remain false. The explicit local prerelease exception does not claim OS isolation,
complete Qt memory zeroization, independent cryptographic review, or protection
against arbitrary same-user/root tools. General Lumen/OpenCode agents currently
have host capabilities. Same-user programs can contact the socket; native user
confirmation does not authenticate them and prompt spam remains possible.

The encrypted engine/fault-recovery and desktop limitations in
`SPEC-vault-secrets.md` and `native/vault-ui/REVIEW.md` remain production gates.
Production automatic/background use requires an enforceable whole-agent boundary
covering general tools, other simultaneous agents, clipboard/screen/accessibility,
config and host execution, plus independent expert review. Do not expose a generic
secret export, shell substitution, bearer grant or reusable raw HTTP proxy.

## Verification

`native/vault-ui/build.sh`: existing UI tests plus `vault-access-test`, using
synthetic credentials, temporary KDBX, private runtime, local test TLS server and
process-local test CA. Covers native intake/encrypted persistence/reference-only
results, lock/cancel/stale replies, strict routes, query encoding, invalid TLS,
redirect refusal, response size, default-Cancel approval and reflection filtering.
`files/test_vault_access.py`: non-secret schemas/adapter/private socket results and
error handling. Existing native MCP, launcher and isolated KDE regressions also run.
No authenticated test uses a credential from chat or a personal service.

## Generic profiles (supersedes the BookStack-only connection UI)

The credential is independent of the provider. The editor now has one service
address and one token-ID field, plus a connector selection (HTTPS API or remote
MCP over HTTPS) and authentication mode:

- Bearer token;
- API key in a named header;
- `Authorization: Token <id>:<secret>`;
- ID and secret in two separately named headers.

No provider is inferred from the presence of two credential parts. The previous
BookStack tool remains a compatibility adapter for its fixed read endpoints; it
does not control storage or the generic connection UI. Old dedicated address/ID
fields take precedence when populated; ordinary URL/UserName fields are fallback
sources. Saving through the new editor synchronizes them. Invalid populated
fields never silently fall back to other destinations. HTTP is not silently
upgraded or used to transmit a secret: the inline hint requires an HTTPS address.

Connect reads the saved entry directly. It does not open a setup wizard. Missing
or invalid fields produce a precise inline hint. Active state belongs to the
selected entry; selecting B does not make B appear connected merely because A is
active. Enabling B leaves A available; requests identify their intended entry.

The native request is bound to the full resolved profile, including connector,
auth mode, header names and exact endpoint. Custom header names are absolutely
anchored ASCII tokens; reserved transport/security headers and case-insensitive
duplicates are rejected. Credential values reject controls, CR/LF/NUL, with JWT
punctuation accepted. Only credential components actually transmitted participate
in response-reflection checks. Profile edits still revoke pending access.

### Generic tools

- `lumen_vault_connection`: only explicitly enabled entries' opaque references,
  endpoints and connector types, in pages of 20 (`offset` / `next_offset`). No
  credentials/header values, session IDs or discovery of unshared entries. When
  exactly one entry is available, legacy top-level metadata remains supported.
  Request tools accept `reference`; it is required when multiple entries are
  available. Unknown/disabled references fail before credentials are read.
- `lumen_vault_api_get`: GET under the configured HTTPS origin/base path, with
  constrained path segments and structured encoded query parameters. No absolute
  references, traversal, encoded delimiters, arbitrary headers or host override.
  Result is bounded untrusted JSON. Confirmation does not claim that every remote
  implementation of GET is side-effect-free.
- `lumen_vault_api_request`: GET, POST, PUT, PATCH or DELETE under the same
  configured HTTPS origin/base path. Optional object/array JSON body up to 32 KiB
  UTF-8; GET/DELETE do not accept a body. Only the method, path, query, JSON body
  and optional entry reference are caller-controlled. No headers/host override,
  credential arguments, form/multipart uploads or redirect following. Every
  request requires native confirmation with entry identity and exact
  method/URL/body in a scrollable plain-text view. Ordinary MCP action switches
  cannot bypass it. The legacy read tools remain available.
- `lumen_vault_mcp`: list tools or invoke a named tool with explicit arguments.
  Every operation has native approval showing the local entry title/reference, destination and arguments;
  calls may mutate remote state. General MCP-write disablement does not prevent
  opening this independently confirmed native operation, and does not change
  access to any other writing tool.

MCP uses initialize → initialized notification → one requested operation. Supported
negotiated versions: 2025-06-18 and 2025-03-26. JSON and bounded SSE responses are
accepted, including CR/LF/CRLF and BOM. Limit: 64 SSE events per response and 1 MiB
cumulative body data across all stages. Session IDs stay native and volatile;
subsequent requests include the negotiated protocol/session headers. No roots,
sampling, elicitation, server-request execution, destination change, reconnect or
automatic replay is implemented. Legacy HTTP+SSE, OAuth login and local stdio-MCP
credential injection are not supported. Server sessions are left to expire; the
client does not reuse or persist them.

A dispatched MCP call cannot be undone by disconnecting. Native errors after
call dispatch and client transport/decoding loss conservatively report unknown
outcome; check the service before retrying. Independent security review and
whole-agent OS isolation remain outstanding prerelease limitations.

Protocol references checked for this implementation:
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle

Regression coverage adds legacy-field activation without a wizard, selected-entry
status, missing-field hints, generic Bearer/JWT and custom headers, CR/LF rejection,
path confinement, unused-ID reflection, TLS MCP initialization/headers with JSON
and SSE, unexpected IDs/server requests, event bounds, and cancellation after a
potentially mutating call without replay.

### Persistent availability verification

`LumenApiEnabled` is a protected KDBX field, changed only by the dedicated native
broker action. Generic editing cannot write it. Missing flags stay off: old
volatile grants do not silently migrate to permanent preferences. Runtime
hydration is revision-guarded and published as one complete profile map. Invalid
enabled profiles remain visibly enabled in the UI and can always be disabled;
they cannot service requests. Editing suspends access until its dialog closes.
The selected entry title/reference is shown locally at approval and is never
forwarded as an HTTP/MCP argument. A saved permission is neither an unlocked
vault nor automatic approval. Restore-from-backup restores the backup's settings;
restoring an individual entry's historical fields instead clears its permission.

Synthetic regressions cover persisted enable/disable across unlocks, reserved
field rejection, trash/history clearing, ambiguity/unknown references, selected
credential approval, permission revalidation, bounded discovery, lock/cancel and
stale callbacks. No production qualification flag is changed.

### Generic API writes and uncertain outcomes

API writes use the same post-approval encrypted-permission/profile recheck and
native-only authentication. Successful 2xx responses return `http_status` and
bounded untrusted JSON, or null for an empty response (including204/205). A202
means accepted, not that the service has completed the operation; inspect the
response or query its state. Neither server response headers nor raw error bodies
are exported. After dispatch, lost, invalid, unsafe or interrupted responses are
reported as an unknown outcome. The Python socket client and outer MCP worker
preserve that uncertainty on disconnect, timeout, crash, oversized or malformed
output. No automatic application replay occurs. This also applies to MCP calls.

Qt's HTTP implementation can otherwise retry connection failures internally.
Mutations therefore use a sequential upload that refuses reset/seek, explicit
Content-Length even for empty requests, disabled upload buffering, HTTP/2 and
pipelining, and sendCustomRequest. The same path protects MCP tools/call. This
blocks rewinding before a transport resend. The synthetic TLS suite disconnects
both immediately after headers and after a complete request and asserts exactly
one HTTP write for POST/PUT/PATCH/bodyless DELETE. Cancellation before approval
sends no request. Unknown outcome never means that a remote change was undone.

The HTTP response remains bounded to1 MiB. Native/Python result envelopes have a
separate2 MiB budget so wrapper/JSON whitespace expansion does not turn a valid
near-limit successful write into a false failure. Real-worker socket fixtures
verify near-limit ASCII and Unicode results without touching a user service.
Tests also cover strict method/body/path validation, caller-header rejection,
body size,201/202/204/205, token reflection, invalid JSON, denied approval and
redirects. Existing TLS/certificate, lock and MCP tests continue to pass.

Implementation references (read, not copied into Lumen):
- https://doc.qt.io/qt-6/qnetworkaccessmanager.html#sendCustomRequest
- https://www.rfc-editor.org/rfc/rfc9110.html#name-successful-2xx
- https://github.com/qt/qtbase/blob/v6.11.2/src/network/access/qhttpnetworkconnection.cpp
- https://github.com/qt/qtbase/blob/v6.11.2/src/corelib/io/qnoncontiguousbytedevice.cpp
