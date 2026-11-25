# Build and publish Lumen

GitHub is the distribution source for Lumen Desktop (`ativaro/lumen`, branch `main`).
Forgejo serves internal internal-desktop installations. Publish the same reviewed source
tree to both. Each installation keeps its recorded source.
When their histories differ, publish the reviewed source tree on top of each
remote's existing history without force-pushing or copying private development logs.
GitHub Actions remain disabled. Personal system inventories, session logs, app data,
credentials, backups and desktop screenshots do not belong in this repository.
See [INSTALL.md](INSTALL.md) for installation and recovery.

## Installation from source

The README and installation guide use the same `main` clone and bootstrap command.
Keep them aligned when updating [INSTALL.md](INSTALL.md). Local bootstrap detects its
checkout without another download and always starts the setup wizard after success.
Keep tokens and personal Git or SSH configuration out of the installer.

Before publishing changes to this path, run the relevant bootstrap/installer
checks and the fresh-profile desktop check below. Include required Python/QML,
translations and desktop assets. The manifest `packaging/retired-desktop-files.txt`
excludes retired local app implementations; do not repackage them to satisfy old
tests.

## Verify locally

One command runs the whole desktop suite (`files/test_*.py`, `tests/test_*.py`,
`tests/test-*.py`) and is the gate for CI:

```bash
scripts/test-desktop.sh            # all test files, 4 at a time
scripts/test-desktop.sh -j 8 files/test_search.py tests/test_server_notes_app.py
```

It builds `lumen-service` and `lumen-document` into `.test-desktop/bin` (or uses
`LUMEN_BIN_DIR`), runs every test file on its own in a throwaway profile and
writes `.test-desktop/summary.txt` with every failure and skip; the exit status
is non-zero on any failure. The script header lists its settings
(`LUMEN_TEST_PYTHON`, `CARGO_TARGET_DIR`, `LUMEN_TEST_TMP`, …).

Each profile has its own HOME, XDG folders, `TMPDIR`, `LUMEN_DATA`,
`LUMEN_TOOLS_DATA`, `LUMEN_HOST_TEST_ROOT`, `LUMEN_IMPORT_FIXTURES`, a runtime
folder and a private session bus (`tests/session-bus.conf`, which activates no
services of the host desktop). The screen file `tests/offscreen-screen.json` gives
the offscreen platform a 1920×1200 display; Qt's 800×800 default is smaller than
the window sizes the tests expect. The runtime folder of its own keeps the tests
away from the Lumen service of the running session: a test that reached the
installed service would replace it with the build under test. A service the tests
start in that folder ends by itself once the folder is removed. Afterwards, any
process still carrying the profile in its environment or working directory fails
the test file: the gate reports and kills it.

A CI image needs: Python 3 with pytest 9, PySide6 with Qt WebEngine, PyGObject
(GLib/Gio typelibs), Pillow, NumPy, dbus-python and markdown-it-py; dbus
(`dbus-run-session`), git, openssl, ffmpeg, desktop-file-utils, tesseract with
German and English data, coreutils and `/usr/bin/python3`; Rust with cargo and a
C toolchain for the two native builds; cargo-audit and npm for the workflow's
dependency audit (a step of its own, with network access); the Liberation and DejaVu fonts (the PDF
engine's substitutes), the Breeze icon theme, the AT-SPI typelib and the
`de_DE.UTF-8` locale. rclone and a desktop with kio-fuse are optional; the tests
that need them say so when they skip. Run as an
unprivileged user (Qt WebEngine and the permission tests expect one) and give the
container a larger `/dev/shm` (e.g. `--shm-size=1g`). `packaging/ci/Dockerfile`
builds that image (see the pinned image in the workflow), and
`.forgejo/workflows/desktop-gate.yml` runs the gate in it on the cluster's Forgejo
runner for every push and pull request. Pulling the private image needs the
repository secrets `REGISTRY_USERNAME` and `REGISTRY_PASSWORD`. After a rebuild,
push the image and pin its new digest in the workflow.

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

Lumen-owned components are covered by the
[Lumen EULA](LICENSE), identified as `LicenseRef-Lumen-EULA`. Distribute that
agreement and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) with the software.
Do not label the entire project MIT. Prior MIT grants and third-party rights
remain valid. [LICENSE-PLAN.md](LICENSE-PLAN.md) records the adopted direction
and the remaining legal/provenance checks.

PDF processing uses Lumen's own engine; no external PDF engine is bundled or
required. Verify [the native document engine guide](native/document-core/README.md), including the documented
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
