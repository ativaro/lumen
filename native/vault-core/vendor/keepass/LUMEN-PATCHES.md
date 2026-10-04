# Lumen's local keepass 0.15.0 patch set

Origin: the crates.io `keepass` 0.15.0 archive, SHA-256
`558a5ce7577f580b35aebcd6fe0e4d2995445c2bd0375bbea104952cd09ed4ae`.
Upstream VCS metadata records commit `d08c68084cd40db9bacf38dbb151d478623fda2b`
with `dirty: true`; the published archive, not a claim of an identical clean Git
commit, is the source of truth. Copyright and MIT LICENSE remain intact.
Lumen modifications dated 2026-10-05, licensed under the root MIT LICENSE.

The source, Cargo manifests, README, LICENSE and VCS metadata are retained.
Upstream examples' source is retained; their optional dependencies/features are
not enabled. Upstream external test fixtures are not bundled. Lumen executes the
exact admission/compression source in its own `tests/parser_bounds.rs` and tests
real encrypted roundtrips through the full linked crate.

Changes:

- Require the authenticated zero-length HMAC terminator and reject trailing data.
- Require the inner stream ID to contain exactly four bytes before decoding.
- Bound gzip output to 64 MiB before parsing XML.
- Streaming XML admission: 48 levels, 2 million events, bounded keys/fields,
  duplicate UUID/String/CustomData key rejection, matched history-owner UUIDs,
  no nested histories, no document types, CDATA, attachment or custom-icon data.
- Reject unknown serde fields rather than silently discard unsupported data.
- Explicit `Zeroizing` wrappers for KDBX4 derived-key and XML/payload buffers;
  enable `hybrid-array`'s zeroize feature. This is not total memory erasure.

No cryptographic algorithm has been replaced. The local changes are not an
upstream release, external audit, or production approval. The broker additionally
uses a wiping allocator, bounded imports and process resource limits. Keep the
patches, provenance, notices and regression tests when distributing this build.
