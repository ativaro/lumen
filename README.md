# opencode Agent — OS integration for Linux desktops

Turn [opencode](https://opencode.ai) into an **agentic-OS layer**: a native desktop
app, Dolphin context menus, global hotkeys, a KRunner runner, a system watchdog and
an MCP server that exposes your machine to the agent.

Built for **KDE Plasma 6 on Wayland** (CachyOS/Arch), but written to degrade
gracefully on other setups.

## Features

| Component | What it does |
|---|---|
| **Desktop app** (`opencode Agent`) | Kirigami/QML GUI: streaming chat, system dashboard (CPU/RAM/GPU/disk), quick actions — **no PyQt needed** |
| **Dolphin service menu** | Right-click a file/folder → *open / explain / fix / review / ask* |
| **Global shortcuts** | `Meta+Shift+O` ask · `Meta+Shift+S` explain clipboard |
| **KRunner runner** | Type `ai <question>` or `oc <question>` in KRunner |
| **System watchdog** | systemd user timer checks failed units, kernel errors, disk, GPU temp; runs an automatic opencode analysis on findings |
| **MCP server `cachyos`** | Structured tools: `systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `sensors`, `kwin`, guarded `cmd` |
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
git clone <this-repo> opencode-agent
cd opencode-agent
./install.sh
```

Options:

```bash
PREFIX=~/.local/share/opencode-agent ./install.sh   # custom install prefix
./install.sh --no-timer                             # skip systemd timer
./install.sh --no-mcp                               # skip opencode MCP/commands/skill
```

Then:
1. **Restart opencode** so MCP/commands/skill are picked up.
2. Reload KRunner if the `ai …` trigger is missing: `kquitapp6 krunner`
3. Launch the app from the menu (**opencode Agent**) or run
   `~/.local/share/opencode-agent/bin/opencode-agent-app`.

## Configuration

All scripts read these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENCODE_BIN` | `opencode` in `$PATH`, else `~/.opencode/bin/opencode` | opencode binary |
| `OPENCODE_TERM` | `alacritty`, `konsole` or `xterm` | terminal emulator |
| `OPENCODE_WORKDIR` | `~/Documents/work` | default working directory |
| `OPENCODE_AGENT_STATE` | `~/.cache/opencode-agent` | state/report/cache dir |
| `OPENCODE_WATCH_ANALYZE` | `1` | `0` disables the automatic watchdog analysis |
| `OPENCODE_WATCH_MODEL` | *(provider default)* | model for the watchdog analysis |

## Uninstall

```bash
./uninstall.sh
```

## Layout

```
bin/                      helper scripts + GUI backend (installed to PREFIX/bin)
agent-app/ui/             Kirigami/QML desktop app
data/                     .desktop / krunner / dbus / autostart templates
systemd/                  watchdog user units
opencode-command/         /sync, /sysreport, /fix
opencode-skill/           cachyos-admin skill
install.sh / uninstall.sh
```

## Notes

- The desktop app keeps its **own** opencode session (separate from your terminal
  sessions) so chats don't collide.
- Nothing here modifies system files; everything is per-user. The only privileged
  action you might take is installing optional packages.
- Tested on KDE Plasma 6.7 on Wayland with `nvidia-open`.

## License

MIT — see [LICENSE](LICENSE).
