#!/usr/bin/env bash
# uninstall.sh — remove the Lumen OS-integration for the current user.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/lumen}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

say "Entferne systemd-User-Timer"
systemctl --user disable --now lumen-watch.timer lumen-jobs.timer >/dev/null 2>&1 || true
rm -f "$CONFIG_HOME/systemd/user/lumen-watch.service" \
      "$CONFIG_HOME/systemd/user/lumen-watch.timer" \
      "$CONFIG_HOME/systemd/user/lumen-jobs.service" \
      "$CONFIG_HOME/systemd/user/lumen-jobs.timer"
systemctl --user daemon-reload >/dev/null 2>&1 || true

systemctl --user disable --now lumen-sound.service >/dev/null 2>&1 || true
rm -f "$CONFIG_HOME/systemd/user/lumen-sound.service"

say "Entferne Desktop-Integration"
systemctl --user disable --now lumen-vault.timer >/dev/null 2>&1 || true
systemctl --user stop lumen-vault.service >/dev/null 2>&1 || true
rm -f "$CONFIG_HOME/systemd/user/lumen-vault.service" "$CONFIG_HOME/systemd/user/lumen-vault.timer"
systemctl --user daemon-reload >/dev/null 2>&1 || true
rm -f "$DATA_HOME/kio/servicemenus/lumen.desktop"
rm -f "$DATA_HOME/applications/lumen.desktop" "$DATA_HOME/applications/lumen-files.desktop"
rm -f "$DATA_HOME/applications/lumen-open.desktop" "$DATA_HOME/applications/lumen-apps.desktop"
rm -f "$DATA_HOME/applications/lumen-search.desktop" "$DATA_HOME/applications/lumen-search-preview.desktop"
for tool in meetings household workbench radio vault inbox reader sound wissen; do
    rm -f "$DATA_HOME/applications/lumen-$tool.desktop" "$DATA_HOME/icons/hicolor/scalable/apps/lumen-$tool.svg"
done
rm -f "$DATA_HOME/applications/lumen-ask.desktop"
rm -f "$DATA_HOME/applications/lumen-ask-sel.desktop"
rm -f "$DATA_HOME/applications/lumen-vision.desktop"
rm -f "$DATA_HOME/applications/lumen-sel.desktop"
rm -f "$DATA_HOME/krunner/dbusplugins/lumen-runner.desktop"
rm -f "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/lumen.svg"
rm -f "$CONFIG_HOME/autostart/lumen-krunner-runner.desktop" "$CONFIG_HOME/autostart/lumen-versions.desktop"

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
  - Cache/Reports: rm -rf ~/.cache/lumen
  - Systempaket (falls installiert): sudo pacman -R lumen
EOF
