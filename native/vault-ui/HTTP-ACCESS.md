# General authenticated service access

Lumen augments OpenCode's normal tools; no new global tool deny-list. Existing explicit read-only/proposal/project/screen modes keep their boundaries. The generic service-access skill teaches discovery and verification, not a service-name router.

MCP `lumen_vault_http_open(reference, requests?)` creates one temporary native HTTP(S) session using an explicitly shared login or token entry's saved URL. Open returns the approved origin and opaque session handle, not credentials. `lumen_vault_http_request(session, method, path, body?, capture_token?)` sends one exact approved request to that origin. JSON body values `{"$vault":"username"}` / `{"$vault":"password"}` are replaced natively. The response to credential submission is withheld; cookies remain native. Optional capture_token is a JSON Pointer to a string token in the response; it is stored natively and sent as Bearer authorization on following calls. It is never returned. No fixed RPC envelope or service names: the agent constructs the documented JSON structure. Authentication submission is NOT proof of login; a subsequent bounded read must verify it. `lumen_vault_http_close(session)` discards local state, not a promise of server logout.

Trust boundaries: model-controlled request structure and remote response; native Vault credentials, TLS and same-origin policy; user-reviewed exact request. Paths must be absolute origin-relative, without authority/fragment/userinfo; redirects are not followed. Credential placeholders are permitted only in JSON body, never URL/query. No caller-selected host, TLS bypass, raw credential arguments, JS execution or local shell. Explicit confirmation for the complete exact plan, or for open and each request when no plan is supplied; entry re-read before execution, close/revoke on lock/change/expiration or disconnected in-flight IPC. The local caller is not authenticated as Lumen. One session, ten-minute lifetime; response <=1 MiB, request <=32 KiB, 30-second network timeout, no retry. Known credential/cookie/token reflections cause response withholding; arbitrary transformations by a malicious authorized host are outside this boundary.

First slice: JSON HTTP/RPC with cookie sessions and JSON bearer-token capture. HTTPS verifies certificates; stored HTTP targets require a separate unchecked plaintext-transport consent checkbox once for the exact displayed plan, or on opening and each unplanned request. No automatic downgrade. Browser tools handle HTML/forms/MFA; SSH tools handle SSH. OAuth, arbitrary header authentication, form encoding and cross-origin SSO are not silently simulated. No change to the saved entry type or URL is required.

Acceptance: synthetic HTTPS RPC and REST login sequences; exact credential injection; cookie/token retention; origin/redirect/TLS rejection; deny/revoke/source-change; unknown outcome; response reflection and size limits; native IPC consent; installed tool discovery. OpenMediaVault is a read-only real acceptance target, never production-specific code. Live authentication requires its native approval; no password extraction or bypassing that approval for tests.

## One approval for a bounded request plan

`http_open(reference, requests?)` accepts an optional ordered list of 1–12 exact
requests (method/path/body/capture_token), at most 32 KiB combined. The native
dialog shows the target and complete plan once, including one explicit HTTP-risk
checkbox for that plan. Approval executes nothing yet. The existing request tool
executes each matching next step once, after re-reading the current entry.
A mismatch clears the remaining plan and needs individual approval; reordering,
changed bodies/capture pointers, replay and extra calls never inherit approval.
Transport errors or non-2xx responses clear the remainder. Lock, revocation,
expiration and entry changes keep their existing fail-closed behavior. Responses
remain untrusted; the caller must inspect RPC errors before continuing.
Old callers without a plan keep individual approval. No persisted permissions,
new secret exports, service-specific code or changes to browser/SSH/API approvals.
Acceptance: one dialog for open+login+several reads; modified/out-of-order/replayed
steps prompt again; denial, source changes, lock and uncertain outcomes stop grants.
