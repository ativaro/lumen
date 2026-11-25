# Lumen document core

Lumen's own document reader and PDF writer in Rust, without Qt, a server or an office suite.
It is the only PDF engine of Lumen Desktop: Reader, Files, search, the knowledge index, text
recognition, the PDF workshop and PDF translation all go through it. The installer and the Arch
package build it with `native/build-document.sh` from the frozen sources in `vendor/`;
`files/lumen_office.py` finds and starts it.

## Commands

`lumen-document office <file> [--label German=Translation]...` reads `.docx .docm .xlsx .xlsm
.pptx .pptm .odt .ods .odp` and prints `{"title": ..., "sections": [...]}`: one HTML section per
document, sheet or slide, with headings, emphasis, lists, tables and pictures. Pictures are
referenced by their name inside the file; nothing outside the file is read. XML entity
declarations, encrypted parts and oversized archives are refused.

`lumen-document pdf-info <file>` reads a PDF's structure (`src/pdf.rs`): syntax, cross-reference
tables and streams, object streams, the stream filters, the page tree, document information and the
outline. It prints page count, title, outline and, per page, its box and a checksum of its decoded
content. A file whose cross-reference is missing, cut off or wrong is read from its objects, as
other readers do; bytes before the header and lines behind the end are passed over.

`lumen-document pdf-words <file> <first page> <count>` reads the words of pages with their
positions (`src/text.rs`): fonts with their widths, encodings and ToUnicode maps, embedded Type 1
programs (`src/type1.rs`), Type 3 fonts, the text operators, forms, inline images, layers and
replacement text. A glyph name is read by the rules of the Adobe Glyph List; a character nothing
names reads as U+FFFD, and a glyph the font lacks is left out of the picture, neither refuses the
page.

`lumen-document pdf-render <file> <page> <scale> <png>` draws a page (`src/render.rs`): paths,
text as glyph outlines, pictures (JPEG, JPEG 2000, CCITT fax, JBIG2, Flate and the other filters),
colour spaces with ICC profiles, forms with transparency, knockout and grey groups, soft masks,
clipping, shadings including radial ones between any two circles, shading and tiling patterns for
fills and lines, Type 4 functions (`src/calculator.rs`) and annotations. Large pages are drawn in
bands on several processor cores. A picture whose data are damaged or end before its last row is
refused with its page, not drawn in part.

`lumen-document pdf-reader <file> metadata | page <index>` is what the Reader asks: page count,
title and outline, and for a page its words and its picture as PNG. `pdf-cli text|info|render` is
the same for Files, search and the workshop.

`lumen-document pdf-export` writes a new PDF from a JSON request on standard input
(`src/write.rs`): pages copied, reordered and turned, redactions burnt into rasterised pages, and an
invisible text layer from Tesseract. Sources may be encrypted when they open without a password.

`lumen-document pdf-translate` finds the text blocks of a PDF and writes a copy with translated
text set in their place (`src/translate.rs`): styles from the source spans, shaping, line breaks
and shrinking down to 60 % to fit, embedded TrueType fonts with a text map.

`lumen-document blocks <format> <scratch> [<first page>]` is what the Lumen server reads of a
document (`src/blocks.rs`). The document is standard input, a regular file that is never opened by
name; `<scratch>` is a private folder, the only place written to and empty again afterwards.
`<format>` is one of `text pdf image wav docx docm xlsx xlsm pptx pptm odt ods odp`. JSON lines are
printed as they are known: `{"info": ...}` with the page count of a PDF or the header of a WAV file,
`{"text", "location", "method"}` for a block of text, `{"blank": page}` for a PDF page without
any and `{"unread": page, "detail": message}` for a page the core can neither read nor draw; the
pages after it are still read. Text files are decoded as UTF-8, as UTF-16 with a byte-order mark, and as Windows-1252 where
bytes are not UTF-8. PDF pages are read from `<first page>`, counted from 0; a page whose text layer
is missing or unreliable, or that is a scan under a few words, is drawn and recognised by
Tesseract. Office files give one line per paragraph, table row, cell or slide paragraph with its
place, then the text recognised in their embedded pictures. Pictures, also HEIC, AVIF and JPEG XL,
are told by their first bytes and normalised by ImageMagick and `djxl`, up to 128 megapixels. A failure is the last line,
`{"error": code, "detail": message}`, with exit code 1; the codes are `password_required`,
`parser_unavailable`, `resource_limit` and `parse_failed`.

`lumen-document view <pdf|image> <scratch> <page>` writes the picture of a page, counted from 1,
as `<scratch>/view.jpg`, at most 1600 pixels long and 90000 bytes large, and prints
`{"width": ..., "height": ...}`. ImageMagick encodes the JPEG.

Encrypted files open with the standard security handler, revisions 2 to 6 (`src/security.rs`); a
password reaches the program on standard input when `LUMEN_PDF_PASSWORD_STDIN` is set, and
revision 6 prepares it with SASLprep.

Error messages are the German source texts, which the caller translates. What the core cannot
read, draw or write is refused by name; nothing else is asked to try.

## Checks

```bash
python3 check-licenses.py
cargo fmt --check
cargo clippy --locked --release --all-targets -- -D warnings
cargo test --locked --release
```

The apps' behaviour is checked end to end through this program by `files/test_lumen_pdf*.py`,
`files/test_workshop.py`, `files/test_translate.py`, `files/test_reader.py` and
`files/test_lumen_office.py`.

## Dependencies

Only licences that can be used freely without buying or separately licensing them are accepted
(MIT, Apache-2.0, BSD, Zlib, ISC and the like); `check-licenses.py` fails on anything else.
A part without such a building block is written in this crate. Direct dependencies: `roxmltree`
(XML tree), `zip` (archive, Deflate only), `flate2` (Deflate), `ttf-parser` (font tables),
`tiny-skia` (rasteriser), `zune-jpeg` and `jpeg-decoder` (JPEG), `hayro-jpeg2000` (JPEG 2000),
`hayro-ccitt` (fax images) and `hayro-jbig2` (JBIG2 images),
`moxcms` (ICC colour management), `rustybuzz` (shaping), `unicode-linebreak` (line breaks),
`stringprep` (SASLprep), `md-5`, `sha2` and `aes` (primitives for encrypted files) and `libc`.
