# Third-party notices and license boundaries

The [Lumen EULA](LICENSE) covers only materials the Lumen licensor owns or is
authorized to license. It is not a replacement for third-party licenses.
This index is not an exhaustive dependency audit or a certification that the
complete application can be distributed under proprietary terms.

- **Qt / PySide6:** applicable LGPL/GPL/commercial licenses remain in force.
  Preserve notices, corresponding-source availability and required replacement,
  relinking and debugging rights.
- **Native desktop bar:** dynamically links the separately installed
  LayerShellQt (LGPL-2.0-or-later) and libdbusmenu-glib
  (LGPL-2.1-only OR LGPL-3.0-only) libraries. Their upstream/system-package notices
  and replacement rights remain applicable. No modified copy of these libraries
  is bundled. The native bar's own source is in `native/topbar/`.
- **Desktop test protocol:** `tests/desktop/fake-input.xml` is KDE's
  fake-input protocol by Martin Gräßlin, LGPL-2.1-or-later. Its copyright is retained
  in the XML and the license is in `tests/desktop/COPYING.LGPL-2.1`. The generated
  input helper is used only inside isolated test sessions and is not installed.
- **PDF processing:** Lumen now uses its own PDF parser, renderer, writer and
  workflow code. No external PDF engine is required or bundled. Qt supplies
  general font, image and drawing primitives; installed fonts retain their own
  licenses and embedding restrictions. Password-protected PDFs use the system's
  OpenSSL 3 library for general cryptographic primitives, under its
  [Apache-2.0 license](https://docs.openssl.org/3.0/man7/migration_guide/).
  PDF algorithms and format handling are implemented in Lumen. This change does
  not alter license obligations for earlier distributions.
- **Desktop artwork:** modified MacTahoe assets and the four original SVG
  wallpapers retain GPL-3.0 and editable sources. See
  [desktop/CREDITS.md](desktop/CREDITS.md) and
  [desktop/COPYING.GPL-3.0](desktop/COPYING.GPL-3.0).
- **Bundled DM Sans fonts:** copyright the DM Sans Project Authors; distributed
  under the SIL Open Font License 1.1. The complete notice is shipped alongside
  the unchanged font files in [files/fonts/OFL.txt](files/fonts/OFL.txt).
- **Separately installed tools, fonts and models:** their accompanying licenses
  apply independently; installing them does not make them Lumen-owned materials.
- **Earlier releases and contributions:** prior MIT grants remain valid for the
  copies to which they apply. A contributor's rights are not transferred merely
  by accepting a commit. Materials without established relicensing authority
  retain their existing licenses.

Release decisions and remaining checks: [LICENSE-PLAN.md](LICENSE-PLAN.md).

## Optional local memory search

The opt-in multilingual MiniLM model and the ONNX Runtime 1.30.0 library (MIT, Microsoft) that runs it
are pinned, verified and installed separately. Original model card, Apache-2.0 license and notices
are included in files/memory-runtime/. The library comes unmodified from the pinned `onnxruntime` wheel;
its LICENSE and ThirdPartyNotices.txt are installed beside it.
No model weights or personal memory contents are included in this repository.


## Optional Desktop browser automation

Browser setup downloads `@playwright/mcp` 0.0.84 and its locked Playwright runtime
from npm. Playwright and Playwright MCP are Microsoft projects under Apache-2.0;
license and notice files remain in the downloaded packages. Chromium is installed
through Playwright and retains its bundled licenses. These components run only in
separate browser sessions; bubblewrap provides the local filesystem isolation.
The exact package versions and integrity hashes are in `files/browser-runtime/package-lock.json`.

## Document reader (`lumen-document`)

Lumen's own document core in `native/document-core` is built from the frozen sources in
`native/document-core/vendor`; the build does not reach the network. Only licences that can be used
freely are accepted, which `native/document-core/check-licenses.py` enforces. The compiled program
contains these packages; each package's licence text is in its folder under `vendor/`:

| Package | Version | Licence |
|---|---|---|
| `adler2` | 2.0.1 | 0BSD OR MIT OR Apache-2.0 |
| `aes` | 0.8.4 | MIT OR Apache-2.0 |
| `arrayref` | 0.3.9 | BSD-2-Clause |
| `arrayvec` | 0.7.8 | MIT OR Apache-2.0 |
| `bitflags` | 1.3.2 | MIT/Apache-2.0 |
| `bitflags` | 2.13.2 | MIT OR Apache-2.0 |
| `block-buffer` | 0.10.4 | MIT OR Apache-2.0 |
| `bumpalo` | 3.20.3 | MIT OR Apache-2.0 |
| `bytemuck` | 1.25.2 | Zlib OR Apache-2.0 OR MIT |
| `cfg-if` | 1.0.5 | MIT OR Apache-2.0 |
| `cipher` | 0.4.4 | MIT OR Apache-2.0 |
| `core_maths` | 0.1.1 | MIT |
| `cpufeatures` | 0.2.17 | MIT OR Apache-2.0 |
| `crc32fast` | 1.5.5 | MIT OR Apache-2.0 |
| `crypto-common` | 0.1.7 | MIT OR Apache-2.0 |
| `digest` | 0.10.7 | MIT OR Apache-2.0 |
| `equivalent` | 1.0.3 | Apache-2.0 OR MIT |
| `fdeflate` | 0.3.7 | MIT OR Apache-2.0 |
| `flate2` | 1.1.11 | MIT OR Apache-2.0 |
| `generic-array` | 0.14.7 | MIT |
| `hashbrown` | 0.17.1 | MIT OR Apache-2.0 |
| `hayro-jpeg2000` | 0.5.0 | Apache-2.0 OR MIT |
| `indexmap` | 2.14.2 | Apache-2.0 OR MIT |
| `inout` | 0.1.4 | MIT OR Apache-2.0 |
| `jpeg-decoder` | 0.3.2 | MIT OR Apache-2.0 |
| `libc` | 0.2.191 | MIT OR Apache-2.0 |
| `libm` | 0.2.16 | MIT |
| `log` | 0.4.35 | MIT OR Apache-2.0 |
| `md-5` | 0.10.6 | MIT OR Apache-2.0 |
| `memchr` | 2.8.3 | Unlicense OR MIT |
| `miniz_oxide` | 0.8.9 | MIT OR Zlib OR Apache-2.0 |
| `miniz_oxide` | 0.9.1 | MIT OR Zlib OR Apache-2.0 |
| `moxcms` | 0.9.2 | BSD-3-Clause OR Apache-2.0 |
| `num-traits` | 0.2.19 | MIT OR Apache-2.0 |
| `png` | 0.17.16 | MIT OR Apache-2.0 |
| `pxfm` | 0.1.30 | BSD-3-Clause OR Apache-2.0 |
| `roxmltree` | 0.20.0 | MIT OR Apache-2.0 |
| `rustybuzz` | 0.20.1 | MIT |
| `sha2` | 0.10.9 | MIT OR Apache-2.0 |
| `simd-adler32` | 0.3.10 | MIT |
| `smallvec` | 1.16.5 | MIT OR Apache-2.0 |
| `strict-num` | 0.1.1 | MIT |
| `stringprep` | 0.1.5 | MIT/Apache-2.0 |
| `tiny-skia` | 0.11.4 | BSD-3-Clause |
| `tiny-skia-path` | 0.11.4 | BSD-3-Clause |
| `tinyvec` | 1.13.3 | Zlib OR Apache-2.0 OR MIT |
| `ttf-parser` | 0.25.1 | MIT OR Apache-2.0 |
| `typenum` | 1.20.1 | MIT OR Apache-2.0 |
| `unicode-bidi` | 0.3.18 | MIT OR Apache-2.0 |
| `unicode-bidi-mirroring` | 0.4.0 | MIT/Apache-2.0 |
| `unicode-ccc` | 0.4.0 | MIT/Apache-2.0 |
| `unicode-linebreak` | 0.1.5 | Apache-2.0 |
| `unicode-normalization` | 0.1.26 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| `unicode-properties` | 0.1.5 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| `unicode-script` | 0.5.9 | MIT OR Apache-2.0 |
| `zip` | 2.6.1 | MIT |
| `zopfli` | 0.8.4 | Apache-2.0 |
| `zune-core` | 0.4.12 | MIT OR Apache-2.0 OR Zlib |
| `zune-jpeg` | 0.4.21 | MIT OR Apache-2.0 OR Zlib |

The glyph names in `src/text.rs` are taken from the Adobe Glyph List (BSD-3-Clause, Adobe Systems).

The other folders under `vendor/` belong to build tools and to platforms and features that are
not compiled into the program.

## Desktop service (`lumen-service`)

Lumen's desktop service in `native/service`, with the memory meaning search, the engine conversations, the
persona, the notebook core of Lumen Notes and the HTTPS connection to the Lumen Server (rustls with ring), is
built from the frozen sources in `native/service/vendor`, together with Lumen's sentence encoder in
`native/sentence-encoder`, the engine crate in `native/engine`, the persona crate in `native/persona` and the
memory crate in `native/memory`; the build does not reach the network and accepts only freely usable licences
(`native/document-core/check-licenses.py native/service`). Character tables in `native/persona/src/printable.rs`,
`native/memory` and `native/service/src/notebook/python.rs` are derived from the Unicode Character Database
16.0.0 (Unicode License V3, text in `native/service/vendor/unicode-ident/LICENSE-UNICODE`). The compiled program
contains these packages; each package's licence text is in its folder under `vendor/`:

| Package | Version | Licence |
|---|---|---|
| `ahash` | 0.8.12 | MIT OR Apache-2.0 |
| `aho-corasick` | 1.1.5 | Unlicense OR MIT |
| `atomic-waker` | 1.1.2 | Apache-2.0 OR MIT |
| `base64` | 0.13.1 | MIT/Apache-2.0 |
| `base64` | 0.22.1 | MIT OR Apache-2.0 |
| `base64` | 0.23.1 | MIT OR Apache-2.0 |
| `bit-set` | 0.8.0 | Apache-2.0 OR MIT |
| `bit-vec` | 0.8.0 | Apache-2.0 OR MIT |
| `bitflags` | 2.13.2 | MIT OR Apache-2.0 |
| `block-buffer` | 0.10.4 | MIT OR Apache-2.0 |
| `bytes` | 1.12.1 | MIT |
| `caseless` | 0.2.2 | MIT |
| `castaway` | 0.2.4 | MIT |
| `cfg-if` | 1.0.5 | MIT OR Apache-2.0 |
| `compact_str` | 0.9.1 | MIT |
| `cpufeatures` | 0.2.17 | MIT OR Apache-2.0 |
| `crossbeam-deque` | 0.8.8 | MIT OR Apache-2.0 |
| `crossbeam-epoch` | 0.9.21 | MIT OR Apache-2.0 |
| `crossbeam-utils` | 0.8.23 | MIT OR Apache-2.0 |
| `crypto-common` | 0.1.7 | MIT OR Apache-2.0 |
| `darling` | 0.20.11 | MIT |
| `darling_core` | 0.20.11 | MIT |
| `darling_macro` | 0.20.11 | (proc-macro) MIT |
| `dary_heap` | 0.3.9 | MIT OR Apache-2.0 |
| `derive_builder` | 0.20.2 | MIT OR Apache-2.0 |
| `derive_builder_core` | 0.20.2 | MIT OR Apache-2.0 |
| `derive_builder_macro` | 0.20.2 | (proc-macro) MIT OR Apache-2.0 |
| `digest` | 0.10.7 | MIT OR Apache-2.0 |
| `displaydoc` | 0.2.7 | (proc-macro) MIT OR Apache-2.0 |
| `either` | 1.19.0 | MIT OR Apache-2.0 |
| `errno` | 0.3.14 | MIT OR Apache-2.0 |
| `esaxx-rs` | 0.1.10 | Apache-2.0 |
| `fallible-iterator` | 0.3.0 | MIT/Apache-2.0 |
| `fallible-streaming-iterator` | 0.1.9 | MIT/Apache-2.0 |
| `fancy-regex` | 0.14.0 | MIT |
| `fnv` | 1.0.7 | Apache-2.0 / MIT |
| `foldhash` | 0.2.0 | Zlib |
| `form_urlencoded` | 1.2.2 | MIT OR Apache-2.0 |
| `futures-channel` | 0.3.34 | MIT OR Apache-2.0 |
| `futures-core` | 0.3.34 | MIT OR Apache-2.0 |
| `futures-task` | 0.3.34 | MIT OR Apache-2.0 |
| `futures-util` | 0.3.34 | MIT OR Apache-2.0 |
| `generic-array` | 0.14.7 | MIT |
| `getrandom` | 0.2.17 | MIT OR Apache-2.0 |
| `getrandom` | 0.3.4 | MIT OR Apache-2.0 |
| `hashbrown` | 0.17.1 | MIT OR Apache-2.0 |
| `hashlink` | 0.12.2 | MIT OR Apache-2.0 |
| `http` | 1.5.0 | MIT OR Apache-2.0 |
| `http-body` | 1.1.0 | MIT |
| `http-body-util` | 0.1.5 | MIT |
| `httparse` | 1.10.1 | MIT OR Apache-2.0 |
| `hyper` | 1.12.0 | MIT |
| `hyper-util` | 0.1.21 | MIT |
| `icu_collections` | 2.4.0 | Unicode-3.0 |
| `icu_locale_core` | 2.4.0 | Unicode-3.0 |
| `icu_normalizer` | 2.4.0 | Unicode-3.0 |
| `icu_normalizer_data` | 2.4.0 | Unicode-3.0 |
| `icu_properties` | 2.4.0 | Unicode-3.0 |
| `icu_properties_data` | 2.4.0 | Unicode-3.0 |
| `icu_provider` | 2.4.0 | Unicode-3.0 |
| `ident_case` | 1.0.1 | MIT/Apache-2.0 |
| `idna` | 1.1.0 | MIT OR Apache-2.0 |
| `idna_adapter` | 1.2.2 | Apache-2.0 OR MIT |
| `ipnet` | 2.12.2 | MIT OR Apache-2.0 |
| `itertools` | 0.14.0 | MIT OR Apache-2.0 |
| `itoa` | 1.0.19 | MIT OR Apache-2.0 |
| `libc` | 0.2.191 | MIT OR Apache-2.0 |
| `libloading` | 0.9.1 | ISC |
| `libsqlite3-sys` | 0.40.0 | MIT |
| `linux-raw-sys` | 0.12.1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT |
| `litemap` | 0.8.3 | Unicode-3.0 |
| `log` | 0.4.35 | MIT OR Apache-2.0 |
| `macro_rules_attribute` | 0.2.3 | Apache-2.0 OR MIT OR Zlib |
| `macro_rules_attribute-proc_macro` | 0.2.3 | (proc-macro) Apache-2.0 OR MIT OR Zlib |
| `memchr` | 2.8.3 | Unlicense OR MIT |
| `minimal-lexical` | 0.2.1 | MIT/Apache-2.0 |
| `mio` | 1.2.4 | MIT |
| `monostate` | 0.1.18 | MIT OR Apache-2.0 |
| `monostate-impl` | 0.1.18 | (proc-macro) MIT OR Apache-2.0 |
| `nom` | 7.1.3 | MIT |
| `once_cell` | 1.21.4 | MIT OR Apache-2.0 |
| `openssl-probe` | 0.2.2 | MIT OR Apache-2.0 |
| `ort` | 2.0.0-rc.15 | MIT OR Apache-2.0 |
| `ort-sys` | 2.0.0-rc.15 | MIT OR Apache-2.0 |
| `paste` | 1.0.15 | (proc-macro) MIT OR Apache-2.0 |
| `pastey` | 0.2.3 | (proc-macro) MIT OR Apache-2.0 |
| `percent-encoding` | 2.3.2 | MIT OR Apache-2.0 |
| `pin-project-lite` | 0.2.17 | Apache-2.0 OR MIT |
| `potential_utf` | 0.1.6 | Unicode-3.0 |
| `ppv-lite86` | 0.2.21 | MIT OR Apache-2.0 |
| `proc-macro2` | 1.0.107 | MIT OR Apache-2.0 |
| `quote` | 1.0.47 | MIT OR Apache-2.0 |
| `rand` | 0.9.5 | MIT OR Apache-2.0 |
| `rand_chacha` | 0.9.0 | MIT OR Apache-2.0 |
| `rand_core` | 0.9.5 | MIT OR Apache-2.0 |
| `rayon` | 1.12.0 | MIT OR Apache-2.0 |
| `rayon-cond` | 0.4.0 | Apache-2.0/MIT |
| `rayon-core` | 1.13.0 | MIT OR Apache-2.0 |
| `regex` | 1.13.1 | MIT OR Apache-2.0 |
| `regex-automata` | 0.4.18 | MIT OR Apache-2.0 |
| `regex-syntax` | 0.8.11 | MIT OR Apache-2.0 |
| `reqwest` | 0.13.5 | MIT OR Apache-2.0 |
| `ring` | 0.17.14 | Apache-2.0 AND ISC |
| `rusqlite` | 0.42.0 | MIT |
| `rustix` | 1.1.5 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT |
| `rustls` | 0.23.46 | Apache-2.0 OR ISC OR MIT |
| `rustls-native-certs` | 0.8.5 | Apache-2.0 OR ISC OR MIT |
| `rustls-pki-types` | 1.15.1 | MIT OR Apache-2.0 |
| `rustls-webpki` | 0.103.16 | ISC |
| `rustversion` | 1.0.23 | (proc-macro) MIT OR Apache-2.0 |
| `ryu` | 1.0.23 | Apache-2.0 OR BSL-1.0 |
| `serde` | 1.0.229 | MIT OR Apache-2.0 |
| `serde_core` | 1.0.229 | MIT OR Apache-2.0 |
| `serde_derive` | 1.0.229 | (proc-macro) MIT OR Apache-2.0 |
| `serde_json` | 1.0.154 | MIT OR Apache-2.0 |
| `sha2` | 0.10.9 | MIT OR Apache-2.0 |
| `signal-hook-registry` | 1.4.8 | MIT OR Apache-2.0 |
| `slab` | 0.4.12 | MIT |
| `smallvec` | 1.16.5 | MIT OR Apache-2.0 |
| `socket2` | 0.6.5 | MIT OR Apache-2.0 |
| `spm_precompiled` | 0.1.4 | Apache-2.0 |
| `stable_deref_trait` | 1.2.1 | MIT OR Apache-2.0 |
| `static_assertions` | 1.1.0 | MIT OR Apache-2.0 |
| `strsim` | 0.11.1 | MIT |
| `subtle` | 2.6.1 | BSD-3-Clause |
| `syn` | 2.0.119 | MIT OR Apache-2.0 |
| `syn` | 3.0.10 | MIT OR Apache-2.0 |
| `sync_wrapper` | 1.0.2 | Apache-2.0 |
| `synstructure` | 0.14.0 | MIT |
| `thiserror` | 2.0.21 | MIT OR Apache-2.0 |
| `thiserror-impl` | 2.0.21 | (proc-macro) MIT OR Apache-2.0 |
| `tinystr` | 0.8.5 | Unicode-3.0 |
| `tinyvec` | 1.13.3 | Zlib OR Apache-2.0 OR MIT |
| `tokenizers` | 0.22.2 | Apache-2.0 |
| `tokio` | 1.54.1 | MIT |
| `tokio-macros` | 2.7.2 | (proc-macro) MIT |
| `tokio-rustls` | 0.26.6 | MIT OR Apache-2.0 |
| `tower` | 0.5.3 | MIT |
| `tower-http` | 0.6.11 | MIT |
| `tower-layer` | 0.3.3 | MIT |
| `tower-service` | 0.3.3 | MIT |
| `tracing` | 0.1.44 | MIT |
| `tracing-core` | 0.1.36 | MIT |
| `try-lock` | 0.2.5 | MIT |
| `typenum` | 1.20.1 | MIT OR Apache-2.0 |
| `unicode-ident` | 1.0.27 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| `unicode-normalization` | 0.1.24 | MIT/Apache-2.0 |
| `unicode-normalization-alignments` | 0.1.12 | MIT/Apache-2.0 |
| `unicode-segmentation` | 1.13.3 | MIT OR Apache-2.0 |
| `unicode_categories` | 0.1.1 | MIT OR Apache-2.0 |
| `untrusted` | 0.9.0 | ISC |
| `url` | 2.5.8 | MIT OR Apache-2.0 |
| `utf8_iter` | 1.1.0 | Apache-2.0 OR MIT |
| `utf_types` | 1.0.0 | Apache-2.0 OR MIT |
| `want` | 0.3.2 | MIT |
| `writeable` | 0.6.4 | Unicode-3.0 |
| `yoke` | 0.8.4 | Unicode-3.0 |
| `yoke-derive` | 0.8.4 | (proc-macro) Unicode-3.0 |
| `zerocopy` | 0.8.63 | BSD-2-Clause OR Apache-2.0 OR MIT |
| `zerofrom` | 0.1.8 | Unicode-3.0 |
| `zerofrom-derive` | 0.1.8 | (proc-macro) Unicode-3.0 |
| `zeroize` | 1.9.1 | Apache-2.0 OR MIT |
| `zerotrie` | 0.2.5 | Unicode-3.0 |
| `zerovec` | 0.11.9 | Unicode-3.0 |
| `zerovec-derive` | 0.11.7 | (proc-macro) Unicode-3.0 |
| `zmij` | 1.0.23 | MIT |

The sentence model and the ONNX Runtime library it loads are downloaded during setup and are described in
`files/memory-runtime/`.
