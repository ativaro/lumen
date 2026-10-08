# Build and publish Lumen

GitHub stores distributable source, tests, documentation and desktop artwork.
GitHub Actions are disabled. Personal system inventories, session logs, app data,
credentials, backups and desktop screenshots do not belong in this repository.
See [INSTALL.md](INSTALL.md) for installation and recovery.

## Private one-line installer

The README starts with the authenticated `main` clone and `bootstrap.sh` command.
Keep that command and [INSTALL.md](INSTALL.md) aligned. Local bootstrap detects its
checkout without another download and always starts the setup wizard after success.
The public curl command remains explicitly unavailable while this repository is
private. Never embed a token or personal Git/SSH configuration in the installer.

Before publishing changes to this path, run `files/test_bootstrap.py` and the
fresh-profile desktop check below. Include all Python/QML/translations and desktop
assets; preserve the explicit native Vault prerelease boundary described below.

## Verify locally

Use an isolated user profile:

```bash
lumen_test_python="$(bin/lumen-python -c 'import sys; print(sys.executable)')"
lumen_test_root="$(mktemp -d)"
HOME="$lumen_test_root" XDG_CONFIG_HOME="$lumen_test_root/config" \
  XDG_DATA_HOME="$lumen_test_root/data" XDG_STATE_HOME="$lumen_test_root/state" \
  XDG_CACHE_HOME="$lumen_test_root/cache" QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de \
  LUMEN_PYTHON="$lumen_test_python" dbus-run-session -- "$lumen_test_python" -m unittest discover -s files -v
```

Create the ignored screenshot directories and run Qt 6's QML checks:

```bash
mkdir -p artifacts/islands artifacts/panel artifacts/themes
/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests -platform offscreen
```
Run the installed desktop in disposable virtual Plasma sessions:

```bash
python3 tests/check-desktop.py
python3 tests/check-desktop.py --width 1280 --screens 1
```

The check creates an empty HOME/XDG profile and separate D-Bus/compositor session. Verify all three desktop roles, Files/search launchers,
four themes and Aurorae decorations, wallpaper selection and idempotent setup.
Do not reset a developer's running Plasma session to test an installer.

Review staged files and the commits that will be pushed for private information.
Do not push local development history containing deployment logs or machine data;
prepare a clean change on top of the remote branch when necessary. Generated design
mockups and diagnostic artifacts are not needed to install Lumen.

## Package

All desktop programs use PySide6/Qt 6. The [QML search](SEARCH-PREVIEW.md) is the
production search behind the existing panel and shortcuts. Include `files/qml/search`,
its translation catalog and `bin/lumen-python` in every package.

Commit the reviewed source, then run:

```bash
./packaging/arch/build-package.sh
```

The build uses `git archive HEAD` so only committed project files enter the source
archive. Check the resulting package contains `usr/share/lumen/desktop`, all
`org.lumen.*` applets and the three app/Files/search launchers. The package installs
resources; each user explicitly activates their desktop using `lumen-desktop-setup`.
Updates preserve existing service preferences and user data.

A fresh-system clone build is supported. The PKGBUILD's release-tarball mode is
for maintainers: create the matching version tag and replace `SKIP` with the
verified archive checksum before distributing that PKGBUILD independently.
No AUR release or binary repository is currently implied by this source repository.

## Native Vault laboratory

The optional native password-vault laboratory is built and installed separately;
see [native/vault-ui/README.md](native/vault-ui/README.md). It remains restricted
to synthetic data pending the release gates in its REVIEW.md. The default package
ships only the launcher route and readiness status, not an audited password manager.
Native binaries must include the full notice/source bundle produced by its installer.

## Licenses

The repository remains private. Lumen-owned components are covered by the
[Lumen EULA](LICENSE), identified as `LicenseRef-Lumen-EULA`. Distribute that
agreement and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) with the software.
Do not label the entire project MIT. Prior MIT grants and third-party rights
remain valid. [LICENSE-PLAN.md](LICENSE-PLAN.md) records the adopted direction
and the remaining legal/provenance checks.

PDF processing uses Lumen's own engine; no external PDF engine is bundled or
required. Verify [SPEC-pdf-core.md](SPEC-pdf-core.md), including the documented
unsupported formats, when releasing changes. Preserve applicable Qt/PySide6 LGPL
notices, corresponding-source availability, library replacement and debugging
rights. The EULA expressly preserves those rights.

Keep the modified MacTahoe artwork and four SVG wallpapers under GPL-3.0 with
`desktop/CREDITS.md`, `COPYING.GPL-3.0` and their editable sources. Preserve all
vendored/library notices. Do not include personal configuration or credentials.

Real image-model smoke (after explicitly installing the optional image search):

```bash
/usr/bin/python3 tests/check-photos.py
```

It uses synthetic colored images and a temporary index, verifies German motif
queries, vector reuse and removed-file filtering. No personal image folders are
read. The normal suite tests preview invalidation, cleanup suggestions, sensor
units, activity deferral, stale-file trash refusal and the native review workflow.
Models, indexes, sensor output and UI captures are private runtime/test artifacts;
never include them in a source release.
