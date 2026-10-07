# Licensing status and release constraints

## Adopted direction — 5 October 2026

The maintainer instructed an immediate change from the project-wide MIT offer
to the original proprietary [Lumen EULA](LICENSE), identified as
`LicenseRef-Lumen-EULA`. This supersedes the earlier proposed AGPL/commercial
model; the proposal was never adopted as Lumen's general license.

The EULA allows personal and internal business use, local builds and internal
customization. Redistribution, resale, commercial forks, OEM editions and
hosted offerings require the maintainer's express written agreement. It sets
no price or revenue share. Source availability is not an open-source grant.
The repository remains private. Microsoft is not a party and its terms have
not been copied.

## Boundaries that remain

- This change cannot withdraw rights already granted for earlier MIT copies.
  Historical license texts remain in Git. No history rewrite or retroactive
  restriction is intended.
- Only code and assets the maintainer owns or is authorized to relicense are
  covered. Verify authorship and contribution rights before a release; a Git
  author label does not establish copyright ownership. Third-party notices and
  separately licensed contributions remain effective.
- Qt/PySide6 LGPL obligations, including library replacement, corresponding
  source and debugging/relinking rights, remain mandatory where applicable.
- The previous external PDF engine has been replaced with Lumen's own format
  implementation. Runtime and installation no longer require that component.
  This removes that dependency from the current distribution, without certifying
  the complete application or changing obligations for earlier releases.
  System OpenSSL 3, Qt and font licenses still apply.
- GPL desktop artwork and MIT vendored keepass (including its local patches)
  retain their notices and rights. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Before a public/commercial release, confirm the licensor's full legal identity
and contact details, have qualified counsel review the EULA and acceptance flow
for the intended jurisdictions, and complete the dependency/contribution audit.
The repository text and installer notice alone do not certify enforceability,
user assent or clearance of the complete distribution. Do not publish a
proprietary binary distribution with unresolved copyleft integrations.

Primary references:
- [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [OpenSSL 3 migration and license](https://docs.openssl.org/3.0/man7/migration_guide/)
- [GNU license FAQ](https://www.gnu.org/licenses/gpl-faq.en.html)
