# Third-party notices and license boundaries

The [Lumen EULA](LICENSE) covers only materials the Lumen licensor owns or is
authorized to license. It is not a replacement for third-party licenses.
This index is not an exhaustive dependency audit or a certification that the
complete application can be distributed under proprietary terms.

- **Qt / PySide6:** applicable LGPL/GPL/commercial licenses remain in force.
  Preserve notices, corresponding-source availability and required replacement,
  relinking and debugging rights. Native Vault's modules, notices and instructions
  are documented in [native/vault-ui/LICENSES.md](native/vault-ui/LICENSES.md).
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
- **Native Vault dependencies:** vendored keepass, including its documented local
  patches, remains MIT. The exact dependency inventory, license expressions and
  notice hashes remain in [native/vault-core/THIRD_PARTY.md](native/vault-core/THIRD_PARTY.md)
  and `native/vault-core/licenses/`. Rust and Qt notices are also shipped by the
  native installer. Those MIT and other notices must not be replaced by the EULA.
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

The opt-in multilingual MiniLM model and isolated CPU runtime are pinned, verified
and installed separately. Original model card, Apache-2.0 license and dependency
notices are included in files/memory-runtime/. Binary wheel licenses stay in the installed environment.
No model weights or personal memory contents are included in this repository.


## Optional Desktop browser automation

Browser setup downloads `@playwright/mcp` 0.0.84 and its locked Playwright runtime
from npm. Playwright and Playwright MCP are Microsoft projects under Apache-2.0;
license and notice files remain in the downloaded packages. Chromium is installed
through Playwright and retains its bundled licenses. These components run only in
separate browser sessions; bubblewrap provides the local filesystem isolation.
The exact package versions and integrity hashes are in `files/browser-runtime/package-lock.json`.
