# Lumen — OS integration for Linux desktops

Turn [opencode](https://opencode.ai) into an **agentic-OS layer**: a native desktop
app, Dolphin context menus, global hotkeys, a KRunner runner, a system watchdog and
an MCP server that exposes your machine to the agent.

Built for **KDE Plasma 6 on Wayland** (CachyOS/Arch), but written to degrade
gracefully on other setups.

## Features

| Component | What it does |
|---|---|
| **Desktop app** (`Lumen`) | Kirigami/QML GUI: streaming chat, system dashboard (CPU/RAM/GPU/disk), quick actions — **no PyQt needed** |
| **Dolphin service menu** | Right-click a file/folder → *open / explain / fix / review / ask* |
| **Global shortcuts** | `Meta+Shift+O` ask · `Meta+Shift+S` explain clipboard · `Meta+Shift+V` vision · `Meta+Shift+E` explain selection |
| **Vision** | capture a screen region → opencode analyses the image (`lumen-vision`) |
| **Selection actions** | explain / translate / fix / summarize selected or copied text (`lumen-sel`) |
| **Shell integration** | `why` (explain last failed command), `vix`, `sel` — bash & fish (`shell/opencode.{bash,fish}`) |
| **Git** | `lumen-gitmsg` drafts a Conventional-Commit message from the diff |
| **KRunner runner** | Type `ai <question>` or `oc <question>` in KRunner |
| **Plasma applet** | panel widget with agent status + quick actions (`org.lumen.agent`) |
| **System watchdog** | systemd timer checks failed units, kernel errors, disk, GPU temp; automatic opencode analysis |
| **Daily digest / nightly report** | scheduled summaries (`lumen-digest`, `lumen-nightly`) |
| **MCP server `cachyos`** | read tools `systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `sensors`, `kwin`, guarded `cmd` — plus **opt-in action tools** (`notify`, `restart_unit`, `media`, `wallpaper`, `screenshot`) behind `LUMEN_MCP_ACTIONS=1` |
| **opencode commands/skill** | `/sync`, `/sysreport`, `/fix` + `cachyos-admin` skill |

## Requirements

**Required:** `bash`, `python3`, a working [opencode](https://opencode.ai) install.

**Optional** (individual features need these):
- `qml6` + `kirigami` / `kirigami-addons` — desktop app
- `jq` — faster streaming in the app bridge
- `alacritty` or `konsole` — terminal used for prompts
- `kdialog` or `zenity` — input dialogs
- `wl-clipboard` — clipboard quick action
- `notify-send` (libnotify) — watchdog notifications
- `nvidia-smi` — GPU metrics
- KDE Plasma 6 + Dolphin + KRunner — for the KDE integrations

## Install

```bash
git clone <this-repo> opencode-lumen
cd opencode-lumen
./install.sh
```

Options:

```bash
PREFIX=~/.local/share/opencode-lumen ./install.sh   # custom install prefix
./install.sh --no-timer                             # skip systemd timer
./install.sh --no-mcp                               # skip opencode MCP/commands/skill
```

Then:
1. **Restart opencode** so MCP/commands/skill are picked up.
2. Reload KRunner if the `ai …` trigger is missing: `kquitapp6 krunner`
3. Launch the app from the menu (**Lumen**) or run
   `~/.local/share/opencode-lumen/bin/lumen-agent-app`.

## Configuration

All scripts read these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LUMEN_OPENCODE_BIN` | `opencode` in `$PATH`, else `~/.opencode/bin/opencode` | opencode binary |
| `LUMEN_TERM` | `alacritty`, `konsole` or `xterm` | terminal emulator |
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
./uninstall.sh
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
agent-app/ui/             Kirigami/QML desktop app
plasmoid/                 Plasma panel applet (org.lumen.agent)
shell/                    bash + fish integration (why/vix/sel)
data/                     .desktop / krunner / dbus / autostart templates
systemd/                  watchdog user units
system/                   system daemon, watchdog, notify, dbus policy
etc/sudoers.d/            optional system-wide sudo cache drop-in
opencode-command/         /sync, /sysreport, /fix
opencode-skill/           cachyos-admin skill
packaging/arch/           PKGBUILD, build-package.sh
distro/aur/               AUR tree tooling
distro/cachyos/           local pacman repo tooling
.github/workflows/        CI: lint + package build + release
install.sh / uninstall.sh
install-system.sh         optional root-only tweaks
```

## Notes

- The desktop app keeps its **own** opencode session (separate from your terminal
  sessions) so chats don't collide.
- Nothing here modifies system files; everything is per-user. The only privileged
  action you might take is installing optional packages.
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
