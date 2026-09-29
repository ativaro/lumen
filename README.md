# Lumen — OS integration for Linux desktops

Lumen is a native desktop assistant with a shared conversation panel in Lumen Files.
[OpenCode](https://opencode.ai) runs as its background engine. Desktop actions,
file context menus, hotkeys, image analysis and KRunner all open Lumen directly.
System monitoring and MCP tools provide local machine context.

Built for **KDE Plasma 6 on Wayland** (CachyOS/Arch), but written to degrade
gracefully on other setups.

## Features

| Component | What it does |
|---|---|
| **Desktop app** (`Lumen`) | Native PyQt5 chat, conversation history, cancellation, permission/question forms, system dashboard and quick actions |
| **File actions** | Explain / fix / review show a native result and progress view in Files or a compact standalone window; free chat remains separate |
| **Global shortcuts** | `Meta+Shift+O` ask · `Meta+Shift+S` explain clipboard · `Meta+Shift+V` vision · `Meta+Shift+E` explain selection |
| **Vision** | capture a screen region → opencode analyses the image (`lumen-vision`) |
| **Selection actions** | explain / translate / fix / summarize selected or copied text (`lumen-sel`) |
| **Shell integration** | `why` (explain last failed command), `vix`, `sel` — bash & fish (`shell/lumen.{bash,fish}`) |
| **Git** | `lumen-gitmsg` drafts a Conventional-Commit message from the diff |
| **KRunner runner** | Type `lumen <question>`, `ai <question>` or `oc <question>` in KRunner |
| **Plasma applet** | panel widget with agent status + quick actions (`org.lumen.agent`) |
| **Lumen Files** | file manager with fast filename search, local text/PDF content search with optional Lumen synonyms, previews, tabs, gallery, disk analysis, KIO network folders, native rename/sort proposals with editable preview and undo, integrated Lumen panel |
| **System watchdog** | systemd timer checks failed units, kernel errors, disk, GPU temp; automatic opencode analysis |
| **Daily digest / nightly report** | scheduled summaries (`lumen-digest`, `lumen-nightly`) |
| **MCP server `cachyos`** | read tools `systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `sensors`, `kwin`, guarded `cmd` — plus **opt-in action tools** (`notify`, `restart_unit`, `media`, `wallpaper`, `screenshot`) behind `LUMEN_MCP_ACTIONS=1` |
| **opencode commands/skill** | `/sync`, `/sysreport`, `/fix` + `lumen-admin` skill |

## Requirements

**Required:** `bash`, Python 3, PyQt5, PyGObject/GIO, Pillow and a working [OpenCode](https://opencode.ai) installation with the server API.

**Optional** (individual features need these):
- `notify-send` (libnotify) — watchdog notifications
- `nvidia-smi` — GPU metrics
- KDE Plasma 6 + Dolphin + KRunner — for the KDE integrations

## Install

### Arch / CachyOS — package (recommended)

```bash
# from a local build
git clone <repo-url> opencode-lumen && cd opencode-lumen
./packaging/arch/build-package.sh
sudo pacman -U packaging/arch/opencode-lumen-*.pkg.tar.zst

# later, once published to the AUR:
yay -S opencode-lumen      # or: paru -S opencode-lumen
```

The package pulls in `opencode` (official repos), enables its services by
default (opt-out) and drops the desktop integration in `/usr/share`.

### Any distro — per-user install

```bash
git clone <repo-url> opencode-lumen && cd opencode-lumen
./install.sh
```

Options:

```bash
PREFIX=~/.local/share/opencode-lumen ./install.sh   # custom install prefix
./install.sh --no-timer                             # skip systemd timer
./install.sh --no-mcp                               # skip opencode MCP/commands/skill
```

After installing (either way):

1. Register the opencode integration (system package does this automatically
   for logged-in users; skip if you used `install.sh`):
   ```bash
   lumen-setup              # MCP 'cachyos' + /sync,/sysreport,/fix + lumen-admin skill
   ```
2. **Restart opencode** so MCP/commands/skill are picked up.
3. Reload KRunner if the `ai …` trigger is missing: `kquitapp6 krunner`
4. Launch the app from the menu (**Lumen**) or run `lumen-agent-app`.

## Configuration

All scripts read these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LUMEN_OPENCODE_BIN` | `opencode` in `$PATH`, else `~/.opencode/bin/opencode` | opencode binary |
| `LUMEN_WORKDIR` | `~/Documents/work` | default working directory |
| `LUMEN_STATE` | `~/.cache/opencode-lumen` | state/report/cache dir |
| `LUMEN_WATCH_ANALYZE` | `1` | `0` disables the automatic watchdog analysis |
| `LUMEN_WATCH_MODEL` | *(provider default)* | model for the watchdog analysis |
| `LUMEN_MCP_ACTIONS` | `0` | `1` enables the writing MCP action tools |
| `LUMEN_SEL_LANG` | `Deutsch` | translate target for `lumen-sel translate` |
| `LUMEN_VISION_PROMPT` | *(built-in)* | override the vision prompt |
| `LUMEN_GITMSG_STYLE` | Conventional Commits | commit message style |

### Shell integration

Add to `~/.config/fish/config.fish` (fish) or `~/.bashrc` (bash):

```fish
source /usr/share/opencode-lumen/shell/lumen.fish
```

Then `why` explains the last failed command, `vix` runs vision on a region and
`sel fix` corrects the selected text.

## Uninstall

```bash
lumen-setup --uninstall     # opencode MCP/commands/skill (system package: do first)
./uninstall.sh              # per-user install
sudo pacman -R opencode-lumen   # system package
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
agent-app/main.py         Native standalone Lumen window
plasmoid/                 Plasma panel applet (org.lumen.agent)
files/                    Lumen Files file manager (PyQt5)
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
.github/workflows/        CI: lint + package build + release
install.sh / uninstall.sh
install-system.sh         optional root-only tweaks
```

## Notes

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
- The shared panel uses the existing PyQt5 runtime. QML, terminal launchers and
  the temporary text-file bridge are no longer used for conversations.
- `lumen-sel translate|fix|summarize` copies successful answers back to the clipboard.
  Every answer can also be copied from the panel.
- Per-user installation writes under the user home. The pacman package installs
  under `/usr` and keeps the existing system services on upgrade.
- Tested on KDE Plasma 6.7 on Wayland with `nvidia-open`.

## License

MIT — see [LICENSE](LICENSE).

## System-wide install (Arch / CachyOS)

For a system package instead of the per-user install:

```bash
./packaging/arch/build-package.sh            # build opencode-lumen-*.pkg.tar.zst
sudo pacman -U packaging/arch/opencode-lumen-*.pkg.tar.zst
```

or via a local pacman repo:

```bash
./distro/cachyos/make-repo.sh
# then add the printed [opencode-lumen] block to /etc/pacman.conf
sudo pacman -Sy && sudo pacman -S opencode-lumen
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
`/var/lib/opencode-lumen/findings.md`; a **per-user path unit** picks that up,
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
