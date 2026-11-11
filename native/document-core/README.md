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

`lumen-document pdf-info <file>` reads a PDF's structure (`src/pdf.rs`): syntax, cross-reference
tables and streams, object streams, the stream filters, the page tree, document information and the
outline. It prints page count, title, outline and, per page, its box and a checksum of its decoded
content. The Reader does not use it yet; it still reads PDFs with `files/lumen_pdf*.py`.
`compare-pdf.py` runs both readers over the same files and requires equal results or the same
refusal: 40 real files with 1419 pages are equal. Not ported yet: encrypted files (refused with a
clear message), text and words, rendering.

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
