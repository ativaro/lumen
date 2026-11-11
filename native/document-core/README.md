# Lumen document core

Lumen's own document reader in Rust, without Qt, a server or an office suite.
The installer and the Arch package build it with `native/build-document.sh` from the frozen
sources in `vendor/`; `files/lumen_office.py` starts it for the Reader.

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
```

The Reader's behaviour is checked end to end by `files/test_lumen_office.py`. Before the Python
parser was removed, its output was compared with this crate's file by file: title and every
section were equal for 40 real and 4 synthetic files.

## Dependencies

Only licences that can be used freely without buying or separately licensing them are accepted
(MIT, Apache-2.0, BSD, Zlib, ISC and the like); `check-licenses.py` fails on anything else.
A part without such a building block is written in this crate. Direct dependencies: `roxmltree`
(XML tree) and `zip` (archive, Deflate only).
