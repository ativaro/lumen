# Licensing direction — not a replacement license

The current LICENSE remains MIT for Lumen-authored code; third-party components
retain their own licenses. The repository remains private. This document records
the maintainer's intended policy, not new restrictions on existing recipients.

## Desired policy

Private/noncommercial use should be permitted. Commercial use and commercial
variants should require a separate agreement with the maintainer. A possible
standard basis is **PolyForm Noncommercial 1.0.0**, combined with separately
negotiated commercial rights. This is source-available, not an open-source license.
The unmodified license also allows listed nonprofit, educational, research,
public-safety/health and government organizations. If the intended rule is
strictly natural persons only, it needs different, professionally reviewed terms.

Official terms: https://polyformproject.org/licenses/noncommercial/1.0.0

## Resolve before adopting or publishing

- Lumen currently uses PyQt5. Riverbank requires a commercial PyQt license for
  distribution under GPL-incompatible terms. A noncommercial restriction cannot
  simply be added to that GPL distribution. Alternatives to assess are a
  commercial PyQt license or migration to PySide/Qt for Python, complying with
  the licenses of every Qt module used. LGPL compliance still has obligations.
- Modified MacTahoe assets and other GPL artwork retain their original notices,
  source availability and GPL rights. They must not be relabeled as proprietary.
- Audit source provenance and any contributions before claiming exclusive
  licensing authority. Use an appropriate contributor agreement if future
  contributions must support commercial licensing; copyright does not transfer
  merely because a pull request is accepted.
- A new license does not simply withdraw rights already granted for existing
  MIT copies. Future changes and existing recipients need separate consideration.
- Have the final scope and commercial agreement reviewed by qualified counsel
  before release. This note is a technical licensing inventory, not legal advice.

References:
- https://www.riverbankcomputing.com/commercial/license-faq
- https://doc.qt.io/qtforpython-6/licenses.html
- https://choosealicense.com/licenses/mit/
- https://choosealicense.com/no-permission/
- desktop/CREDITS.md
