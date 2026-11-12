# Build and publish Lumen

GitHub stores the tester Desktop release at `ativaro/lumen` on `main`.
Forgejo serves internal internal-desktop installations. Both repositories remain private;
publish the same reviewed source tree to both. Each installation keeps its source.
When their histories differ, publish the reviewed source tree on top of each
remote's existing history without force-pushing or copying private development logs.
GitHub Actions remain disabled. Personal system inventories, session logs, app data,
credentials, backups and desktop screenshots do not belong in this repository.
See [INSTALL.md](INSTALL.md) for installation and recovery.

## Private one-line installer

The README starts with the authenticated `main` clone and `bootstrap.sh` command.
Keep that command and [INSTALL.md](INSTALL.md) aligned. Local bootstrap detects its
checkout without another download and always starts the setup wizard after success.
An unauthenticated curl command cannot install from this private repository. Never embed a token or personal Git/SSH configuration in the installer.

Before publishing changes to this path, run the relevant bootstrap/installer
checks and the fresh-profile desktop check below. Include required Python/QML,
translations and desktop assets. The manifest `packaging/retired-desktop-files.txt`
excludes retired local app implementations; do not repackage them to satisfy old
tests.

## Verify locally

Use an isolated user profile:

```bash
lumen_test_python="$(bin/lumen-python -c 'import sys; print(sys.executable)')"
lumen_test_root="$(mktemp -d)"
HOME="$lumen_test_root" XDG_CONFIG_HOME="$lumen_test_root/config" \
  XDG_DATA_HOME="$lumen_test_root/data" XDG_STATE_HOME="$lumen_test_root/state" \
  XDG_CACHE_HOME="$lumen_test_root/cache" LUMEN_DATA="$lumen_test_root/lumen" \
  LUMEN_TOOLS_DATA="$lumen_test_root/tools" LUMEN_HOST_TEST_ROOT="$lumen_test_root/host" \
  LUMEN_IMPORT_FIXTURES="$lumen_test_root" \
  QT_QPA_PLATFORM="offscreen:configfile=$PWD/tests/offscreen-screen.json" LUMEN_LANGUAGE=de \
  LUMEN_PYTHON="$lumen_test_python" dbus-run-session -- "$lumen_test_python" -m unittest discover -s files -v
```

The screen file gives the offscreen platform a 1920×1200 display; Qt's 800×800
default is smaller than the window sizes the tests expect. `LUMEN_IMPORT_FIXTURES`
is the folder in which the import tests create their private files.

Exercise the native topbar in a disposable virtual Plasma session:

```bash
python3 tests/check-desktop.py
python3 tests/check-desktop.py --width 1600 --scale 1.25 --surface-only
```

The runner creates a private profile, bus and virtual compositor. Run
`tests/check-install-closure.py` for fresh and repeated user installations and the
system package layout. Verify desktop Inbox and Notes using their normal menu
commands against an isolated Staging account.
Do not reset a developer's running Plasma session to test an installer.

Review staged files and the commits that will be pushed for private information.
Do not push local development history containing deployment logs or machine data;
prepare a clean change on top of the remote branch when necessary. Generated design
mockups and diagnostic artifacts are not needed to install Lumen.

## Package

All desktop programs use PySide6/Qt 6. The [QML search](SEARCH-PREVIEW.md) is the
production search behind the existing panel and shortcuts. Include `files/qml/search`,
its translation catalog and `bin/lumen-python` in every package. Also include
`files/fonts`, `files/project_fonts`, `files/notes_icons` and their licenses.
A release must not resolve missing modules or binaries from a developer checkout
or a pre-existing personal installation.

Commit the reviewed source, then run:

```bash
./packaging/arch/build-package.sh
```

The build requires a clean Git checkout and uses `git archive HEAD`. It records
the source revision, credential-free repository URL and fixed source timestamp
in `source.json`. `--source-only` creates the deterministic source archive and
its SHA-256 file without building or installing a system package. An extracted
archive can use `install.sh` without a Git checkout. Check the resulting package contains `usr/share/lumen/desktop`, all
`org.lumen.*` applets and the three app/Files/search launchers. The package installs
resources; each user explicitly activates their desktop using `lumen-desktop-setup`.
Updates preserve existing service preferences and user data.

The package builder verifies the source archive checksum and checks build
dependencies. For an independently downloaded release archive, maintainers must
set `LUMEN_SOURCE_ARCHIVE_URL` and `LUMEN_SOURCE_SHA256` explicitly; there is no
unverified `SKIP` source or assumed release tag. For local metadata, create the
source archive before running `build-package.sh --srcinfo`.
No AUR release or binary repository is implied by this source repository.
Source-archive reproducibility does not by itself establish bit-identical native
binaries or a successful installation on every distribution.

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
