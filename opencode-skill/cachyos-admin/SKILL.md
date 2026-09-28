---
name: cachyos-admin
description: >
  Use when administering, troubleshooting or querying THIS specific
  CachyOS/KDE Plasma machine (host "internal-desktop", user "ativaro"). Triggers on:
  systemd units, journal logs, pacman, GPU/NVIDIA, disk/space, Plasma panels,
  KWin, kickerdash/start menu, shortcuts, theme/Kvantum, Steam, or questions
  about how the machine is configured. The full reference lives in
  /home/example/Documents/work/system.md and sync.md.
---

# CachyOS-Systemadministration (internal-desktop)

Dieser Rechner läuft **CachyOS** (Arch-basiert), **KDE Plasma 6.7.5 / KWin Wayland**,
**AMD Ryzen 9 9950X3D** + **RTX 4090** (`nvidia-open`), 60 GiB RAM.

## Zuerst die Referenz lesen
Bevor du Änderungen vornimmst oder Annahmen triffst:
- `/home/example/Documents/work/system.md` — vollständige Systemreferenz
- `/home/example/Documents/work/sync.md` — Änderungshistorie

Diese Dateien sind auch automatisch als opencode-`instructions` geladen.

## Strukturierter Zugriff
Bevorzugt das MCP-Tool **`cachyos`** statt freier Bash-Kommandos:
- `systemctl` — Unit-Status (system/user)
- `journal` — Logs (Unit/Priority/Lines)
- `pacman` — Paket-Suche/-Info (read-only)
- `disk`, `gpu`, `memory`, `sensors`, `kwin`
- `cmd` — eingeschränkter Shell-Befehl (Präfix-Allowlist)

## Wichtige Konventionen
- **Paketmanager**: nur `pacman` (kein AUR-Helper). Vor Systemänderungen Backup.
- **Root**: `sudo -A` (GUI-Askpass, kein TTY-Prompt).
- **Panels/Plasma**: Wayland-sicher per `qdbus6 org.kde.plasmashell /PlasmaShell`.
- **KWin**: `kreadconfig6`/`kwriteconfig6`, `qdbus6 org.kde.KWin`.
- **Blackscreen-Fix**: `KWIN_DRM_NO_DIRECT_SCANOUT=1` in `~/.config/environment.d/`.
- **Rollback**: `snapper rollback` oder Snapshots im Limine-Bootmenü.

## Arbeitsweise
1. Referenz (system.md/sync.md) konsultieren.
2. Ist-Zustand mit dem `cachyos`-MCP oder gezielten read-only Befehlen prüfen.
3. Kleinste reversible Änderung vorschlagen/ausführen, Backup anlegen.
4. Ergebnis verifizieren.
5. Änderungen nach `/sync`-Konvention in `sync.md` dokumentieren.
