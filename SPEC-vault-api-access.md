# Vault: native credential intake and constrained credential use

Status: manually approved prerelease, 2026-10-05. The user explicitly accepts
trying the installed native Vault before production qualification. The primary
requirement is encrypted credential storage instead of passwords/tokens in
Markdown files. BookStack is the first read-only integration used to exercise it.
No personal hostname, token or vault data belongs in source or test fixtures.

## Native storage flow

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
**Mit Lumen verwenden / Use with Lumen** to enable that selected entry for at
most five minutes while unlocked. A second click ends access. Editing, opening
history, trashing/restoring, locking, expiry and profile changes revoke access.
Only one entry is enabled, and only one request can be pending.

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
- Private owned runtime socket, one active client, 4 KiB input, 3-second framing
  deadline and 90-second total request deadline. Both native code and MCP schema
  validate input; native validation is authoritative.
- Every request is bound to one entry/origin and an epoch. Approval, credential
  retrieval, dispatch and completion recheck expiry/revocation. A disconnected
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
