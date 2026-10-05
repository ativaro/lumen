# Lumen — AI-first desktop for CachyOS

## Install → setup wizard

**Arch/CachyOS · KDE Plasma 6 · run as your normal user.**
This repository is currently **private**. With Git installed and your GitHub
account authorized to access `ativaro/lumen`, run from a directory without a
`lumen` checkout:

```bash
git clone --branch main --single-branch https://github.com/ativaro/lumen.git && bash lumen/bootstrap.sh
```

The installer prepares missing dependencies, installs Lumen locally and opens
the graphical wizard for AI, speech and desktop setup. Git authentication is
handled by your Git credential helper; never put a token in the command or README.
Desktop panels, wallpapers and decorations are included; activate them in the
wizard when ready. See [installation and recovery](INSTALL.md).

## Update → one command

From the directory containing your original `lumen` checkout, run as your normal user:

```bash
git -C lumen pull --ff-only origin main && bash lumen/bin/lumen-updater
```

This downloads and opens the latest **Lumen Updater**. Review the selection and
click **Update all / Alles aktualisieren**. It updates installed Lumen apps,
panels, themes, the compatible engine and installed local extensions without
reopening the setup wizard. Your data, vault, settings and valid models are retained.
The checkout must be clean and on `main`; private GitHub access is still required.

Already have the Updater installed? Run `lumen-updater` from any directory, or open
**Lumen → Updater** in the top panel, **Lumen Apps → Lumen Updater**, or
**Settings → Maintenance**. This also checks GitHub for the latest Lumen version.
System packages and Flatpaks are optional selections; system changes may ask for
your password. Reopen apps after updating and log in again to reload the panels.

**Deutsch / English:** choose **Settings → Lumen → Interface language**, or select
a language in the setup wizard. System language is the default. Reopen apps to
apply a change; desktop panels pick it up when Plasma starts again.

<details>
<summary>Public download command — available only after the repository becomes public</summary>

```bash
curl -fsSL https://raw.githubusercontent.com/ativaro/lumen/main/bootstrap.sh | bash
```

This unauthenticated command cannot download a private repository. It is shown
here for a future public release; the repository remains private.
</details>

Lumen is an AI extension for CachyOS, combining conversations, file management,
durable tasks, selected knowledge, reusable workflows and system diagnostics.
[OpenCode](https://opencode.ai) is the background engine; the product and package
are **Lumen**. The desktop bar has a system overview on the left, unified search and conversation in the middle, and settings on the right. **Lumen Files**
(`lumen-files`) opens a separate file-manager window with the same settings and
AI integrations. The assistant also keeps its integrated Files page.

[Bedienung, Datenschutz und Migration](LUMEN-GUIDE.md) · [Implementation contract](SPEC-lumen-os.md)

Built for **KDE Plasma 6 on Wayland** (CachyOS/Arch), but written to degrade
gracefully on other setups.

## Features

| Component | What it does |
|---|---|
| **Desktop app** (`lumen`) | One PySide6 window for conversations, files, system status, tasks, knowledge, workflows and models |
| **Workplace** | Projects resume selected folders/NAS, apps, webpages and a continuation note; source availability/recent files, editable desktop modes, shared transfers and guarded history in Lumen and Files |
| **Durable tasks** | SQLite task history, process leases, interruption recovery, pause/resume/cancel, results and native file undo with conflict checks |
| **Knowledge** | Explicit folder selection, bounded local text/PDF index, source/page citations and editable memories |
| **Workflows** | Approved native steps or AI tasks; manual, interval and direct-directory-change triggers; opt-in user timer |
| **Models & context** | Main/background/local model policies, request timeout, GPU deferral, visible file/image/clipboard context, optional offline dictation and explanation mode |
| **Shared settings** | Settings button / Ctrl+, in Lumen and Files: app preferences, models, global shortcuts, panels/tray, native KDE appearance editors, services and report schedules |
| **File actions** | Explain / fix / review show a native result and progress view in Files or a compact standalone window; free chat remains separate |
| **Global shortcuts** | `Meta+Shift+O` ask · `Meta+Shift+C` explain clipboard · `Meta+Shift+V` vision · `Meta+Shift+E` explain selection |
| **Vision** | capture a screen region → opencode analyses the image (`lumen-vision`) |
| **Selection actions** | explain / translate / fix / summarize selected or copied text (`lumen-sel`) |
| **Shell integration** | `why` (explain last failed command), `vix`, `sel` — bash & fish (`shell/lumen.{bash,fish}`) |
| **Git** | `lumen-gitmsg` drafts a Conventional-Commit message from the diff |
| **KRunner runner** | Type `lumen <question>`, `ai <question>` or `oc <question>` in KRunner |
| **Plasma applet** | panel widget with agent status + quick actions (`org.lumen.agent`) |
| **Lumen Files** (`lumen-files`) | file manager with combined local/NAS libraries and visible origins, per-room collection shelves and saved workspaces, fast search, previews, tabs, gallery, disk analysis, KIO network folders, native rename/sort with preview and undo, integrated Lumen panel |
| **Lumen Vault** (`lumen-vault`) | encrypted restic backups, snapshot browsing, verified restore and opt-in schedules. The native credential vault and its guided NAS backup UI require the [separate prerelease installation](native/vault-ui/README.md) |
| **Lumen Meeting & Radio** (`lumen-meetings`, `lumen-radio`) | one window with Meeting/Radio tabs, local transcription, editable results and personal audio programmes; both starters keep the same window and retained state |
| **Lumen Translate** (`lumen-translate`) | text translation, writing styles, spelling correction and PDF layout translation |
| **Lumen System** (`lumen-system`) | retained System, Sound and Work modes tabs: live resource usage, hardware, audio and desktop presets with guarded undo |
| **Lumen Inbox** (`lumen-inbox`) | local IMAP inbox and SMTP drafts, Proton Bridge preset, CalDAV calendars, read-only ICS subscriptions and local tasks; [setup and limits](VAULT-INBOX.md) |
| **Lumen Reader** (`lumen-reader`) | PDFs, EPUBs and saved articles; reading position, highlights, margin notes, local read-aloud and cited passages in Lumen knowledge |
| **Sound in Lumen System** (`lumen-sound`) | opens the Sound tab in the existing System window: per-stream volume, mute, outputs, app rules and conversation ducking; [Reader/Sound guide](READER-SOUND.md) |
| **Lumen Wissen** (`lumen-wissen`) | direct notebook with autosave, editable titles, folder/tag collections and separate Lumen memory; explicit sharing, optional learning, corrections and forgetting; images, links, knowledge map and sourced questions; [Wissen guide](WISSEN.md) |
| **Application designs** | Glas by default, plus Graphit, Atelier and Mitternacht; shared live themes for Lumen, search, Files, the image viewer, desktop panels and their popups, with native previews in settings |
| **System watchdog** | systemd timer checks failed units, kernel errors, disk, GPU temp; automatic opencode analysis |
| **App recovery** | Independent crash/hang detection for Lumen, Files and search; private reports and restoration of views and drafts |
| **Daily digest / nightly report** | scheduled summaries (`lumen-digest`, `lumen-nightly`) |
| **MCP server `cachyos`** | read tools `systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `sensors`, `kwin`, guarded `cmd` — plus **opt-in action tools** (`notify`, `restart_unit`, `media`, `wallpaper`, `screenshot`) behind `LUMEN_MCP_ACTIONS=1` |
| **opencode commands/skill** | `/sync`, `/sysreport`, `/fix` + `lumen-admin` skill |

## Native workplace

First launch offers **Lumen einrichten**, also available from **Einstellungen →
Einrichtung** and `lumen-setup-wizard`. It checks optional dependencies, reuses
OpenCode/provider settings, connects API-key providers and prepares offline dictation
with a verified local speech engine/model and a microphone test. Installs and
downloads require an explicit selection; the test sends no text to a provider.
See [installation and setup](INSTALL.md#ai-engine-and-personal-settings).

Files now includes offline NAS working copies with conflict choices, OCR and opt-in
image-content search, independent file versions, reusable personal actions and a
PDF page workshop with real redaction. The shared search/chat has continuous voice
turns with local Whisper and Piper. See [feature details and limits](files/README.md).

Open **Arbeitsplatz** in Lumen (`lumen --page workplace`) or the Files menu.
Projects extend saved file rooms. Choose sources, programs and URLs explicitly;
**Aktuellen Stand merken** saves the current Files tabs and assistant context.
**Quellen prüfen** reads up to 5,000 entries per source in bounded subprocesses;
unavailable sources retain their last successful recent-file listing with an offline label.
**Alle Dateien gemeinsam** opens the existing origin-aware library view.

Work modes use KDE window layout/notification settings and PipeWire's PulseAudio
interface. They report individual failures and journal each changed component.
History offers guarded undo for native task/file edits, Lumen preferences, panel
settings, shortcuts and mode components. External edits block undo. Untracked AI
shell commands and actions without a safe inverse are never presented as undoable.

Transfers started by Lumen are shared across windows. Downloads continue after
closing the overview; HTTP resume requires a matching validator and byte range.
Copies/moves retry remaining entries without overwriting existing destinations.
Browser downloads are not intercepted. Stalled workers stop after two minutes
without progress; original files and staged destination data are preserved.
Large directory operations beyond 5,000 metadata entries are logged without undo.

The desktop has three purpose-specific surfaces: **Dein System** on the left
(tasks, system status, workplace and files), **Suchen oder fragen …** in the middle,
and **Einstellungen** on the right (native controls, Lumen/Files preferences and
Lumen themes and KDE settings). The middle opens `lumen-search`: one input finds installed apps and
files in the home folder; a question continues as a conversation in the same window.
Enter opens the selected result, Ctrl+Enter asks, and follow-up questions keep the
conversation. Completed and cancelled tasks have an **×** in the system overview and a
**Schließen** (completed) or **Löschen** (cancelled) button in the task page. This hides them across both displays
and subsequent starts; result/history remain under **Geschlossene Aufgaben anzeigen**.
A later task update makes it visible again. Active tasks cannot be dismissed. The scan is asynchronous, bounded to 100 results / 100,000 inspected
entries and eight seconds. It starts no model until a question is submitted.
`lumen-settings` opens preferences directly. The existing KRunner shortcut remains
available. The role-specific applets share their QML implementation and are installed
as `org.lumen.system`, `org.lumen.search` and `org.lumen.control`.

## Complete desktop installation

The repository includes all Lumen applets, four matching Plasma/Aurorae themes,
eleven wallpapers and a portable panel layout. No pre-existing Lumen or MacTahoe
installation is required. See [INSTALL.md](INSTALL.md) for a fresh Arch/CachyOS
setup and recovery instructions.

`lumen-desktop-setup` installs the resources without changing the active desktop.
`lumen-desktop-setup --apply --replace-panels` explicitly activates the Glas theme,
Lichtstrom wallpaper, system/search/control panels and native task/pager docks.
Existing desktop configuration is backed up first. Wide screens use three top
islands; smaller screens combine the same controls into one top panel.
Repeated setup does not duplicate Lumen panels. Application-drawn title bars remain
controlled by their applications.

Artwork and licenses are in [desktop/CREDITS.md](desktop/CREDITS.md).

## Crash detection and recovery

Lumen, Files and search run with a small independent supervisor. It records abnormal
exits (including signals), captures Python fault traces and checks the Qt event loop
through a pipe. After 60 seconds without a response, a desktop notification offers
waiting or ending and reopening the application. It never kills a slow window on
its own and never retries an action automatically.

The next normal launch offers restoration of an interrupted view: Files tabs and
active tab, Lumen page, search/conversation mode and conversation drafts. The last
20 text messages are retained as a local preview; the engine keeps the full history.
Restoration does not contact the engine or replay prompts, approvals or file operations.
Unsaved image edits are not recovered. Each launch restores one interrupted session;
other unacknowledged sessions remain available on subsequent launches.

**Settings → Stabilität** controls monitoring for newly started apps and opens local
reports under `$XDG_STATE_HOME/lumen/crashes` (normally `~/.local/state/lumen/crashes`).
Reports and drafts are private to the user and are never uploaded automatically.
Normal sessions are removed when closed; old inactive records are pruned on startup
to leave room for at most 20 retained runs. Diagnostic logs are bounded to about 1 MB.
Existing windows gain supervision when restarted. No additional system service is needed.

## Requirements

**Required:** `bash`, Python 3, PySide6 with QtSvg, QtQuick and QtDBus, PyGObject/GIO, Pillow. AI features additionally need [OpenCode](https://opencode.ai) with its server API.

The wizard installs a SHA-256-verified **OpenCode 1.18.34** runtime for Lumen
(Linux x86_64/ARM64, about 61 MB) when setting up the assistant. An existing
OpenCode installation is initially reused. If “Check connection and load models”
fails, choose **“Set up compatible engine”** and the wizard retries after installation.
The runtime lives in `$XDG_DATA_HOME/lumen/engine/1.18.34/` (by default
`~/.local/share/lumen/engine/1.18.34/`); it takes precedence for Lumen without
replacing the system/CLI OpenCode or overwriting provider credentials. OpenCode 2's
changed API is not supported by this client yet. An explicit `LUMEN_OPENCODE_BIN`
override must be removed before using the managed runtime.

**Optional** (individual features need these):
- `notify-send` (libnotify) — watchdog notifications
- `nvidia-smi` — GPU metrics
- KDE Plasma 6 + Dolphin + KRunner — for the KDE integrations

## Install

### One command → setup wizard (Arch / CachyOS)

For the current private repository, use the authenticated clone command at the
top of this README. Inside a logged-in Plasma session, an existing clone needs:

```bash
bash lumen/bootstrap.sh --local
```

This uses your local checkout, installs missing Python/Qt dependencies (with sudo when
needed), copies the applications into `~/.local/share/lumen`, and opens the native
setup wizard. No build tools are needed for Lumen itself. The wizard completes
OpenCode/provider setup, optional speech features and desktop activation. Choose
a theme and **Lumen-Desktop aktivieren** to apply panels, wallpaper and decorations
after a backup; skipping this step keeps the current desktop. The script needs
internet access and an existing Plasma desktop. Re-running opens the wizard
again and preserves personal settings and models. See [INSTALL.md](INSTALL.md).

### Arch / CachyOS — system-wide package

```bash
# from a local build
git clone https://github.com/ativaro/lumen.git lumen && cd lumen
./packaging/arch/build-package.sh --install

# activate the full desktop as your normal user, inside Plasma:
lumen-desktop-setup --apply --replace-panels
```

The package supports repository or standalone OpenCode installations and installs the desktop integration
in `/usr/share`. New schedules are opt-in. The build installer preserves legacy
reports and service preferences when migrating `opencode-lumen`; direct installation over the old package stops
on file conflicts instead of invoking its destructive uninstaller.
Known legacy app launchers are backed up and redirected to the current installation,
so cached screenshot shortcuts and an already-running KRunner use the current UI.
Custom launchers are preserved.

### Any distro — per-user install

```bash
git clone https://github.com/ativaro/lumen.git lumen && cd lumen
./install.sh
```

Options:

```bash
PREFIX=~/.local/share/lumen ./install.sh   # custom install prefix
./install.sh --no-timer                             # skip systemd timer
./install.sh --no-mcp                               # skip opencode MCP/commands/skill
```

After installing (either way):

1. Register the engine integration (skip if you used `install.sh`):
   ```bash
   lumen-setup              # MCP 'cachyos' + /sync,/sysreport,/fix + lumen-admin skill
   ```
2. **Restart opencode** so MCP/commands/skill are picked up.
3. Reload KRunner if the `ai …` trigger is missing: `kquitapp6 krunner`
4. Open the assistant from the panel/menu (**Lumen**) or run `lumen`.
   Open the file manager with **Lumen Files** or `lumen-files [folder-or-URL]`.

Launching Lumen again from the menu, panel or main shortcut activates its existing
window and keeps the current conversation and draft. Explicit file actions,
prompts, selections, pages or working directories still open their own window.
Activation uses the desktop session bus; without D-Bus the app opens normally.

Updates rebuild KDE's application cache without deleting live shortcut components.
If an existing shortcut's `Exec` path changes, KDE may keep the previous path until
the next login. Existing `plasma_icons/lumen.desktop` panel copies are updated with
executable permissions so Plasma can launch them.

## Configuration

All scripts read these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LUMEN_OPENCODE_BIN` | managed Lumen engine if installed, else `opencode` in `$PATH` or `~/.opencode/bin/opencode` | explicit OpenCode binary override |
| `LUMEN_WORKDIR` | `~/Documents/work` | default working directory |
| `LUMEN_DATA` | `~/.local/state/lumen` | private task/workflow/knowledge database |
| `LUMEN_STATE` | `~/.cache/lumen` | state/report/cache dir |
| `LUMEN_WATCH_ANALYZE` | `1` | `0` disables the automatic watchdog analysis |
| `LUMEN_WATCH_MODEL` | *(provider default)* | model for the watchdog analysis |
| `LUMEN_MCP_ACTIONS` | `0` | `1` enables the writing MCP action tools |
| `LUMEN_SEL_LANG` | `Deutsch` | translate target for `lumen-sel translate` |
| `LUMEN_VISION_PROMPT` | *(built-in)* | override the vision prompt |
| `LUMEN_GITMSG_STYLE` | Conventional Commits | commit message style |

### Shell integration

Add to `~/.config/fish/config.fish` (fish) or `~/.bashrc` (bash):

```fish
source /usr/share/lumen/shell/lumen.fish
```

Then `why` explains the last failed command, `vix` runs vision on a region and
`sel fix` corrects the selected text.

## Uninstall

```bash
lumen-setup --uninstall     # opencode MCP/commands/skill (system package: do first)
./uninstall.sh              # per-user install
sudo pacman -R lumen   # system package
```

## Optional: system-wide sudo helper

opencode's non-TTY tool calls re-prompt for a password unless sudo caches
credentials user-wide. This is **optional** and needs root:

```bash
sudo ./install-system.sh      # adds /etc/sudoers.d/20-opencode-sudo-cache
sudo ./install-system.sh --uninstall
```

It sets `timestamp_type=global` and `timestamp_timeout=15`, validates the
sudoers file with `visudo -cf` before installing, and configures a graphical
askpass (`ksshaskpass`/GNOME/OpenSSH) in `/etc/sudo.conf` if none is set.

## Layout

```
bin/                      helper scripts + GUI backend (installed to PREFIX/bin)
agent-app/main.py         Unified native Lumen window
plasmoid/                 Plasma panel applet (org.lumen.agent)
files/                    Integrated files, tasks, knowledge and assistant (PySide6)
shell/                    bash + fish integration (why/vix/sel)
data/                     .desktop / krunner / dbus / autostart templates
systemd/                  watchdog user units
system/                   system daemon, watchdog, notify, dbus policy
etc/sudoers.d/            optional system-wide sudo cache drop-in
opencode-command/         /sync, /sysreport, /fix
opencode-skill/           lumen-admin skill
packaging/arch/           PKGBUILD, build-package.sh
distro/aur/               AUR tree tooling
distro/cachyos/           local pacman repo tooling
install.sh / uninstall.sh
install-system.sh         optional root-only tweaks
```

## Notes

- The private GitHub repository stores source and history only. GitHub Actions
  are disabled. Tests and package builds run locally; future homelab automation
  can use Forgejo. See [PUBLISHING.md](PUBLISHING.md) for local verification.
- Each window owns a password-protected OpenCode server on a random loopback port.
  Lumen conversations are tagged and listed for the selected working directory;
  existing terminal conversations are never continued implicitly.
- The existing OpenCode configuration, provider login, instructions and MCP tools
  remain in effect. Lumen does not rewrite that configuration.
- Permission requests offer Allow once / Reject. The visible **Nicht mehr nachfragen**
  checkbox optionally approves tool permissions automatically, including commands
  and file changes, for this conversation and its verified child tasks. It defaults
  off and is remembered for newly opened Lumen windows and Files panels; existing
  windows keep their visible setting. Explicit engine denials and locked proposal
  tools remain in force. Questions still use native forms.
  The composer offers task mode or read-only analysis mode. Closing an active
  conversation asks before stopping it. Images/PDFs selected as context are sent
  as attachments; other paths are supplied as text context.
- The shared panel uses PySide6/Qt 6 Widgets; search uses QtQuick/QML. Terminal launchers and
  the temporary text-file bridge are no longer used for conversations.
- `lumen-sel translate|fix|summarize` copies successful answers back to the clipboard.
  Every answer can also be copied from the panel.
- Per-user installation writes under the user home. The pacman package installs
  under `/usr` and keeps the existing system services on upgrade.
- Tested on KDE Plasma 6.7 on Wayland with `nvidia-open`.

## License

The current license for Lumen-authored code is MIT — see [LICENSE](LICENSE).
The repository remains private. The proposed direction is dual licensing: an
AGPLv3 community version and paid licenses for proprietary derivatives. Compliant
AGPL redistribution, including sales, would remain permitted without a license fee.
This proposal is not yet a license change.
See [the licensing plan and dependency constraints](LICENSE-PLAN.md).

## System-wide install (Arch / CachyOS)

For a system package instead of the per-user install:

```bash
./packaging/arch/build-package.sh            # build lumen-*.pkg.tar.zst
sudo pacman -U packaging/arch/lumen-*.pkg.tar.zst
```

or via a local pacman repo:

```bash
./distro/cachyos/make-repo.sh
# then add the printed [lumen] block to /etc/pacman.conf
sudo pacman -Sy && sudo pacman -S lumen
```

The package installs to `/usr` and **enables its services by default
(opt-out)** — install and it just works; disable anything you don't want:

```bash
sudo systemctl disable --now lumen-agentd.service        # D-Bus service
sudo systemctl disable --now lumen-watch.timer     # system watchdog
sudo systemctl --global disable lumen-notify.path  # per-user notify
systemctl --user disable --now lumen-notify.path   # this session
```

Architecture: the **system watchdog** runs as root and writes findings to
`/var/lib/lumen/findings.md`; a **per-user path unit** picks that up,
notifies the desktop and runs the opencode analysis in the user's context.
A small **D-Bus system service** (`org.lumen.Agent`) exposes read-only
`GetSummary` / `GetFindings` / `RefreshWatch`.

Upgrades keep your choice: if you disabled a service, `post_upgrade` does not
re-enable it.

> Note: never `systemctl restart dbus` to apply a policy change — the bus
> reloads policies itself and a restart tears down the running desktop session.

## Native UI checks

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -v
./bin/lumen-agent-app
./bin/lumen-files
```

`files/test_assistant.py` exercises streaming messages, permission isolation,
question forms, cancellation and authenticated API requests against a local fake
server. Existing file/gallery/network tests run alongside it. The implementation
uses the [OpenCode server API](https://opencode.ai/docs/server/); see
[NATIVE-LUMEN.md](NATIVE-LUMEN.md) for the scope and runtime checks.

## Eigenständige Werkzeuge

Lumen Meeting & Radio, Lumen Digitaler Haushalt und Lumen Projekte
werden mit eigenen Startern installiert. Meeting und Radio teilen sich ein Fenster
mit Tabs; beide bisherigen Startbefehle bleiben verfügbar. Funktionen, Speicherung, Einrichtung
und Grenzen: [Desktop-Werkzeuge](TOOLS.md).

### Lumen System

A native, local performance overview with CPU/GPU/RAM/storage cards, activity
charts, current-user processes and device sensors. Open **Lumen System** from
Lumen Apps, the panel's System controls, or run `lumen-system`. Shared settings
retain the existing background-work preferences. Session history stays in memory;
AI analysis only starts when requested. See [measurement details](files/README.md#lumen-system).


### Sound and work modes in System

`lumen-system` opens one window with **System**, **Sound** and **Work modes** tabs.
The existing `lumen-sound` command opens its Sound tab. `lumen-system --page modes`
opens desktop modes; the Workplace entry and shared settings use the same route.
Switching tabs retains monitoring, mixer controls and mode selection. Apply/save
buttons retain their existing behavior; switching a tab changes no system setting.
Mode history includes guarded undo; existing audio rules and mode profiles keep
using their original local stores. The separate Sound app-menu entry is hidden.
