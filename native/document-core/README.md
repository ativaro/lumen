# Lumen document core

Lumen's own document reader in Rust, without Qt, a server or an office suite.
`PRODUCTION_READY=false`: the crate is built and compared here, but the installer does not
ship it yet and the Reader still uses `files/lumen_office.py`.

## What it does today

`lumen-document office <file> [--label German=Translation]...` reads `.docx .docm .xlsx .xlsm
.pptx .pptm .odt .ods .odp` and prints `{"title": ..., "sections": [...]}`: one HTML section per
document, sheet or slide, with headings, emphasis, lists, tables and pictures. Pictures are
referenced by their name inside the file; nothing outside the file is read. XML entity
declarations, encrypted parts and oversized archives are refused. Error messages are the German
source texts, which the caller translates.

PDF follows; see `PLAN-dokument-kern-rust.md` in the working folder of the migration.

## Checks

```bash
python3 check-licenses.py
cargo fmt --check
cargo clippy --locked --release --all-targets -- -D warnings
cargo test --locked --release
python3 compare.py target/release/lumen-document ../../files <office files>...
```

`compare.py` is the acceptance check of the migration: for every file the title and every
section must equal what the Python reader produces. It prints outcomes and run times only.

## Dependencies

Only licences that can be used freely without buying or separately licensing them are accepted
(MIT, Apache-2.0, BSD, Zlib, ISC and the like); `check-licenses.py` fails on anything else.
A part without such a building block is written in this crate. Direct dependencies: `roxmltree`
(XML tree) and `zip` (archive, Deflate only).
