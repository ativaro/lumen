---
name: lumen-admin
description: >
  Use when administering, troubleshooting or querying a Linux desktop through
  Lumen (KDE Plasma, systemd, NVIDIA, wayland). Triggers on: systemd units,
  journal logs, package manager queries, GPU/temperature, disk space, Plasma
  panels, KWin, shortcuts, theme/styling, or "how is this machine set up".
  Prefers the Lumen MCP server over ad-hoc shell commands.
---

# Lumen system administration

Lumen exposes the local machine to the agent through the MCP server `cachyos`.

## Structured access first

Prefer the MCP tools over free-form shell:

- `systemctl` — unit status (system/user)
- `journal` — logs (unit / priority / lines)
- `pacman` — package search/info (read-only)
- `disk`, `gpu`, `memory`, `sensors`, `kwin`
- `cmd` — explicitly validated read-only argv; shell syntax is rejected
- `lumen_knowledge` — selected knowledge folders with file/page citations
- `lumen_propose_task` — native task draft for the user to review in Lumen; never an execution approval

Writing actions (`notify`, `restart_unit`, `media`, `wallpaper`, `screenshot`)
are available only when the server runs with `LUMEN_MCP_ACTIONS=1`.

## Conventions

- **Backups before system changes.** Prefer the smallest reversible change.
- **Distro-agnostic where possible** — detect the package manager instead of
  assuming one; on Arch-based systems use `pacman` (no AUR helper assumed).
- **Root**: use the system's configured sudo askpass; never assume a TTY.
- **Wayland/Plasma**: use `qdbus6` for Plasma scripting, `kreadconfig6`/
  `kwriteconfig6` for KDE config. Never restart `dbus` to apply a policy.
- **Rollback**: prefer filesystem snapshots (e.g. snapper/btrfs) if available.

## Working method

1. Gather facts with the MCP tools or targeted read-only commands.
2. State the most likely cause and what would contradict it.
3. Apply/propose the smallest reversible fix; create a backup first.
4. Verify the result.
5. Offer to record the change in the project's changelog.
