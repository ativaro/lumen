# Native Vault laboratory: licensing and distribution

This document covers the new native Vault laboratory, **not** a proprietary
licensing clearance of the complete Lumen distribution. Lumen's root LICENSE is
still MIT. No license was silently replaced and no commercial rights are purchased.

## Included code and notices

- Lumen-authored C++, Rust code and interface SVG marks: MIT, root `LICENSE`.
- KDBX engine: locally patched `keepass` 0.15.0, MIT, with original LICENSE and
  documented provenance in `../vault-core/vendor/keepass/LUMEN-PATCHES.md`. No KeePassXC source is copied or
  linked. KeePassXC is a separately installed reference program used by tests.
- All 98 Cargo.lock dependencies, including non-Linux targets: exact package
  manifests and upstream notice texts are in `../vault-core/licenses/`.
  `inventory.json` records versions, SPDX declarations, origin and notice hashes;
  `check-licenses.py` fails when the lock inventory or collected texts differ.
  This is a checked inventory, not a legal certification or proof of authorship.
- Where offered, the MIT alternative is selected. For constant_time_eq and the
  empty block-modes 0.9.1 marker crate, the Apache-2.0 alternative is selected;
  zlib-rs uses Zlib; unicode-ident additionally requires Unicode-3.0. Preserve
  every supplied notice, including Apache NOTICE files and attribution headers.
  rust-argon2's legacy `MIT/Apache-2.0` declaration is clarified by its included
  dual-license header and complete LICENSE-MIT/LICENSE-APACHE texts.
- blake2b_simd omits its license text from its crate archive. The included text
  comes from the **exact recorded upstream commit** listed in inventory.json.
  r-efi supplies its actual MIT grant/copyrights in AUTHORS; that file is included.
  block-modes 0.9.1 contains only a deprecation comment and metadata, no algorithm;
  its declared Apache alternative and standard text are retained explicitly.
- Rust 1.89.0 standard-library/runtime notices, including third-party notices,
  are in `licenses/rust-runtime/`. Update these when changing the pinned compiler.

## Qt

The native application dynamically links the separately installed Qt 6 **Core,
Gui, Widgets and D-Bus** libraries. Qt Test is used by tests only. These modules
are used under LGPLv3; `licenses/qt/` contains LGPLv3 and its GPLv3 base text.
Settings → About / Licenses identifies Qt and these rights. SVG icons use the
separately installed Qt SVG plugin (LGPLv3); its code is not bundled here. We do not ship
Qt DLLs/shared libraries, plugins, or a Qt Python wheel in this laboratory bundle.
Users obtain Qt through their distribution; its package carries the matching
library notices and source information. The current developer host uses Qt 6.11.2.

Users may replace the Qt libraries and debug/reverse engineer the application
for the purpose of modifying those libraries. No EULA, integrity lock, signature
requirement or installation restriction in this bundle removes those rights.
CMake sources and rebuild/install instructions are included. To use a different
compatible Qt build, configure with `-DCMAKE_PREFIX_PATH=/path/to/Qt`, rebuild,
and run with the corresponding loader/plugin paths. The broker has no Qt dependency.

If a future distributor **bundles Qt**, that distributor must additionally supply
matching complete Qt source (including modifications and third-party code) or an
applicable compliant source offer/access mechanism, Qt's third-party notices and
necessary installation/relinking information. This laboratory is not a generic
permission to bundle arbitrary Qt modules: some other modules are GPL-only.

Official references:
- https://www.qt.io/development/open-source-lgpl-obligations
- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qt-6/qtwidgets-index.html#licenses-and-attributions
- https://doc.qt.io/qt-6/qtdbus-index.html#licenses-and-attributions

## Entire Lumen project

Existing PyMuPDF/MuPDF and GPL artwork retain their own terms. The native Vault
work does not remove them, convert them to MIT, or authorize a closed-source
commercial redistribution of the entire product. See ../../LICENSE-PLAN.md and
../../desktop/CREDITS.md. Keep the repository private as requested; obtain a
qualified review before adopting/distributing the proposed commercial edition.
