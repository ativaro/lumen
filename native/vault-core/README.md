# Lumen Vault core — synthetic qualification milestone

**Not a released password manager. `PRODUCTION_READY` is false.** The desktop
preview remains synthetic-only. No runtime UI, MCP or agent is connected to this
crate, and the normal Lumen installer does not install this executable.

This is an actual Rust KDBX read/write implementation around the pinned,
MIT-licensed `keepass` **0.15.0** crate. Upstream still labels KDBX writing
experimental. Passing the checks below establishes a limited interoperability
baseline, not an independent audit or general import compatibility.

## Reproduce

Linux, Rust **1.89.0** (rustfmt + clippy), `keepassxc-cli` and `cargo-audit`:

```sh
cd native/vault-core
./check.sh
cargo run --locked --release
```

The executable accepts **no arguments or user-supplied passwords, paths, files or
fields**. It creates fresh private directories, exercises fixed public synthetic
fixtures, prints checkpoint labels only, then removes its test directories.
Credentials for the reference CLI go through stdin. XML export remains in RAM.
No normal user files are opened. A process failure may leave an encrypted
synthetic temporary directory; cleanup is not an erasure guarantee.

`Cargo.lock` records all transitive versions/checksums. Use `--locked` for builds;
dependency updates require re-running qualification and advisory review.
[THIRD_PARTY.md](THIRD_PARTY.md) records declared dependency licenses. Do not
infer the eventual Lumen distribution license from this inventory.

## Implemented boundary

- The storage session is crate-private. Only the fixed synthetic qualification
  routine and public-header validator are public; there is no secret-bearing RPC.
- New files: KDBX **4.1**, AES-256 and authenticated KDBX storage, Argon2id
  **64 MiB / 3 iterations / 2 lanes**. This is a fixed test profile, **not** the
  planned device-calibrated production setting. OS randomness supplies both
  library encryption seeds and the 24-character password generator (144 bits
  before any future website constraints).
- Protected fields include title, username, URL, password, notes and custom fields.
  Change history lives in the encrypted database. Lock drops the database/key and
  blocks all further field reads or saves through that session.
- Private directory 0700, files 0600, final-path symlinks/nonregular files/hard links
  rejected. One cooperating Lumen writer via a held OS file lock. Encrypted
  temporary writes, file fsync, atomic rename, directory fsync, prior encrypted
  version retained. SHA-256 revision checks reject observed external changes.
- Public-header preflight before decrypting/KDF: at most 8 MiB file, 64 KiB header,
  known AES/Argon2id profile, 64–256 MiB KDF memory, 3–16 iterations, 1–4 lanes.
  Only uncompressed input is accepted for this milestone. Compressed KDBX,
  older formats, future minor versions and public custom headers are rejected.
- Standalone probe: core dumps disabled, nondumpable process, no-new-privileges,
  512 MiB address-space limit, 60 seconds CPU and 90 seconds wall-clock deadline.
  These are **resource controls, not a completed agent sandbox**.

## Checks passed on 2026-10-04

Eight tests (six library tests and two executable tests), `cargo fmt --check`,
Clippy with warnings denied, and the standalone reference probe passed.

| Check | Evidence |
|---|---|
| Create, save, lock, reopen | Entry and encrypted history survive |
| Fresh encrypted backup/restore | Opens in a different empty private directory |
| KeePassXC 2.7.12 reads Rust output | Password, history, Unicode and custom field found in RAM-only reference export |
| KeePassXC edits; Rust reopens | Updated password, custom field and history preserved |
| Encryption parameters | Reference rewrite retains AES/Argon2id parameters; KeePassXC writes this fixture as KDBX 4.0, which the reader explicitly accepts |
| Re-save randomness | Identical logical database produces different ciphertext |
| Wrong password / corrupted ciphertext / truncation | Rejected |
| Malicious KDF values / excess file size / unknown header | Rejected before the library parser/KDF |
| Second writer / externally changed revision | Busy/conflict, no silent overwrite in tested cases |
| Actual backup rename failure | Original active file remains intact |
| Symlinks / public directory / backup overwrite | Rejected; unrelated target stays intact |
| Canary scan | No fixed fixture secrets or sensitive metadata in the test store's on-disk files or probe output |
| RustSec audit | 0 known vulnerabilities, 0 warnings; 99 packages including this crate; database revision `ef6173cbc5c50ec8166f9a5b28f07834144373ee` |

## Remaining release gates

1. **Native secure input and broker:** no real-secret UI or authenticated IPC yet.
   Keep master passwords out of the general Python/QML layer. Add session
   capabilities, lock/suspend races, and narrowly scoped native display/copy paths.
2. **Memory lifetime:** library `DatabaseKey` and protected values use zeroization;
   caller-owned secret buffers use `Zeroizing`. This does **not** prove that every
   derived-key, serializer, cipher, parser or metadata allocation is erased.
   In particular, upstream `format/kdbx4/dump.rs` uses ordinary buffers during
   serialization/key derivation. Audit and harden the full dependency path; add
   locked pages where appropriate. Rust alone is not a memory-erasure guarantee.
3. **Storage guarantees:** OS locks coordinate our writers only. Another application
   that ignores the lock can still write between the final revision check and
   rename. Until a stronger ownership/import workflow is designed, never edit an
   active store concurrently in KeePassXC or on a NAS. Failure after rename but
   before directory fsync can leave a committed file with an uncertain durability
   result; fail closed and reopen rather than promise a rollback. Actual power
   loss, full disks, directory races and filesystems still need qualification.
4. **Import coverage and resource isolation:** the tested fixture covers fields,
   Unicode, history and a reference edit. It does not certify every KDBX feature,
   malformed XML structure, attachment, icon, plugin field, nested group, TOTP or
   future-version roundtrip. An input-size limit is not a full XML parser audit.
   Aggregate edit/history limits and compressed imports need additional work.
5. **Production KDF calibration** and recovery/backup policy, native clipboard
   integration, end-to-end agent isolation, package update policy and independent
   expert review remain pending. No account/backup-keyring migration is performed.

The next implementation step is the native input/broker boundary using this
restricted tested profile, while the remaining core findings are hardened. It
must continue using synthetic fixtures until the release gates are satisfied.
