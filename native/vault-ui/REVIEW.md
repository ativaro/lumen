# Review handoff — release remains closed

Scope: native/vault-core + native/vault-ui, launcher `--lab`, optional native
button in tools_vault.py, and readiness-only MCP. The legacy synthetic QML preview
and Restic backups remain separate. All tests use public synthetic values.

## Implemented trust boundary

Native Qt widgets -> QProcess-owned anonymous stdin/stdout pipes -> Rust Session.
The inherited descriptors are the capability; there is no reconnect service or
UID-only authentication. Requests/replies are bounded binary frames, exact length
and count checked, with command-specific validation. IPC requests never traverse
Python, a shell, chat history or MCP. Child exit, malformed frames and failed
operations lock the UI. No secret or document paths in error messages.

Persistent plaintext is restricted to code, settings for appearance/language,
fixed filenames and license documents. All entry fields/history are inside KDBX.
A held directory descriptor pins the storage inode, a file lock coordinates our
writers, hashes detect observed foreign edits, and encrypted fsync/rename writes
retain the previous encrypted version. Uncooperative external writers can still
race the last hash check; active files must remain exclusively managed by Vault.

## Required before real credentials

1. Independent expert review of the full Rust library and native UI/IPC boundary,
   including `keepass`'s experimental writer, parser/serializer/key-buffer lifetime,
   Qt/QProcess allocation copies, memory locking and crash/failure behavior.
   Current zeroization is **best effort**, not proven total erasure.
2. Broader fuzzing and fault/power-loss tests on supported filesystems, including
   errors after rename but before directory fsync and external noncooperating writers.
   Existing deterministic corruption/KDF/framing/failure tests are a baseline.
3. KDE/Wayland lock/suspend/reveal/clipboard races, actual Klipper history behavior,
   accessibility/screen-analysis exclusions and alternate clipboard managers. The
   automated native tests cover handlers and offscreen clipboard ownership only.
4. Whole-Lumen agent isolation before any claim that an unrestricted agent cannot
   obtain screen/clipboard/process data, and before any connector secret-use API.
   The current MCP endpoint returns readiness constants and exposes no secret API.
5. Production UX/policy for history retention, broad KDBX import profiles, recovery
   documentation, larger vaults and new dependency/source distribution obligations.

Do not remove the explicit laboratory flag, install in the default production
wizard, set PRODUCTION_READY, or label this audited merely because these tests pass.
No personal credentials, encrypted user vaults, logs or screenshots belong in the
review source bundle. Licensing checks cover the collected native dependencies;
proprietary redistribution of all Lumen remains subject to LICENSE-PLAN.md.
