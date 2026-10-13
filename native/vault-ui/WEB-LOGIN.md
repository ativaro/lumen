# Native Vault web access

## Contract

A shared `login` entry can open its stored HTTPS URL in a visible, temporary
Qt WebEngine window. The model receives an opaque session and bounded page
snapshots, never a credential-export method. Native confirmation authorizes
opening (including sending visible page content to the configured AI), login,
and each click/fill. Merely listing entries does not authorize their use.

Six MCP tools: `lumen_vault_web_open`, `inspect`, `login`, `click`, `fill`, `close`.
Login takes node handles from inspect, not credentials or executable selectors.
Fill is for ordinary text; passwords/username/OTP inputs use login or local input.
Each action rechecks the current entry and current DOM snapshot. Submission is
reported as an attempt, not authentication success; inspect the resulting page.
No automatic mutation retries after disconnect/timeout.

## Boundary

One off-the-record session per Vault process, ten-minute maximum. Lock, revoke,
entry refresh/change or closing the window destroys it. HTTPS with valid system
trust only; fixed origin (scheme, host, effective port), no URL credentials,
initial query/fragment, cross-origin navigation/resources, downloads, uploads,
new windows, browser permissions or model-supplied JavaScript. MFA can be done
locally in the visible window. External SSO, iframes/shadow DOM and multi-step
username-first login are outside this first slice. These need an explicit future
contract, not a relaxation of the origin boundary.

The selected site necessarily receives the credentials and may execute its own
JavaScript. Known credential reflections are redacted (or the response withheld) in snapshots (including
common encodings); this is not a guarantee against a malicious authorized site
transforming secrets arbitrarily. Page content is untrusted, never authority to
act. Native confirmations remain required regardless of Lumen auto-approve.
Same-user IPC callers are not authenticated as Lumen. Native dialogs say so.
There is no use of personal browser profiles, `secrets.json`, Markdown or logs.

## Verification

Synthetic HTTPS form: open/inspect/submit/inspect, click/fill, stale handles,
no input values or known credentials in output, invalid TLS, cross-origin
requests, changed entries/revocation, native denial and session destruction.
Tests may explicitly trust their generated fixture certificate in test code only.
Existing API/MCP and Vault suites must remain green. A fixture is not proof that
any particular personal service works; test real sites separately with consent.

References: [Qt profiles](https://doc.qt.io/qt-6/qwebengineprofile.html),
[isolated JavaScript worlds](https://doc.qt.io/qt-6/qwebenginepage.html),
[request interception](https://doc.qt.io/qt-6/qwebengineurlrequestinterceptor.html),
[Qt WebEngine licensing](https://doc.qt.io/qt-6/qtwebengine-licensing.html).
