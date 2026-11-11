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
content. The Reader reads PDFs through `pdf-reader` (see below).
`compare-pdf.py` runs both readers over the same files and requires equal results or the same
refusal: 40 real files with 1419 pages are equal.

`lumen-document pdf-words <file> <first page> <count>` reads the words of pages with their
positions (`src/text.rs`): fonts with their widths, encodings and ToUnicode maps, the text
operators, forms, layers and replacement text. `compare-words.py` requires the same words, order
and lines as the Python engine, with positions within half a pixel: 418 pages of the 40 real files
are equal. Drawing operators are passed over in this pass, so a page whose drawing the Python
engine refuses is still read here.

`lumen-document pdf-render <file> <page> <scale> <png>` draws a page (`src/render.rs`): paths,
text as glyph outlines, pictures, forms with transparency and knockout groups, clipping, shadings,
shading and tiling patterns, and annotations. `compare-render.py` draws the same pages with both
engines and compares reduced grey pictures: of 418 pages of the 40 real files, 417 are equal and
one is refused by name (a four-channel JPEG picture). Drawing those pages takes 16 s here and 50 s
in the Python engine, with a process start and a PNG file per page on this side.

Soft masks, Type 4 functions (`src/calculator.rs`), matte pictures, knockout groups and stroke
adjustment are drawn as the Python engine draws them.

Encrypted files open with the standard security handler, revisions 2 to 6 (`src/security.rs`); a
password reaches the program on standard input when `LUMEN_PDF_PASSWORD_STDIN` is set. Embedded
Type 1 font programs are read by `src/type1.rs`. Four-channel JPEG pictures go through
`jpeg-decoder`. An sRGB colour profile is used as it is.

Checked against the Python engine on 78 real files: structure equal for all, words and pictures
equal on all 646 pages that both draw.

Refused by name, and then read by the Python engine: colour profiles other than sRGB, JPEG 2000
pictures, stroking with patterns, radial shadings between two offset circles, transparency groups
in grey outside a mask, and non-ASCII passwords of revision 6.

`lumen-document pdf-reader <file> metadata | page <index>` is what the Reader asks: page count,
title and outline, and for a page its words and its picture as PNG. `files/reader_data.py` calls it
in the Reader's own job thread, without a Python worker. When the core refuses a file or a page,
the Reader falls back to the Python engine (`files/lumen_pdf*.py`), which also still does everything
that writes PDFs. That fallback is the transition named in the migration plan; it ends when the
list above is empty.

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
(XML tree), `zip` (archive, Deflate only), `flate2` (Deflate for PDF streams), `ttf-parser` (font tables),
`tiny-skia` (rasteriser), `zune-jpeg` and `jpeg-decoder` (JPEG pictures), and `md-5`, `sha2` and
`aes` (primitives for encrypted files).
