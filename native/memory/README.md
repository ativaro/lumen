# Lumen memory search

`lumen-memory` is Lumen's one implementation of how the memory and Notes search split, fold and rank
text. The server uses it for memories and notes (`rust/src/memory_retrieval.rs`), the entries of its
meaning search (`rust/src/worker/encoder.rs`), its Notes tags and the fingerprints of forgotten texts;
the desktop's service `lumen-service` (`native/service/src/recall.rs`) uses it for the memory,
in place of the earlier `files/memory_core.py`. The server keeps a pinned, hash-checked copy in `rust/shared/memory`
(`scripts/update_shared_crates.py`).

Callers hand in rows they have just authorized; neither text nor meaning scores grant access to a
source. Storage, access rules, the meaning search (`native/sentence-encoder`), excerpts and context
assembly stay with each side.

## Contents

- `Entry`: one memory or note as a caller hands it to the search (`id`, `title`, `text`,
  `revision`, `boundary`; `kind` fact, `project`, `status` active, `allowed`, `updated`,
  `correction`, `supersedes`); unknown fields are refused. `valid()`: identity, revision and boundary
  present, at most 500 title and 20000 text characters, a known kind and state.
- `eligible(entries, boundary, project)`: the allowed, active, not replaced entries of a boundary,
  general or of that project, in their order.
- `unicode`: Python 3's identities at Unicode 16.0.0, independent of Rust's Unicode version:
  `word` (`str.isalnum()` or `_`), `digit`, `wide` (East Asian width W/F), `whitespace`
  (`str.isspace()`), `search_fold` (NFKC, then case folded) and `tag_fold` (NFC, then case folded,
  the identity of a Notes tag). The ranges in `src/unicode_data.rs` are written by
  `generate_unicode.py`.
- `terms(text)`: the search terms: folded words without `_`, joined by a single `-`, `.` or `/`
  between word characters; runs of wide characters also yield their character pairs.
- `Ranking<K>`: `new(query)`, `push(key, title, text, updated, correction)` per row, then
  `ordered(semantic, first, browse)`: word scores (rarity, title terms ×3, term counts, share of query
  terms, +4 when the title contains the query), optionally fused by reciprocal rank with meaning
  scores by `key`; ties go to corrections, then newer rows, then the smaller key. Equal folded texts
  appear once. `first` places rows before the ranking (the desktop's reserved preferences);
  `browse` makes an empty query list every row, newest first (the server). `rows[i].literal_body`
  says whether the text contains the query (`mentions`).
- `mentions(text, query)`: whether the text already contains the trimmed query, case folded only.
- `fingerprint(text)`: the SHA-256 (hex) of the folded words of a forgotten text.

## Checks

```bash
python3 ../document-core/check-licenses.py .
cargo fmt --check
cargo clippy --locked --offline --release --all-targets -- -D warnings
cargo test --locked --offline --release
python3 generate_unicode.py && git diff --exit-code src/unicode_data.rs   # Python with Unicode 16.0.0
```

The dependencies (caseless, unicode-normalization with tinyvec, serde, sha2; serde_json for the
tests) are frozen in `../service/vendor`; the build never reaches the network. A test compares word,
digit, case folding, NFC and NFKC of every Unicode scalar with the digest Python wrote into the data
file.
`tests/golden.json` holds outputs recorded from the code the crate replaces, for the same inputs
(German, English, CJK, Hangul, emoji, combining marks, numbers, separators, empty and long texts,
ties, duplicates, meaning scores, random rows; valid and invalid entries, replacements): the server's
`rust/src/memory_rank.rs`, `note_unicode.rs`, fingerprint and the entries of `worker/encoder.rs` at
50d57c35 and the desktop's `files/memory_core.py` and `lumen_memory.fingerprint` at 61ff3bff. Both
gave the same entry checks, eligibility, terms, folding, fingerprints and rankings;
they differ only where the desktop's `search` has options the server lacks (reserved preferences,
an empty query without `browse`, fusion with an empty score map), which `first`, `browse` and
`Some`/`None` for `semantic` express.
