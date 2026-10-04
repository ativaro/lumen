# Native Lumen Vault

A functional **prerelease**, normally tested with synthetic credentials. The user
explicitly opted into local native intake/BookStack evaluation before qualification.
Independent expert review is pending; `PRODUCTION_READY=false`. The compact unlock/about notice is
intentional. Diagnostic and backup controls no longer dominate the main view.

## Build and installation

Linux, C++17, CMake, dynamic Qt 6.5+ Core/Gui/Widgets/Network/DBus, the system Qt SVG icon
plugin, Qt Test for tests, and Rust **1.89.0** with rustfmt/clippy:

```sh
./native/vault-ui/build.sh
./native/vault-ui/install-laboratory.sh
lumen-vault
```

Installation remains explicit and user-local. If that native installation exists,
`lumen-vault` opens the native three-column vault. `lumen-vault --lab` remains an
explicit alias. `lumen-vault --backups` selects Backups in the same native
window. Both tabs are retained widgets: selection and snapshots survive switching,
with no second application window or focus handoff. Subsequent launches activate
the existing native instance. Legacy explicit interop/handoff CLI arguments still
use the established Python review dialogs; fresh production installs without the
explicit native prerelease retain the Python backup application.

The backup page uses the installed Lumen Python runtime and headless
`files/vault_service.py` (PySide6 Core/Network). The service reuses Restic, keyring,
Library, source-consistency and schedule code. It has one service-owned job,
private owner-only local IPC, bounded requests/results and request IDs; it survives
credential process retirement and reconnects without replaying mutations.
Scheduled/legacy jobs remain separately protected by existing per-plan leases.
Only backup requests cross this socket; KDBX credentials continue exclusively
through the Rust broker's anonymous pipe. A tab switch does not lock the vault;
it hides revealed secrets and clears its owned clipboard. Backup activity does
not extend the credential idle timeout. Actual credential lock still retires the
GUI and cancels any unsent backup dialog; accepted jobs continue. No existing data
is migrated. Restores remain isolated new folders; advanced app-data merge dialogs
remain available through the legacy backup workflow.

Binaries/source/notices: `$XDG_DATA_HOME/lumen/vault-lab`, default
`~/.local/share/lumen/vault-lab`. Encrypted test store:
`$XDG_DATA_HOME/lumen-vault-lab` (0700, files 0600). Neither belongs in Git.
`XDG_RUNTIME_DIR` must identify an absolute, private directory owned by the user.

## User interface and working flows

- Four themes, German/English; the approved three-column desktop layout with
  a Lumen mark, centered section navigation, distinct title/subtitle rows,
  collection separators and integrated reveal/copy actions. Detail fields scroll
  at smaller window heights; labels and icons remain native, keyboard-accessible
  controls. Recovery codes and Trash remain available in Settings.
- Collections and entry details come from the encrypted store. App access shows
  actual temporary BookStack access status; no invented modification date is displayed. Version history remains directly available.
- Login, token, note, recovery codes, custom fields, trash, collections and tags.
  Expiry/permissions are notes, not verification against the provider.
- Masked secrets, explicit 10-second reveal, 24-character OS-random generator.
- Explicit copies and note cut/copy use KDE's sensitive MIME hint, ownership tag
  and 20-second clearing timer. Other clipboard contents are left alone.
- Five-minute idle lock, screen lock, suspend and broker failures lock the UI.
  Lock hides the window first, clears models/dialogs, closes the private pipe
  gracefully, and retires the desktop UI process before opening a locked window.
  A hung broker is killed after the bounded graceful wait.
- History lists timestamps, opens masked prior fields, restores selected fields,
  or explicitly retains a chosen number of newest versions. Imports are sorted
  by modification time; unknown timestamps sort last. No silent automatic pruning.
- Up to 10,000 entries, 64 entries per IPC page, 1,000 historical versions per
  entry, 64 stored fields, 32 changed fields/request, 16 KiB/value, 32 KiB/edit,
  16 MiB aggregate logical field data, 64 MiB encrypted/decompressed file.
  Limits fail closed. Version pruning frees history capacity explicitly.
- Restore/import into an empty profile after password validation. KDBX4.0/4.1,
  AES256, Argon2id (8–256 MiB, 1–16 passes, 1–4 lanes), gzip or uncompressed,
  nested groups, ordinary/custom fields and histories. KDBX4.0 is resaved as4.1.
  Attachments, custom icons, unknown XML/header extensions, keyfiles and other
  cipher/KDF profiles are rejected. This is a bounded import profile.
- New stores calibrate Argon2id near 800ms with 128 MiB/2 lanes/3–16 passes.
  Existing/imported KDF parameters are preserved. The source file is not changed.

## Protection boundaries

Credential widgets communicate only through inherited anonymous pipes with the Rust
child. The separate Restic service handles backup metadata and backup passwords only. No secret endpoint in MCP/Python/QML, no drafts or global index. Both
processes disable core dumps, are nondumpable and set no-new-privileges.
Input frames have dedicated locked/no-dump mappings. Rust heap deallocation and
reallocation wipe their owned storage; selected library key/payload buffers have
explicit zeroizing lifetimes. Qt/stack/cipher/Argon allocations are not all locked
or proven erased. Process retirement is not erasure of old swap or hibernation.

Notes export empty PRIMARY MIME; masked password fields and nonselectable reveals
do not copy PRIMARY. **Visible editable metadata such as titles/usernames may
still use Qt's ordinary PRIMARY selection.** Do not place secrets in these fields.
This is a remaining release boundary, not a claim of complete clipboard isolation.
KDE hints cannot stop arbitrary other clipboard managers from collecting secrets.

Lumen's Spectacle/MCP capture paths hold an exclusive runtime-file lease; native
Vault windows hold a shared lease for their entire lifetime. Close Vault before
Lumen screen analysis. This is cooperative exclusion, not protection from root,
accessibility tools, other screenshot applications or an unrestricted agent.
Protected MIME is refused by Lumen/Translate clipboard actions and text editors,
and Search paste actions. No content is sent to an LLM by Vault itself.

## Verification

`build.sh`: same-window tabs/retained selection plus native flows for queued requests and create/edit/copy/lock/reopen
with the real broker, clipboard
ownership, notes paste/IME bounds and plaintext canaries. `test-kde.sh`: isolated
KWin/Xwayland/Plasma/Klipper session with temporary HOME/config/data/runtime;
checks real PRIMARY selection, history hints and D-Bus screen-lock/suspend signals.
No lock/suspend or clipboard changes are applied to the user's desktop.
This does not simulate physical suspend/resume or every manager/platform race.

`../vault-core/check.sh`: Rust tests, exact parser regressions, KeePassXC reference
roundtrip, write-failure and subprocess SIGKILL tests, formatting, Clippy, license
inventory and RustSec. `LUMEN_VAULT_CAPTURE=1 build/vault-ui-test` renders four
synthetic theme screenshots under `/tmp`. See [REVIEW.md](REVIEW.md) for remaining
release gates and [LICENSES.md](LICENSES.md) for distribution obligations.

`files/test_vault_service.py` covers real Restic create/preview/backup/restore with a
synthetic repository and in-memory keyring, and separate-process socket reconnect,
request deduplication, cancellation and singleton ownership. Set
`LUMEN_TEST_RESTIC` to an installed Restic binary. Tests never use personal plans.

`python3 native/vault-ui/test-launch.py` checks real native singleton activation
and cold helper startup without a Lumen executable on PATH, in temporary HOME and
XDG directories. It terminates only the processes created by that test.

## Native credential intake and BookStack (explicit local prerelease)

Lumen can open the native editor using `lumen_vault_store` with only a title and
kind. Unlock Vault locally, then enter the password/token in its native form.
The tool receives only a saved reference, never the credential. Existing
plaintext chat cannot be made private retroactively. No Markdown credential file
is created. This is also available by manually choosing New entry in Vault.

For the BookStack test connector, choose API token and enter the optional HTTPS
origin, token ID and secret (Password/token field). Use with Lumen enables that
entry for up to five minutes. Every `lumen_bookstack_read` request separately
asks native approval and returns only bounded read results. No write/delete
operation exists. End access, lock, edit or expiry revokes pending access.
The approval identifies a local program, not a verified app identity. Read
results may reach the configured cloud model; the token stays local except for
authentication to the approved service. The independent-review/production flags
remain false; whole-agent isolation is outstanding. See `SPEC-vault-api-access.md`.

A submitted Save is a commit request: closing an IPC client or locking cannot
reliably undo a write already sent to Rust. If a save is interrupted, check Vault
before retrying; do not assume failure means no entry was stored.
