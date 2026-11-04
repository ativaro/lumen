# Lumen — AI-first desktop for CachyOS

**License: proprietary [Lumen EULA](LICENSE).** Personal and internal business use
are allowed; redistribution, resale and commercial derivatives require prior
written permission. [Third-party rights and release constraints](THIRD_PARTY_NOTICES.md) remain applicable.

## Install → setup wizard

**Arch/CachyOS · KDE Plasma 6 · run as your normal user.**
This release is published **privately on Forgejo**. Your Forgejo account must have
access to `ativaro/lumen` at `forge.example.invalid`; this address must be reachable from the
computer being installed. The GitHub repository is not updated for this release.

Install Git if needed, then clone and run the installer as your normal user:

```bash
sudo pacman -S --needed git
git clone --branch main --single-branch https://forge.example.invalid/ativaro/lumen.git && bash lumen/bootstrap.sh
```

Git uses your configured credential helper or asks for your Forgejo credentials.
Use a repository-read token if your Forgejo authentication requires one. Never
embed a token in the URL, command, documentation or a support message. Keep
`ativaro` in the URL: it is the repository owner. Only dependency installation
uses `sudo`; its password belongs to the local Linux account.

The installer prepares missing dependencies, installs Lumen locally and opens
the graphical wizard for AI, speech and desktop setup. Git authentication is
handled by your Git credential helper; never put a token in the command or README.
If authentication fails, confirm repository access in Forgejo and the local Git credential helper.
Desktop panels, wallpapers and decorations are included; activate them in the
wizard when ready. See [installation and recovery](INSTALL.md).

## Update → one command

For an existing Lumen installation, run from **any directory as your normal user**.
No installed Updater or original installation checkout is needed:

```bash
(d="$(mktemp -d)" && trap 'rm -rf -- "$d"' EXIT && git clone --depth 1 --branch main --single-branch https://forge.example.invalid/ativaro/lumen.git "$d/lumen" && bash "$d/lumen/bin/lumen-updater")
```

This downloads the latest **Lumen Updater** into a temporary directory and opens it.
The temporary download is removed when the Updater closes. Review the selection and
click **Update all / Alles aktualisieren**. It updates installed Lumen apps,
panels, themes, the compatible engine and installed local extensions without
reopening the setup wizard. Your data, vault, settings and valid models are retained.
Git, access to the private Forgejo repository and the existing Lumen Qt/Python
runtime are required. Run this inside your KDE desktop session, without `sudo`.

Already have the Updater installed? Run `lumen-updater` from any directory, or open
**Lumen → Updater** in the top panel, **Lumen Apps → Lumen Updater**, or
**Settings → Maintenance**. The update source is recorded by the installer; a Forgejo installation follows Forgejo.
Older installations without a recorded source continue to use GitHub. To move an
installation to this Forgejo release, run the Forgejo installation command above;
downloading only its Updater does not silently switch the installed source.
If user and system installations have different sources, update them separately;
Lumen reports the conflict instead of choosing a source for both.
System packages and Flatpaks are optional selections; system changes may ask for
your password. Reopen apps after updating and log in again to reload the panels.

**Deutsch / English:** choose **Settings → Lumen → Interface language**, or select
a language in the setup wizard. System language is the default. Reopen apps to
apply a change; desktop panels pick it up when Plasma starts again.



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
| **Lumen Projects** | Group materials, conversations, tasks, analyses and research; link local or server sources and ask questions about their contents |
| **Durable tasks** | SQLite task history, process leases, interruption recovery, pause/resume/cancel, results and native file undo with conflict checks |
| **Knowledge** | Explicit folder selection, bounded local text/PDF index, source/page citations and editable memories |
| **Workflows** | Approved native steps or AI tasks; manual, interval and direct-directory-change triggers; opt-in user timer |
| **Models & context** | Main/background/local model policies, request timeout, GPU deferral, visible file/image/clipboard context, optional offline dictation and explanation mode |
| **Shared settings** | Settings button / Ctrl+, in Lumen and Files: app preferences, models, global shortcuts, panels/tray, native KDE appearance editors, services and report schedules |
| **File actions** | Explain / fix / review show a native result and progress view in Files or a compact standalone window; free chat remains separate |
| **Global shortcuts** | `Meta+Shift+O` ask · `Meta+Shift+C` explain clipboard · `Meta+Shift+V` vision · `Meta+Shift+E` explain selection |
| **Screen companion** (`lumen-companion`) | choose one window, review the image, and get the next step by text or local voice; optional guarded change monitoring; [privacy and setup](INSTALL.md#screen-companion) |
| **Vision** | capture a screen region → opencode analyses the image (`lumen-vision`) |
| **Selection actions** | explain / translate / fix / summarize selected or copied text (`lumen-sel`) |
| **Shell integration** | `why` (explain last failed command), `vix`, `sel` — bash & fish (`shell/lumen.{bash,fish}`) |
| **Git** | `lumen-gitmsg` drafts a Conventional-Commit message from the diff |
| **KRunner runner** | Type `lumen <question>`, `ai <question>` or `oc <question>` in KRunner |
| **Plasma applet** | panel widget with agent status + quick actions (`org.lumen.agent`) |
| **Lumen Files** (`lumen-files`) | file manager with combined local/NAS libraries and visible origins, personal collection shelves, fast search, previews, tabs, gallery, disk analysis, KIO network folders, native rename/sort with preview and undo, integrated Lumen panel |
| **Lumen Vault** (`lumen-vault`) | shared server vault in a private, device-bound window. Local restic backups remain in Lumen System; the native credential broker remains a separate capability |
| **Lumen Audio Studio** (`lumen-meetings`, `lumen-radio`) | shared server Meeting/Radio contents and editors; reviewed local recordings are handed over through Drive |
| **Lumen Compose** (`lumen-translate`) | text translation, writing styles, spelling correction and PDF layout translation |
| **Lumen System** (`lumen-system`) | retained System, Sound and Work modes tabs: live resource usage, hardware, audio and desktop presets with guarded undo |
| **Lumen Inbox** (`lumen-inbox`) | shared server mail, calendar and tasks, with the existing account and device permissions; no local mail/calendar client installation |
| **Lumen Reader** (`lumen-reader`) | PDFs, EPUBs and saved articles; reading position, highlights, margin notes and local read-aloud. Modern Office/OpenDocument content uses the shared Lumen Server reader after selecting “Inhalt auf Lumen Server lesen”; a paired server with Drive permission is required. The local original is not stored on the server. |
| **Sound in Lumen System** (`lumen-sound`) | opens the Sound tab in the existing System window: per-stream volume, mute, outputs, app rules and conversation ducking; [Reader/Sound guide](READER-SOUND.md) |
| **Lumen Notes** (`lumen-wissen`) | shared server notebook and formatted editor; no separate Notes synchronization. Local Lumen memory remains independent |
| **Project tools and skill** | paired, AI-authorized server project tools and native reviewed material/question handoffs; no local project replica |
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

Open **Lumen Projects** to group selected materials, conversations and tasks.
Projects are optional collections, not a global account or storage selector.
Drive, Photos and Notes belong to the signed-in user and remain accessible without
a project. The project details separate title/goals from selected sources;
source changes can be reviewed and cancelled before saving.

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

The **Panorama Islands** topbar runs as its own Wayland application, `lumen-topbar`.
Lumen and Files come first, followed by the active application's actual menus.
Menus stay visible while space allows; an overflow keeps them accessible on small
screens. Search, system tray, current transfers/recordings, controls, notifications
and the calendar occupy the right island. Fullscreen applications hide the bar.
The visible Start button and Meta open a searchable list of installed programs.
Lumen Apps remains a separate tab in the same launcher. Wide screens show an
inline question field, send action and microphone; small screens retain direct
question/microphone buttons. Enter sends a new question in Lumen, preserving
existing windows and drafts. The field transfers text through stdin, not shell
arguments. The microphone uses the existing voice workflow.
The native task dock remains separate. No additional navigation bar is inserted
inside Lumen applications.

System notification history and its existing actions stay in Plasma through the
invisible `org.lumen.notificationhost` background component. The bar itself does
not host Plasma applets or read task history. It reuses the same Lumen app catalogue,
controls, notification preferences and browser/Reader handoffs.

## Complete desktop installation

The repository includes the native topbar, matching themes, wallpapers and a
portable dock layout. See [INSTALL.md](INSTALL.md) for setup and recovery.
`lumen-desktop-setup` installs resources without activating them.
`lumen-desktop-setup --apply` starts and verifies the native bar before removing
Lumen's old upper panels. Existing bottom task docks remain intact. The setup
backs up desktop configuration and the previous topbar service state.
Unrelated panels are preserved. Meta opens Lumen Apps on the pointer's screen.
Application-drawn title bars remain controlled by their applications.

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
lumen-desktop-setup --apply
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
plasmoid/                 Background system notification access (no topbar UI)
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

- This private Forgejo release stores distributable source and history only.
  GitHub remains at its previous release. Tests and package builds run locally;
  see [PUBLISHING.md](PUBLISHING.md) for verification and release limits.
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

Lumen-owned components are offered under the [Lumen EULA](LICENSE), not MIT.
Personal and internal business use, local builds and internal customization are
allowed. Redistribution, resale, commercial forks, OEM editions and hosted
software offerings require the maintainer's express written permission.

This does not revoke MIT rights already granted for earlier copies. Third-party
licenses remain in force; Qt/PySide6, vendored libraries and GPL artwork are not
relicensed by this change. PDF processing uses Lumen’s own engine; the complete
distribution still needs its dependency and provenance checks. See [third-party notices](THIRD_PARTY_NOTICES.md)
and [licensing status](LICENSE-PLAN.md). The repository remains private.

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
opens desktop modes; shared settings use the same route.
Switching tabs retains monitoring, mixer controls and mode selection. Apply/save
buttons retain their existing behavior; switching a tab changes no system setting.
Mode history includes guarded undo; existing audio rules and mode profiles keep
using their original local stores. The separate Sound app-menu entry is hidden.


### Lumen Server verbinden

Im Lumen Server unter **Geräte → Auf diesem Desktop verbinden** starten, das Öffnen von Lumen zulassen und Serveradresse/Konto im nativen Dialog bestätigen. Erst danach werden Gerätezugang und Hintergrundabgleich aktiviert. Ablehnen, Ablauf oder Wiedergabe einer alten Anfrage erzeugen keinen weiteren Zugang. Der Server kann den Gerätezugang jederzeit widerrufen. Die bestätigten Server-Erinnerungen werden derzeit separat gespiegelt; automatische Verwendung im Desktop-Modell und die native Vault-Zielauswahl folgen separat.

Die beiden `files/lumen_connect*.py` sind die mitgelieferte Client-Komponente aus dem eigenständigen Lumen-Server-Repository (`desktop/`). Bei Protokolländerungen zusammen aktualisieren; keine zusätzlichen Qt-/PyQt-Pakete benötigt.

### Gespräche über Lumen Server / Server conversations

Nach der Gerätekopplung kann im Gespräch **Dieses Gerät** auf
**Lumen Server · Textgespräch** umgestellt werden. In Lumen Search liegt die Auswahl
unter **···**. Das Gespräch bleibt in der nativen Oberfläche; die Ausführung nutzt
das auf dem Server eingerichtete Modell. Standard bleibt dieses Gerät. Lokale
Anhänge müssen für diesen ersten Textanschluss entfernt werden; persönliche
Dateien, lokales Gedächtnis und Tresor werden nicht automatisch hochgeladen.

Bei einer unterbrochenen Verbindung **Serververbindung prüfen** verwenden. Unklare
Übermittlungen erscheinen nach erneutem Öffnen des Serververlaufs als
**Übermittlung prüfen**. Es wird kein Auftrag automatisch erneut gesendet.
Schließen lässt Serveraufträge weiterlaufen; **Abbrechen** beendet den tatsächlichen
Auftrag. Der native Verlauf zeigt die letzten fünf Gespräche; ältere Gespräche
und serverseitige Freigaben sind vorerst in der Server-Weboberfläche erreichbar.

After pairing, select **Lumen Server · Text conversation** in the native conversation
or Search's **···** menu. This uses the server's configured model and permissions;
local execution remains the default. This first connection sends text only.
Use **Check server connection** after a connection error; uncertain submissions
are resolved by receipt instead of resubmitting. Closing a window keeps the server
task running. **Cancel** cancels it. This does not synchronize notes or vaults.


### Lumen Notification

Die Glocke im rechten Panel bündelt KDE- und Lumen-Meldungen. **Alle anzeigen**
öffnet die vollständige Zentrale; auch in Apps und Einstellungen erreichbar.
**Mit Lumen besprechen** bereitet aus der gewählten Meldung einen Gesprächsentwurf
mit Quelle, Titel und Text vor. Erst Senden übermittelt ihn an den KI-Anbieter;
laufende Gespräche und vorhandene Entwürfe bleiben in ihrem Fenster erhalten.
Popups sitzen rechts bündig unter der Panel-Insel mit acht Pixeln Abstand;
schwebende Ränder und die Bildschirmposition werden berücksichtigt.
Lumen zeigt die Popups; KDE liefert Empfang, Originalaktionen, Ton und die
bestehenden Ruhe-Einstellungen. Steam-/GameMode-Spiele und Gamescope schalten
automatisch auf stilles Sammeln (Erkennung spätestens beim nächsten 5-Sekunden-Poll).
Die KDE-Vollbildregel bleibt wirksam; nach Spielende gibt es keine Popup-Flut.
Unter Einstellungen → Lumen Notification lassen sich Lumen-Popups und Spielruhe
abschalten. Systemmeldungen bleiben ausschließlich lokal. Eigene Servermeldungen teilen Lesen/Archivieren/Später über den bestehenden
Connector mit deinen Geräten. Die lokale Ansicht zeigt maximal 500 Karten;
archivierte lokale Karten werden nach 30 Tagen entfernt. KDE-Verlauf folgt der
Plasma-Sitzung. Lokale Erinnerungen benötigen das laufende Panel; verpasste
Termine erscheinen beim nächsten Start.

Notification-MCP: `lumen_notification_settings` liest die Popup-/Spielruhe-Optionen;
`lumen_notification_configure` ändert `native_popups` und/oder `quiet_games` mit
der vorhandenen Aktionsfreigabe. Nicht angegebene Optionen und manueller Ruhemodus
bleiben unverändert. `native_popups=false` schaltet Popups aus. Die Meldungen
bleiben im Mitteilungszentrum. Die bestehenden Werkzeuge lesen eigene Lumen-Meldungen, ändern
Lesen/Archivieren/Später/Jetzt und legen Erinnerungen an.

**Lumen Projekte** fasst Materialien, Gespräche und Aufgaben zusammen. Quellen
werden ausdrücklich verknüpft; Dateien bleiben an ihrem Ort und vorhandene
Zugriffsrechte gelten weiter. **Lumen Projekte → Serveraufträge** zeigt Ergebnisse,
bestehende Zeitpläne und Mitglieder freigegebener Serverprojekte.
Projektzugriff benötigt die Gerätefreigaben `projects` und `tasks`; Materialtitel
zusätzlich `notes` bzw. `drive`. Bearbeitete Zeitpläne werden pausiert und müssen
wieder aktiviert werden. Es werden die bis zu 100 jüngsten Projektaufträge gezeigt.

**Lumen System → Server & Geräte** bietet freigegebene Diagnosen, Dienstneustarts
und eingerichtetes Wake-on-LAN mit Status/Ergebnis. Dafür auf dem Server die neue
Freigabe **Andere Servergeräte von diesem Desktop verwalten** (`device_control`)
aktivieren; Wake benötigt zusätzlich `wake`. Bestehende Geräte erhalten diese
Rechte nicht automatisch. Server-Mitgliedschaft und Zielgerätefreigaben gelten
weiter. Verbindungen/Freigaben werden über den Link zur vorhandenen Serveransicht
verwaltet. Alle Aktionen verwenden die bestehende Queue und den Scheduler.

Desktop app ownership and retired native implementations: [Desktop architecture](docs/desktop-retirement.md).

The standalone desktop topbar offers **Settings → Appearance → Topbar → Layout**:
the existing island bar (default), Key band, Double deck and Context dock. Layouts
change live on all screens, independently of the four themes. App menus remain
real application menus; the context drawer sends only explicitly selected files.
The open Notes entry can be attached explicitly at its saved revision. Notes keep
their server reference and AI permissions; unsaved changes must be saved first.

Native topbar qualification uses `python3 tests/check-desktop.py`. It builds the
shipping QML/C++ components and drives real application menus and tray actions in
a private D-Bus/KWin session with synthetic data and no network. The existing
`tests/check-install-closure.py` verifies fresh installation, update preservation
and Arch payloads separately. Theme/size checks can use `--surface-only --theme
atelier --layout deck`, `--width 840`, or `--width 1920 --scale 1.5`; results and screenshots stay
under `artifacts/desktop-smoke`. Tests additionally need Bubblewrap, Qt Test,
Wayland development tools and the installed KDE desktop tools. The test input
helper is excluded from product builds (`BUILD_TESTING=OFF`).
