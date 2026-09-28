#!/usr/bin/env bash
# uninstall.sh — remove the Lumen OS-integration for the current user.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local/share/opencode-lumen}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

say "Entferne systemd-User-Timer"
systemctl --user disable --now lumen-watch.timer >/dev/null 2>&1 || true
rm -f "$CONFIG_HOME/systemd/user/lumen-watch.service" \
      "$CONFIG_HOME/systemd/user/lumen-watch.timer"
systemctl --user daemon-reload >/dev/null 2>&1 || true

say "Entferne Desktop-Integration"
rm -f "$DATA_HOME/kio/servicemenus/lumen.desktop"
rm -f "$DATA_HOME/applications/lumen.desktop"
rm -f "$DATA_HOME/applications/lumen-ask.desktop"
rm -f "$DATA_HOME/applications/lumen-ask-sel.desktop"
rm -f "$DATA_HOME/applications/lumen-vision.desktop"
rm -f "$DATA_HOME/applications/lumen-sel.desktop"
rm -f "$DATA_HOME/krunner/dbusplugins/lumen-runner.desktop"
rm -f "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/lumen.svg"
rm -f "$CONFIG_HOME/autostart/lumen-krunner-runner.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

say "Laufenden KRunner-Runner beenden"
pkill -f lumen_krunner.py >/dev/null 2>&1 || true

# stop any running app
pkill -f "$PREFIX/agent-app/main.py" >/dev/null 2>&1 || true

# opencode integration (MCP/commands/skill)
if [ -x "$PREFIX/bin/lumen-setup" ]; then
    say "Entferne opencode-Integration"
    "$PREFIX/bin/lumen-setup" --uninstall >/dev/null 2>&1 || true
fi

say "Entferne Programmdateien ($PREFIX)"
rm -rf "$PREFIX"

cat <<EOF

Entfernt. Hinweise:
  - Cache/Reports: rm -rf ~/.cache/opencode-lumen
  - Systempaket (falls installiert): sudo pacman -R opencode-lumen
EOF
