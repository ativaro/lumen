# Install Lumen on a fresh desktop

Supported full-desktop target: Arch Linux/CachyOS, KDE Plasma 6, logged in as a
normal user. Install Plasma and a display manager through your distribution first.
Lumen supplies its applications, applets, themes, decorations and wallpapers;
it uses KDE's compositor, tray, clock, task manager and pager.

## One-command installation

Inside your Plasma session, run this as your normal user (do not prefix it with sudo):

```bash
git clone https://github.com/ativaro/lumen.git && bash lumen/bootstrap.sh --local
```

**The repository is private.** Git and a GitHub account granted access to
`ativaro/lumen` are required. Authenticate through your Git credential helper;
do not paste access tokens into installation commands. Run from a directory that
does not already contain `lumen`. To update an existing checkout:

```bash
git -C lumen pull --ff-only && bash lumen/bootstrap.sh --local
```

The script uses the authenticated local Git checkout, installs
missing base dependencies through pacman/sudo, copies Lumen into
`~/.local/share/lumen` (`$XDG_DATA_HOME/lumen` when set), then opens **Set up Lumen**.
The checkout and installed application files stay local. The bootstrap requests elevated rights
only for missing base system packages. No compiler or manual package build is needed for Lumen itself.
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
Running the existing-checkout update command reinstalls the user bundle and opens the wizard even
if it was previously completed. Download or package errors stop before launching it.

The Arch package workflow below is an alternative for a system-wide installation.

## Install the package

```bash
sudo pacman -S --needed base-devel git python-pyqt5 qt5-svg python-gobject python-pillow \
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
Files, native search, desktop controls and themes also work without an AI provider.
Saved NAS connections, knowledge folders, tasks, conversations, API credentials
and model choices are configured by each user; none are included in the repository.
Report schedules and automatic tool approval remain opt-in.

Lumen respects the system's document associations. If PDF opening differs from
other documents, choose a PDF application in KDE's default-application settings.
No particular office suite or browser is imposed by this installer.

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
