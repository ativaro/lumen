# Build and publish Lumen

GitHub stores distributable source, tests, documentation and desktop artwork.
GitHub Actions are disabled. Personal system inventories, session logs, app data,
credentials, backups and desktop screenshots do not belong in this repository.
See [INSTALL.md](INSTALL.md) for installation and recovery.

## Verify locally

Use an isolated user profile:

```bash
lumen_test_root="$(mktemp -d)"
HOME="$lumen_test_root" XDG_CONFIG_HOME="$lumen_test_root/config" \
  XDG_DATA_HOME="$lumen_test_root/data" XDG_STATE_HOME="$lumen_test_root/state" \
  XDG_CACHE_HOME="$lumen_test_root/cache" QT_QPA_PLATFORM=offscreen \
  dbus-run-session -- /usr/bin/python3 -m unittest discover -s files -v
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

## Licenses

Application code is MIT. The bundled modified MacTahoe Plasma/Aurorae artwork and
four SVG wallpapers use GPL-3.0. Keep `desktop/CREDITS.md`, `COPYING.GPL-3.0` and
editable graphics with the distribution. Image-generated wallpapers are identified
separately in the credits. Do not include third-party account credentials or private
configuration to make a clean installation work.

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
