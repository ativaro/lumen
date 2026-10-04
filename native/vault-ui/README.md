# Native Lumen Vault laboratory

A functional **pre-release laboratory for synthetic credentials only**. It is
not approved for real passwords, tokens, recovery codes or private notes.
`PRODUCTION_READY` remains false; independent expert review has not taken place.

## Build and run

Linux, C++17 compiler, CMake, dynamically installed Qt 6.5+ Core/Gui/Widgets/DBus
and Qt Test, Rust **1.89.0** with rustfmt/clippy. The isolated developer toolchain
can be used by setting CARGO_HOME/RUSTUP_HOME/PATH; these are not product requirements.

```sh
./native/vault-ui/build.sh
./native/vault-ui/build/lumen-vault-lab --laboratory-only
```

The application accepts only the laboratory flag, never passwords on the command
line. Its child broker is a sibling executable. No service, open port or named
socket is installed. Both processes disable core dumps and set nondumpable and
no-new-privileges. This does not sandbox an unrestricted desktop agent or root.

For a deliberate per-user installation:

```sh
./native/vault-ui/install-laboratory.sh
lumen-vault --lab
```

The updated backup window then offers **Tresor · Testversion**. Fresh installs
without the explicit native build keep **Tresor · Vorschau**. Restic plans,
keyring credentials and existing backup behavior are unchanged. No production
installer or MCP tool enables the laboratory automatically.

Binaries and rebuildable source/notices install beneath
`$XDG_DATA_HOME/lumen/vault-lab` (default `~/.local/share/lumen/vault-lab`). The
separate test database lives in `$XDG_DATA_HOME/lumen-vault-lab`, directory 0700,
files 0600. Neither location belongs in Git. Removing the program does not remove
the encrypted database. No existing credentials are imported automatically.

## Working flows

- Create with a confirmed master password, reopen, lock. No password-reset service.
- Native C++ input/edit/display, no plaintext in Python, QML, general Lumen models,
  settings, logs, draft recovery or global search. Qt still makes internal copies;
  no claim that every RAM allocation has been securely erased.
- Login, API token, secure note, recovery codes, collections, favorites, trash,
  tags, expiry/permission notes and protected custom fields. Metadata is encrypted
  alongside secrets. Permissions/expiry fields are user notes, not provider checks.
- OS-random 24-character generator. Masked secrets; explicit reveal for 10 seconds.
- Explicit copy with KDE's sensitive MIME hint; clears after 20 seconds or on lock
  only if our ownership tag is still present. Other clipboard contents are left
  alone. No PRIMARY writes. Other clipboard managers need their own validation.
- Five-minute inactivity, screen-lock and suspend handlers; broker independently
  expires its idle session. Lock destroys models and open edit dialogs. No drafts
  are saved. Broker disconnection/malformed replies/timeouts lock the UI.
- Encrypted export to a new private folder and restore into a fresh empty test
  profile after password validation. Existing active files are never overwritten
  by restore. Restoring requires the original master password.
- Encrypted change history is preserved by the library, currently capped at 20
  revisions per entry (then edits fail closed); history browsing/pruning is not
  yet exposed. Max 100 entries, 32 edited fields, 16 KiB per value, 32 KiB per edit,
  8 MiB encrypted file. Full-size production scalability is not claimed.
- Imported files are deliberately restricted: uncompressed KDBX4.0/4.1 AES256 /
  bounded Argon2id, no nested groups or current attachments. This is backup restore
  for this laboratory, not a general KeePass import wizard.
- New laboratory files calibrate Argon2id toward ~800ms on the machine, using
  128 MiB, 2 lanes, 3–16 passes. This is an estimate, not a timing guarantee.
  Reopening/restoring never silently weakens an existing KDF profile. The separate
  reference probe keeps its fixed 64 MiB / 3-pass test fixture for repeatability.

## Verification

`build.sh` runs native Qt tests against the real Rust process: create/save/copy/
lock/reopen, plaintext canaries, clipboard ownership and destruction of locked
models. Optional `LUMEN_VAULT_CAPTURE=1` on `vault-ui-test` renders all four themes
to `/tmp/lumen-vault-native-*.png` using only synthetic data. Tests use temporary
profiles/settings. `../vault-core/check.sh` adds Rust tests, KeePassXC roundtrip,
formatter, Clippy, license-inventory verification and RustSec audit.

Tests exercise handler behavior and offscreen clipboard semantics, **not** a
completed full KDE/Wayland/third-party-manager security certification. See
[REVIEW.md](REVIEW.md) for remaining release gates and [LICENSES.md](LICENSES.md)
for exact license scope and Qt replacement/rebuild rights.
