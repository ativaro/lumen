# Install Lumen on a fresh desktop

Lumen-owned components use the [Lumen EULA](LICENSE). Read it before installing
or updating; redistribution and commercial derivatives need written permission.
Earlier license grants and [third-party rights](THIRD_PARTY_NOTICES.md) remain
valid. The installer includes both documents in the user bundle; system packages
include them under `/usr/share/licenses/lumen`. Proprietary distribution of the
PyMuPDF integrations remains subject to [licensing clearance](LICENSE-PLAN.md).

Supported full-desktop target: Arch Linux/CachyOS, KDE Plasma 6, logged in as a
normal user. Install Plasma and a display manager through your distribution first.
Lumen supplies its applications, applets, themes, decorations and wallpapers;
it uses KDE's compositor, tray, clock, task manager and pager.

## GitHub access on a fresh computer or VM

**The repository is private.** Your GitHub account must be granted access to
`ativaro/lumen`. Signing in to your Linux desktop or to GitHub in a browser does
not by itself authenticate Git in the terminal. A new VM needs its own Git
authentication, even when the same account already works on the host computer.

Inside the VM's KDE Plasma session, install Git and the GitHub CLI, then sign in:

```bash
sudo pacman -S --needed git github-cli
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
```

The first command may ask for your **VM/Linux password** to install packages.
Run the remaining commands as your normal user, **without `sudo`**. Follow the
browser sign-in, enter the one-time code if prompted, and select the **GitHub
account with access to Lumen**. The final command configures Git to use that
GitHub CLI login. If Git already has working credentials in this VM, you can skip
this setup.

Check repository access before installing:

```bash
git ls-remote https://github.com/ativaro/lumen.git HEAD
```

Success prints a commit identifier followed by `HEAD`. **Do not replace `ativaro`
in the URL**: it is the repository owner, not your VM username or a login field.

If authentication still fails:

- **`Authentication failed`, `Invalid username or token`, or password authentication
  unsupported:** GitHub does not accept a normal account password for HTTPS Git
  operations. Use the browser login above; do not paste a password or token into
  the installation command.
- **`Repository not found` or HTTP 404:** check the signed-in account with
  `gh auth status --hostname github.com` and open
  [the repository](https://github.com/ativaro/lumen) in a browser signed into that
  same account. If it cannot access the repository, the account needs access from
  the repository owner. Changing your Linux username does not grant access.
- **The old `curl … | bash` command fails:** it downloads without Git credentials
  and cannot access the private repository. Use the authenticated clone below.

See GitHub's [authentication documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)
and [GitHub CLI credential setup](https://cli.github.com/manual/gh_auth_setup-git).

## One-command installation

Inside your Plasma session, run this as your normal user (do not prefix it with sudo):

```bash
git clone --branch main --single-branch https://github.com/ativaro/lumen.git && bash lumen/bootstrap.sh
```

Run from a directory that does not already contain `lumen`, after completing the
[GitHub access check](#github-access-on-a-fresh-computer-or-vm) above.
To update an existing Lumen installation, run
from **any directory** in your desktop session as your normal user. Neither an
installed Updater nor the original checkout is needed:

```bash
(d="$(mktemp -d)" && trap 'rm -rf -- "$d"' EXIT && git clone --depth 1 --branch main --single-branch https://github.com/ativaro/lumen.git "$d/lumen" && bash "$d/lumen/bin/lumen-updater")
```

The update command downloads and opens the latest graphical **Lumen Updater**,
then removes its temporary download when the window closes. It uses the existing
Lumen Python/Qt runtime and requires Git with private repository access. Review the
selection and click **Update all / Alles aktualisieren**; it does not reopen the
setup wizard. See [native updates](#native-updates) for components and permissions.

The installation script detects its local checkout automatically (`--local` remains supported),
so private clones do not trigger a second unauthenticated download. It installs
missing base dependencies through pacman/sudo, copies Lumen into
`~/.local/share/lumen` (`$XDG_DATA_HOME/lumen` when set), then opens **Set up Lumen**.
The checkout and installed application files stay local. The bootstrap requests elevated rights
only for missing base system packages. The bootstrap also installs GCC/pkgconf and Qt 6 development files for the small native window-capture helper; no manual build step is needed.
Internet access, sudo access for missing packages and an existing KDE Plasma 6 session are required.
It does not install a Linux distribution, display manager or Plasma session.

If the repository is made public in the future, the download-only route is:

```bash
curl -fsSL https://raw.githubusercontent.com/ativaro/lumen/main/bootstrap.sh | bash
```

This public command does **not** work without authentication while the repository
is private. Its downloaded source is safely extracted into a temporary directory.

## Interface language

Lumen supports German and English. **System language** selects German for a
German locale and English otherwise. Choose explicitly in the first setup step
or **Settings → Lumen → Interface language**. Reopen applications after changing
the setting; Plasma panels use it at their next start/login. Notes, filenames,
existing conversations and other user content are preserved as written.
`LUMEN_LANGUAGE=de` or `LUMEN_LANGUAGE=en` overrides the preference for a launch.
Application-menu entries and external KDE dialogs follow the desktop language.
Dictation has its own recognition-language setting; changing the interface does
not replace an installed text-to-speech voice.

In the wizard, set up OpenCode and the provider, optionally add local speech,
then choose **Activate Lumen desktop** under **Your desktop** to apply the selected
theme, window decorations, wallpaper and panels. This uses the existing desktop
backup mechanism. **Next** leaves the current desktop in place. Existing provider
settings and speech models are reused; the document workshop remains disabled until
enabled in Files settings. The wizard can be closed and resumed later from
**Settings → Setup** or `~/.local/share/lumen/bin/lumen-setup-wizard`.

The desktop uses three separate top islands from 960 logical pixels upwards,
including typical 1024/1280-pixel VM displays; narrower displays use one compact
bar. After updating an older single-bar installation, run the wizard's **Activate
Lumen desktop** once more. Existing Lumen layout markers are upgraded after the
replacement panels have been created; repeating setup does not duplicate panels.
The previous desktop configuration is backed up before applying the layout.
If speech is not yet configured, the panel microphone keeps Search open and offers
**Set up speech**, opening the speech-input settings directly.

The update command uses a fresh temporary checkout and leaves your development
checkout untouched. Running `bootstrap.sh` again
reinstalls the user bundle and opens the setup wizard; use the Updater for normal
updates. Download or package errors are reported before continuing.

### What the one-liner installs

The user bundle contains Lumen, Files, Search, Wissen, Translate, System, Inbox,
Reader, Projects, Household and the combined **Meeting & Radio** window,
**System** also contains Sound and Work modes. All desktop themes, decorations,
wallpapers and panels are included. Both Meeting/Radio
launch commands remain supported. OpenCode, speech models and optional tools are
prepared through the wizard, reusing an existing installation when available.

The Vault backup engine, SMB discovery and keyring integration are included.
The four-step backup wizard is part of the separate native UI described below;
the standard bundle opens the Python backup configuration. Restic and network
dependencies can be added through setup. Backups
need your source/target choices and a separately stored recovery key; no personal
backup job or network password is distributed in Git.

The **native credential vault is a separate prerelease**. The standard one-liner
installs the backup app and Vault integration code, but does not build the Rust/C++
credential UI. See [native Vault installation](native/vault-ui/README.md) for its
explicit build/install procedure and current qualification limits. An existing
native installation and encrypted vault are preserved; update its binary with that
separate procedure. Updating Python files alone does not rebuild native binaries.

The Arch package workflow below is an alternative for a system-wide installation.

## Install the package

```bash
sudo pacman -S --needed base-devel git pyside6 python-gobject python-pillow \
  python-dbus qt6-tools plasma-workspace plasma-desktop kde-cli-tools \
  breeze-icons kio-extras kio-fuse poppler ffmpeg libnotify \
  wireplumber libpulse networkmanager systemsettings
git clone https://github.com/ativaro/lumen.git
cd lumen
./packaging/arch/build-package.sh --install
lumen-desktop-setup --apply --replace-panels
```

Run the last command **as your normal user inside Plasma**, without sudo.
It backs up the affected desktop configuration, replaces existing panels,
selects Glas with matching title bars and sets the Lumen Lichtstrom wallpaper.
No other user's layout, saved files, credentials or accounts are imported.
Re-running it keeps existing Lumen panels instead of creating duplicates.

To keep the current desktop layout, use `lumen-desktop-setup` without arguments:
all four themes and eleven wallpapers become available without activating them.
Choose wallpapers in KDE's wallpaper settings and themes in Lumen → Settings.
`--theme graphite`, `--theme atelier` and `--theme midnight` are also supported
alongside `--apply`.

## Install for one user instead

With the same dependencies installed, run `./install.sh --desktop` from the clone.
This installs into `~/.local/share/lumen` and applies the same desktop layout.
Omit `--desktop` to install resources and applications without changing the layout.
The corresponding setup command is then
`~/.local/share/lumen/bin/lumen-desktop-setup`.

## AI engine and personal settings

On first launch, the native **Lumen einrichten** wizard checks the installed
components. Reopen it in **Einstellungen → Einrichtung** or with
`lumen-setup-wizard` (user install: `~/.local/share/lumen/bin/lumen-setup-wizard`).
On Arch/CachyOS it can install OpenCode and selected preview/network tools through
pacman and the desktop's password dialog. Existing standalone OpenCode installations
are reused. The **KI-Anbindung** step reads configured providers and models; API-key
providers, including Ollama Cloud, can be connected without a terminal. OAuth and
other login methods still use OpenCode's existing provider setup. Listing configured
models does not verify a cloud account's credentials or send a test prompt.
On a fresh profile, Lumen automatically selects and saves an available free model
from connected providers (preferring OpenCode Zen). Selection uses the live
catalogue's zero input/output/cache prices and tool support, not hard-coded model
names. The wizard displays the chosen model above **Modell anpassen**. The first
conversation also sets up this default if the wizard was skipped. Existing Lumen
and explicit OpenCode model choices remain in use. If no confirmed free model is
available, Lumen asks for a selection instead of silently choosing a paid model.
Loading the catalogue does not guarantee provider uptime or available quota.
OpenCode Zen currently may reject free-tier requests when tools are disabled
(see [upstream issue #51315](https://github.com/anomalyco/opencode/issues/51315)).
This can affect Lumen's restricted proposal/project actions even when ordinary
chat works. Lumen keeps those restrictions; use another configured model for
affected actions rather than granting tools solely to bypass the provider error.

The optional **Mit deiner Stimme** step installs a pinned, checksum-verified
whisper.cpp executable and a multilingual Small Q5 model (190 MB) into
`$XDG_DATA_HOME/lumen/speech` (default `~/.local/share/lumen/speech`). Existing tools
and selected local models are reused. The build uses the CPU and at most four build
threads; missing cmake/gcc/make/PipeWire packages require native authorization.
Downloads/builds can be cancelled; package transactions must finish first.
The microphone test records only on a click, for at most 60 seconds, and never sends
its transcription. Dictation is available through the shared conversation's **··· →
Diktieren** menu. Missing speech components open this setup step. The **Sprachgespräch einrichten** button also installs Piper 1.8.0 in a private
Python virtual environment and a checksum-verified German Thorsten voice (63 MB).
Continuous turns use the existing OpenCode provider; speech recognition and speech
output stay local. Interrupt output with the native button. Microphone sensitivity
and pause duration are configurable from the conversation menu.

OCR (`tesseract`, German/English data) and the PDF workshop (`python-pymupdf`) are
additional dependency choices. Offline NAS copies and file versions are enabled
per folder from Files; their contents and settings remain in private user state.
The version watcher starts on login only when folders have been selected.

The wizard requires Lumen's Python/Qt dependencies, installed by the one-command
installer or the Lumen package, or checked by `install.sh`. The bootstrap installs
these before opening the wizard.
`lumen-setup` remains the separate MCP/commands integration helper (user install:
`~/.local/share/lumen/bin/lumen-setup`); it is not renamed or replaced by the wizard.
The MCP helper uses the shared Qt6 runtime through `lumen-mcp`. Existing MCP
environment and enablement settings are preserved. See [MCP tools and access](MCP.md)
for Files, Wissen, tasks, settings, Vault and Inbox integration.
Files, native search, desktop controls and themes also work without an AI provider.
Saved NAS connections, knowledge folders, tasks, conversations, API credentials
and model choices are configured by each user; none are included in the repository.
Report schedules and automatic tool approval remain opt-in.

Lumen respects the system's document associations. If PDF opening differs from
other documents, choose a PDF application in KDE's default-application settings.
No particular office suite or browser is imposed by this installer.

## Share a model-setup diagnostic

If checking the engine fails or the model list remains empty:

1. Open **Settings → Setup → AI connection** and run the connection check.
2. Click **Copy diagnostics / Diagnose kopieren** on the same page.
3. Paste the report into your support conversation or issue.

The report includes Lumen's installed revision/code fingerprint, OpenCode/Python/Qt
versions, the setup stage, HTTP status, response format and model counts. It omits
API keys, auth headers, response bodies, conversation contents, personal paths and
custom provider/model names. Nothing is uploaded automatically. A hung/missing
version command is marked unavailable after five seconds; the report is copied
without waiting for that process to exit. Unreadable source files or startup
metadata missing after an update are marked unavailable. Other collection errors
produce an explicitly partial report with only the error type, never exception
text. Clipboard failures are shown and allow retrying. After updating Lumen,
fully quit and restart it before checking again.

Diagnostic v2 also retains the process exit code, crash/start/timeout outcome,
startup duration and a fixed error category after the engine has stopped.
Raw startup output is never copied: invalid-config errors can include credentials
from the configuration file. The error remains visible after copying the report.
An installed, version-compatible executable can still fail before any model API
request; an empty `requests` list at `engine_start` therefore requires checking
the startup error, rather than changing models or repeatedly reinstalling OpenCode.

If startup reports **Database is not empty and has no session table**, the selected
SQLite database has a schema the managed OpenCode v1 engine cannot use. For example,
an inherited `OPENCODE_DB` can point at another OpenCode version's database.
Lumen checks the table names read-only and uses
`$XDG_DATA_HOME/opencode/lumen-v1.db` (default
`~/.local/share/opencode/lumen-v1.db`) for this specific conflict. Once created,
that store is reused across Lumen restarts. The original database is not reset,
renamed or imported; its conversations remain there. OpenCode configuration and
`auth.json` stay in their existing locations. Credentials stored only in another
version's incompatible database may need reconnecting in Lumen.
Working v1 databases retain their existing location and conversations. Unreadable,
locked or corrupt databases still report their original failure instead of being
silently replaced; explicit external engine binaries and `:memory:` are unchanged.
The diagnostic reports `engine_database: lumen` when isolation is used and
`startup.hint: database_schema` if this schema error still occurs.

## Recover the previous desktop

The setup command prints a backup under
`~/.local/state/lumen/settings-backups/desktop-…/`.
Log out of Plasma, switch to a text console and run:

```bash
lumen-desktop-setup --restore /path/to/printed/backup
```

Then log in again. The restore command refuses to write over a running Plasma
session. Lumen resources remain installed; user documents and app data are preserved.

## Verify a build

Use a temporary HOME and XDG directories for tests; never use your normal desktop
configuration as a test fixture. See [PUBLISHING.md](PUBLISHING.md).

## Qt 6 runtime

All desktop applications now require PySide6/Qt 6 (Widgets, QtQuick, QtSvg and
QtDBus). The Arch bootstrap installs `pyside6`. For an existing user
installation without that system package, `bin/lumen-python --install-runtime`
installs the shared user runtime; every Lumen starter then uses it. Settings and
libraries keep their existing paths. The search pilot has become the normal
search; `lumen-search-preview` remains an alias. See [SEARCH-PREVIEW.md](SEARCH-PREVIEW.md).

## Native updates

Start `lumen-updater`, or use Lumen → Updater in the top panel, Lumen Apps, or
Settings → Maintenance. Checking fetches
private `main` into `$XDG_CACHE_HOME/lumen/updater/source`; installation uses the
exact reviewed commit. A changed checkout is refused. User and system bundles are
both updated when installed. The existing installers retain data/settings and
refresh app launchers, desktop assets and integrations without replacing panels.

Lumen's native **Echo** window controls sit on the right (minimize,
maximize/restore, close), including Files, tools, settings and the setup wizard.
The symbols are 30% smaller than the Echo design preview, with independent
32 × 32 logical-pixel mouse targets and native display scaling. Dialogs retain
their supported window actions. All four Lumen palettes include Echo.

Updates migrate a selected older Lumen decoration to Echo, saving the previous
theme and button arrangement under `$XDG_STATE_HOME/lumen/settings-backups`.
Panels, wallpaper and non-Lumen window themes are preserved. As a native KWin
decoration, Echo also applies to other applications using system window frames.
After a direct package upgrade (or the first update from an older system-only
Updater), run `lumen-desktop-setup --refresh-decoration` as your normal Plasma
user. Repeating this command preserves an already installed Echo arrangement.

Only installed optional components are offered: compatible OpenCode, Qt runtime,
dictation, installed voices/models, image search, calendar and backup runtimes.
These use Lumen's tested/pinned versions, not unrestricted upstream upgrades.
The first check offers verification of these existing components; subsequent
checks compare the corresponding installer definitions with the last successful
run. New extensions still belong in the setup wizard. The native Vault is only
rebuilt if it was explicitly installed, with its existing license checks, locked
Rust dependencies and build tests. Its build environment must still be present;
the existing isolated `lumen-dev` toolchain is reused where available.

Linux packages (`pacman -Syu`) and Flatpaks are explicit optional selections.
System changes use Polkit. No AUR packages or unrelated standalone applications
are updated. Open apps are not force-closed; reopen them after an update and log
in again for panel changes. A running installation cannot be closed mid-step.
Failures remain visible, and successfully updated components are retained on retry.

Update state is private/local under `$XDG_STATE_HOME/lumen/updater`. No credentials,
notebooks, vault data, personal configurations or user files are sent to GitHub.
Installation identity is stored in `install.json` alongside each runtime.

## Screen companion

Open **Lumen Companion** from Apps/Search, or choose **Lumen begleitet mich** in
Lumen's attachment menu (Files: additional context actions). `lumen-vision companion`
opens the same sidecar. Select one application window, enter a goal and review the
local preview before sharing it. Enter sends; Shift+Enter inserts a line. Existing
local voice setup is reused. A vision-capable configured model is required.

Optional change monitoring checks at most every five seconds, requires two stable
changed frames, and pauses after 30 requests or 20 minutes. It is available only
when AT-SPI exposes an unambiguous window tree without visible password fields.
Unknown protection state falls back to manual image approval; visible secrets in
unmarked fields cannot be detected reliably. Pause before entering them. Minimize,
pause or close stops capture and voice. Lumen Vault must be closed.

Only the selected KWin window UUID is captured; there is no desktop/active-window
fallback. KDE Plasma with OpenGL compositing, python-dbus and AT-SPI are used. The
installer builds a dedicated Qt/DBus executable and registers its own restricted
interface permission, never a general Python interpreter's permission. Direct
`install.sh` runs require `g++`, `pkg-config` and Qt 6 Core/DBus development files.
On CachyOS/Arch, missing helper build dependencies request graphical administrator
authorization before application files are replaced; the update one-liner handles
the same dependencies through the bootstrap.

Images are held in memory and go to the configured model provider only after
consent (including optional automatic sharing). Engine/provider history may retain
them; this feature does not promise ephemeral provider storage. The companion
has no execution tools and does not automatically learn screen content into Lumen
Wissen. It explains the next step; the user operates the target application.
