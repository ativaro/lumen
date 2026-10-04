# Lumen Vault native core

Prerelease, synthetic data only; `PRODUCTION_READY=false`. The native UI and
bounded inherited-pipe broker are described in [../vault-ui/README.md](../vault-ui/README.md).
The standalone default executable runs synthetic qualification; it accepts no
user file/secret arguments. No MCP secret endpoint is exposed.

## Storage and memory

KDBX4.1/AES256/Argon2id, private directory0700/files0600. A pinned directory inode
prevents path replacement from redirecting storage. One cooperating writer holds
an OS file lock. Encrypted temporary writes use file fsync, atomic rename and
directory fsync; previous.kdbx retains the previous encrypted active version.
Revision hashes detect observed foreign changes. Other programs that ignore our
lock may still race the last hash check: active stores must be managed exclusively
by Vault and kept local, not edited live through NAS/shared sync.

A failure after rename returns `CommitUncertain`; the UI locks and reopening
reads the actual committed state. It never promises that the old file survived
that boundary. Temporary files left by SIGKILL contain ciphertext only.

Dedicated input mappings require mlock/MADV_DONTDUMP. A broker-only allocator
uses explicit_bzero before deallocation/reallocation, including spare capacity.
Vendored parser/serializer derived-key and plaintext payload buffers use explicit
Zeroizing wrappers. This does not lock or prove erasure of all stack/Qt/cipher/KDF
working memory, old swap or hibernation. Resource limits/nondumpability are not
an unrestricted-agent sandbox. Graceful pipe EOF drops the session; SIGKILL,
abort or power loss cannot run destructors.

## Import and history

See the UI README for exact limits. Public-header checks precede KDF/decryption;
gzip and XML admission are bounded. Imported groups, fields and history are kept;
unsupported attachments/custom icons/extensions are rejected instead of silently
converted. Imports are copied into an empty private profile after authentication;
source files are never rewritten. Existing KDF parameters remain intact.
History is sorted newest first and only pruned on an explicit user command.

The local MIT-licensed keepass0.15 patch set fixes authenticated HMAC termination,
bounded decompression, strict XML admission, the inner stream ID check and selected
buffer lifetimes. Exact origin and changes are in
[vendor/keepass/LUMEN-PATCHES.md](vendor/keepass/LUMEN-PATCHES.md).

## Checks (2026-10-05)

`./check.sh` runs18 library tests,2 parser tests and3 process/reference tests.
The ignored crash-worker test is deliberately executed by the parent test in12
subprocesses with SIGKILL at six stages each for active and backup files.

Coverage: create/save/reopen/history, wrong key, corruption, exact final HMAC
truncation/trailing bytes, header/KDF bounds, XML depth/duplicate/nested-history
checks, gzip expansion, gzip/groups/custom-field roundtrip,151 entries and30
versions, oldest-first import/pruning, private permissions/symlinks, directory
replacement, conflicting writers, six write failure boundaries,12 real killed
writers, plaintext canaries, KeePassXC2.7.12 reference read/edit/reopen.

Formatter, Clippy with warnings denied,98 dependency notice records and RustSec
passed; the audit found no known vulnerability/advisory in the checked lockfile.
This is evidence for these tests, not a full audit of the cryptographic writer.

Remaining: independent expert review, broad fuzzing, actual power-loss/full-disk
and filesystem qualification, complete Qt/library memory-lifetime audit, physical
sleep/resume races, other clipboard managers and whole-agent isolation. Source
and licensing obligations are recorded in [THIRD_PARTY.md](THIRD_PARTY.md) and
[../vault-ui/LICENSES.md](../vault-ui/LICENSES.md).
