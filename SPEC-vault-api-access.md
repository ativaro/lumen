# Vault: constrained API-token use by Lumen

Status: implementation contract draft, 2026-10-05. User selected API tokens and an own BookStack documentation service. The
complete service origin has been supplied privately and its HTTPS API verified without authentication. Authentication and read endpoints have been
verified against the official BookStack API documentation. No credentials have been requested in chat. No secret-use
endpoint is enabled by this document.

## Goal and user flow

An API-token entry offers **Mit Lumen verwenden / Use with Lumen**. A native local
form configures a service origin, authentication scheme and named operations.
The user enters the token only in the existing protected Vault field. The model
can request an operation; it must never receive or retrieve the token itself.

1. Configure a profile on an API-token entry while Vault is unlocked.
2. Select a named operation and the actual Lumen task to authorize.
3. A native confirmation shows the canonical service origin, exact operation,
   request destination, task and lifetime. Default is one request, not a durable
   app grant. The ordinary auto-approve setting has no effect here.
4. A constrained local executor obtains the secret through the existing inherited
   native/Rust channel and applies authentication only to the approved request.
5. Lumen receives a bounded, explicitly defined result. It never receives raw
   request headers, a secret export, network traces, cookies or a shell command.
6. The entry shows pending/active grants; revocation, timeout, vault locking and
   task completion invalidate unused grants. Revocation cannot undo a request
   already accepted by the remote service.

## Existing release boundary

`SPEC-vault-secrets.md` section 6 and `native/vault-ui/REVIEW.md` still apply.
The native credential engine remains an explicitly installed prerelease for
synthetic data; expert review and effective agent isolation are outstanding.
Do not enable a production secret-use MCP endpoint, change readiness constants,
or describe per-session tool permissions alone as an OS sandbox.

General OpenCode sessions currently have host tools. A separate enforceable
execution boundary is required before an agent can hold a use capability:
no host shell/filesystem/clipboard, desktop automation, process memory, raw
Vault IPC or access to another privileged OpenCode server. This protection must
also cover every concurrently available general Lumen/agent session: isolating
only the task holding the capability is insufficient. Merely hiding tool
names, asking the model not to read secrets, or using the same Unix UID does not
establish this boundary. The protected flow must fail closed if it is absent.

## Profile and request contract

- Profile metadata stays encrypted with its token entry in KDBX. No account names,
  origins, endpoints or grants in ordinary Library SQLite or QSettings.
- Origin: explicit HTTPS scheme, canonical host and port. No userinfo, fragment,
  credentials in a URL, arbitrary proxy, insecure TLS switch or redirects.
  Private PKI requires an explicit trusted CA configuration, not ignored errors.
- Authentication: first connector is BookStack (`Authorization: Token ID:SECRET`).
  Token ID and secret are entered locally and protected in the encrypted entry.
  Bearer/X-API-Key are future connector profiles. The header name and scheme are
  profile-owned, never model-controlled. Reject header control characters.
- Operations: exact named request templates. Start with a user-confirmed read
  endpoint using GET; GET alone does not prove the server has no side effects.
  No wildcard path, arbitrary URL, method, Authorization header or generic curl.
- The executor validates the final canonical URL and request after substitutions.
  Model input cannot modify scheme, authority, port, authentication or path scope.
- Grant: random opaque capability bound to profile revision, a trusted task
  identity, one operation, normalized arguments, expiry and one-use count.
  Client-supplied task/app strings are not authentication. Never persist grants
  in conversation history, memory, environment or command arguments.
- Consume before dispatch; no automatic retry after an ambiguous transmission.
  The final authorization check and transition to transmission are serialized
  with revocation in the trusted executor. Revoke/lock before this transition
  cancels DNS/connect/TLS preparation and prevents authenticated HTTP bytes from
  being submitted. If transmission won the race, close/abort the connection but
  report an uncertain remote outcome; neither TLS nor a socket abort can retract
  bytes already sent. Discard any late response after revocation.
  Revoke on profile/token edit, vault lock or task cancellation. Reject replay,
  expired grants, stale revisions and concurrent attempts beyond the use limit.
- Target service receives its token as required by its authentication protocol.
  The promise is no token delivery to the model, not that it never leaves the PC.

## Results and hostile inputs

Define an output schema with the actual service before enabling its operation.
Do not forward arbitrary response bodies or exception strings to the model.
Responses and remote text are untrusted data, never new grants/instructions.
Do not rely on keyword-based redaction as the security boundary. Provider token
reflection, redirects, malformed JSON, oversized results and authentication errors
must be covered. A schema alone cannot prevent reflected secrets in legitimate
text fields. A compromised authorized service already receives its token; no
connector can guarantee it will not exfiltrate that token itself. State this trust
assumption explicitly. Reject recognized credential reflection in whole responses
as additional defence, not a proof against arbitrary encodings. Until the service
trust and output rules are qualified, return only a fixed local status to the
agent; document-body forwarding remains disabled. Never label arbitrary remote
strings as proven secret-free. Status-only connection testing can be implemented independently
of permission to share application data with a cloud model.

No secret or unreviewed response in logs, crash recovery, clipboard, temp files,
search or Lumen memory. Qt/network allocation copies remain a documented native
memory limitation; do not claim complete zeroization from clearing a QString.

## Implementation sequence and acceptance

1. Record the service origin, read operation, auth scheme and response schema;
   use synthetic fixtures, not personal access tokens, in all repository tests.
2. Implement encrypted native profile editing and strict request validation.
   Save/cancel, DE/EN and all existing themes must work without changing backups.
3. Implement the bounded local connector and one-use grant state machine with
   real local TLS fixtures. Keep the credential transport separate from Restic's
   Python socket service. No arbitrary process/command execution by the connector.
4. Establish and test restricted agent execution and task identity; only then add
   a use-operation bridge. MCP exposes operation references/results, never tokens
   or an unrestricted list of Vault entries. Deny unavailable isolation explicitly.
5. Wire native approval/revocation into Lumen task UX, test the full flow, then
   update installation/source/license inventory and release-readiness evidence.
   Production readiness still requires the existing independent review gates.

Tests: valid request, different host/port, URL userinfo, encoded path escape,
redirect (including same-host), invalid certificate, timeout, disconnect after
send, oversized/compressed result, malicious error body, duplicate grant,
concurrent consumption, lock/revoke during request, stale profile, wrong task,
Don't-ask bypass, and attempts to use general tools or another backend server.
Observe synthetic secret canaries across MCP results, logs, persisted state and
crash artifacts; absence in ordinary success output alone is insufficient.

## Existing commands and source locations

Native UI/profile and connector: `native/vault-ui/`; Rust credential state and
private protocol: `native/vault-core/`; restricted task integration:
`files/assistant_backend.py`; current readiness-only MCP:
`files/lumen_mcp_tools.py`. New dedicated tests belong alongside each component.

```sh
./native/vault-ui/build.sh
./native/vault-ui/test-kde.sh
python3 native/vault-ui/test-launch.py
./native/vault-core/check.sh
```

Existing native build prerequisites and Rust toolchain environment are documented
in `native/vault-ui/README.md`; no new dependency has been selected yet.

## First connector: BookStack documentation

Primary reference: https://demo.bookstackapp.com/api/docs (checked 2026-10-05).
Authentication requires the account's **Access System API** permission; content
permissions follow its assigned roles. Use a dedicated account with read access
only to the intended documentation, rather than an administrative account.

Read-only connector operations:

| Operation | Fixed request | Bounded result contract |
| --- | --- | --- |
| Connection test | `GET /api/books?count=1` | Locally generated success/error category only |
| List books | `GET /api/books?count=N&offset=N` | IDs and approved display names; bounded pagination |
| Search documentation | `GET /api/search?query=...&count=N` | IDs, entity type, approved title/excerpt; no automatic URL following |
| Read page | `GET /api/pages/{positive_integer}` | Approved title and plain text; no scripts, images, external resource loading or other author metadata |

The model supplies typed operation arguments only. It cannot supply a path,
HTTP method, header, TLS option or origin. Creating/editing/deleting documentation,
attachments, users, roles, exports and audit-log access are outside this connector.
Before sending selected document contents to a cloud model, the native approval
must make that data transfer explicit. BookStack content may itself contain
sensitive material; enabling authentication is not blanket approval to index all
books into Lumen memory.

## Pending service details

- Complete HTTPS base URL: verified locally without authentication. The API book
  listing returns JSON/401 and does not redirect. The web login redirects to HTTP;
  the connector must retain its HTTPS-only/no-redirect policy. Personal hostname
  is kept out of repository defaults and fixtures.
- Authentication: BookStack token ID + secret, confirmed by official API docs.
- Fresh token: local entry only, after implementation/release qualification.
  A token pasted in chat must be revoked, never copied into source/tests/config.
- Output schema and cloud-data scope: qualify before document forwarding.
