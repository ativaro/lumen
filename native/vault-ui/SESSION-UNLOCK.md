# Session comfort and local browser unlock

Default: 15 minutes of human desktop inactivity; 5 and 30 minutes selectable.
Screen lock, suspend, broker failure and explicit lock clear native state and
retire the process. Closing an unlocked window hides it, clears revealed values
and owned clipboard, and leaves a tray indicator. Locked close exits. Hidden
retirement must not reveal a window. Existing per-tool native consent remains.
The existing screenshot exclusion lease stays in force while this process runs,
including when hidden. For Lumen screen analysis, use the tray action Lock and
quit first. No request or background job counts as human activity. KIdleTime resume events
are used because Wayland does not support idleTime polling. Missing compositor
support falls back to spontaneous Vault input and a finite timeout. The broker
still exits after five minutes without its native parent sending a request;
UI liveness sends a data-free keepalive once per minute while unlocked.

## Passkey trust boundary

Only a native UI action starts enrollment/unlock. The external browser's passkey
provider must return a 32-byte WebAuthn PRF result with user verification. The
browser derives 32 bytes through HKDF-SHA256, using a random salt and a per-link
binding. The native broker uses that high-entropy value as the password of a
separate KDBX wrapper containing the validated master password. Credentials never
leave the native broker for the browser. Neither the derived key nor master
password is stored in plaintext. Metadata and wrapper are private local files
under the existing vault root's passkey/ directory, separate from the synced
primary vault. Existing master-password unlock remains available.

A loopback-only HTTP listener uses a random port and a 256-bit transaction token
passed in the URL fragment, removed from browser history immediately. Private
requests require the token header; POST also requires the exact Origin. Exact
Host, finite time/body/socket limits, no CORS, no cache, restrictive CSP and no
remote assets. Browser keys are never URL parameters or logs. Each successful
handoff is one-shot; timeout/cancel/lock close the listener. Native checks include
challenge, origin, RP hash, expected credential id and user-present/verified bits.
These assertion checks are defense in depth, not a full public-key signature
verifier: successful KDBX decryption with the derived secret is the unlocking
proof. Enrollment requires a native master-password check. No agent/MCP endpoint
can create these flows.

The browser, extension and OS user session are additional trusted components.
This is not hardware isolation. WebAuthn RP IDs do not distinguish localhost
ports; another local app with access to the private metadata could request the
same credential and trick the user into approving it. A compromised same-user
process/browser or root is outside this protection boundary. Only start passkey
confirmation from Lumen Vault. Other websites cannot read the local handoff.
JS/native allocations are cleared where controllable, but zeroization of all
browser/Qt copies cannot be guaranteed. No silent authentication or cloud key
escrow is added; the user's passkey provider may itself synchronize credentials.

Removing the local wrapper does not revoke old copies/backups or delete the
provider's passkey. The primary vault is never deleted. The encrypted wrapper is
not included in the existing primary-file server sync; restore uses the master
password and requires fresh passkey setup. Existing plaintext credential files
are untouched: migrating each caller needs its own verified import.

Tests: Rust encrypted wrapper, bad password/key and recovery; native loopback
origin/token/challenge/UV/credential/replay boundaries; native UI enrollment and
unlock against a synthetic browser handler; JS provider variants with real
WebCrypto and fake authenticators. Personal Proton Pass enrollment needs a human
confirmation and must be separately reported from these synthetic tests.
