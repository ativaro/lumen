# Third-party notices

Lumen Desktop as a whole is licensed under GPL-3.0-only. Individual files
retain the terms and credits supplied by their authors. Both installers ship
the full GPL text, this index, and `THIRD_PARTY_LICENSES.txt` with the component
inventory and original notices.

| Material | Terms and source in this repository |
|---|---|
| Native document reader and desktop service | Each Cargo.lock pins the dependencies under `native/document-core/vendor` and `native/service/vendor`. The installed inventory names every vendored package, version and license expression, including build dependencies and empty placeholders for unused targets. For ring it includes the BoringSSL and other component notices. |
| Adobe Glyph List data used in the PDF reader | BSD-3-Clause, © Adobe. [Notice](packaging/licenses/Adobe-Glyph-List.txt) |
| Unicode character data used by memory, persona and notebook | Unicode License v3. [Notice](native/service/vendor/unicode-ident/LICENSE-UNICODE) |
| DM Sans | SIL Open Font License 1.1. [Font authors and license](files/fonts/OFL.txt) |
| Lucide icons, including Feather designs | ISC and MIT. [Credits and terms](files/notes_icons/LICENSE) |
| MacTahoe-derived panel and window decoration | GPL version 3 in the upstream theme manifests. The editable files and modification credits accompany the artwork. [Credits](desktop/CREDITS.md) |
| Pre-existing MIT-marked Lumen source | The native topbar files and desktop input test helper carrying MIT headers retain that permission. [MIT license](packaging/licenses/Lumen-MIT.txt) |
| KDE fake-input protocol, test sources only | LGPL-2.1-or-later. The XML retains Martin Gräßlin's copyright. [Protocol](tests/desktop/fake-input.xml) · [License](tests/desktop/COPYING.LGPL-2.1) |

Three upstream `jpeg-decoder` tower benchmark JPEGs are supplied with the EXIF metadata removed. Their decoded pixels are unchanged. The vendor file checksums reflect this modification.

## Separately installed software

Qt, PySide6, KDE libraries, LayerShellQt, libdbusmenu, SQLite and OpenSSL are
provided by system packages under their respective licenses. The optional
browser setup installs the locked Playwright packages (Apache-2.0) and the
browser with its own notices. The optional memory model is distributed under
Apache-2.0. ONNX Runtime is distributed under MIT with additional third-party
notices. Their downloads and notices are documented in
[the browser lockfile](files/browser-runtime/package-lock.json) and
[the model notice](files/memory-runtime/NOTICE.md).

## Verify an inventory from source

Run `python3 packaging/third-party.py /tmp/lumen-third-party.txt` from a checkout.
The generator checks both lockfiles against the vendor directories and collects
the notices offline. Full dependency sources and build scripts are part of the
corresponding source. [License scope](LICENSE-PLAN.md) · [Release instructions](PUBLISHING.md#licenses-and-corresponding-source)
