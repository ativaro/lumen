# Licensing direction — not a replacement license

The current LICENSE remains MIT for Lumen-authored code; third-party components
retain their own licenses. The repository remains private. This document records
the maintainer's intended policy, not new restrictions on existing recipients.

## Proposed direction — 2026-10-03

The maintainer wants a dual-licensing model similar to Riverbank's: a free
community license and paid, separately negotiated rights for proprietary
derivatives. This supersedes the earlier noncommercial-only proposal. AGPLv3 is
the proposed community license; the exact grant and commercial terms have not
been finalized or adopted.

| Route | Proposed terms |
| --- | --- |
| Community | AGPLv3, free of license fees. Private and business use, modification, redistribution and sales are permitted subject to its conditions. |
| Commercial | A separately negotiated license for code the maintainer has authority to license, allowing agreed proprietary distribution without that code's AGPL obligations. Third-party rights must be resolved separately. |

**A compliant AGPL fork may be sold without paying the maintainer.** This model
earns license revenue from customers needing proprietary rights; it does not
require a royalty on every resale or guarantee revenue. Ordinary business use
does not by itself require a paid license. AGPL source obligations concern
conveying covered works and, under section 13, offering corresponding source to
users interacting remotely with a modified version. They do not require uploading
private user files or publishing every installation on GitHub.

Developer seats, per-product/OEM agreements, fees, support and update periods
remain commercial decisions. No price or revenue-sharing obligation is set here.

## Resolve before adopting or publishing

- Lumen uses PyQt5, offered under GPLv3 or a commercial license. GPLv3 and AGPLv3
  explicitly permit combining their covered works under their respective terms,
  so the proposed community route does not by itself require a PyQt migration.
  Proprietary distribution needs appropriate Riverbank rights, or an alternative
  such as PySide/Qt for Python with the obligations of each Qt module satisfied.
  A Lumen commercial license cannot waive PyQt or Qt licensing requirements.
- Reader and the optional document workshop use PyMuPDF/MuPDF, offered under
  AGPL or commercial terms. Include these features in the dependency audit.
  Proprietary distribution needs suitable Artifex rights or a verified replacement
  for their rendering and editing functions; a Lumen license alone is insufficient.
- Modified MacTahoe assets and other GPL artwork retain their original notices,
  source availability and GPL rights. They must not be relabeled as proprietary.
- Audit source provenance and any contributions before claiming exclusive
  licensing authority. Use an appropriate contributor agreement if future
  contributions must support commercial licensing; copyright does not transfer
  merely because a pull request is accepted.
- A new license does not simply withdraw rights already granted for existing
  MIT copies. Recipients may retain rights to use those copies in proprietary
  derivatives. Future changes and existing recipients need separate consideration.
- Audit all shipped dependencies, assets and notices before adopting either route.
  Keep the repository private while the exact community grant, licensing authority
  and commercial agreement are resolved. Have the final terms reviewed by qualified
  counsel before release. This plan neither changes LICENSE nor certifies that a
  complete distribution can be licensed solely under MIT or solely by the maintainer.

References:
- https://www.gnu.org/licenses/agpl-3.0.en.html
- https://www.gnu.org/licenses/gpl-faq.en.html#ReleaseUnderGPLAndNF
- https://www.riverbankcomputing.com/commercial/license-faq
- https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright
- https://doc.qt.io/qtforpython-6/licenses.html
- https://choosealicense.com/licenses/mit/
- desktop/CREDITS.md
