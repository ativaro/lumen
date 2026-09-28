#!/usr/bin/env bash
# uninstall.sh — remove the Lumen OS-integration for the current user.

set -uo pipefail

PREFIX="${PREFIX:-$HOME/.local/share/opencode-lumen}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

say "Entferne systemd-User-Timer"
systemctl --user disable --now opencode-watch.timer >/dev/null 2>&1 || true
rm -f "$CONFIG_HOME/systemd/user/opencode-watch.service" \
      "$CONFIG_HOME/systemd/user/opencode-watch.timer"
systemctl --user daemon-reload >/dev/null 2>&1 || true

say "Entferne Desktop-Integration"
rm -f "$DATA_HOME/kio/servicemenus/opencode.desktop"
rm -f "$DATA_HOME/applications/opencode-lumen.desktop"
rm -f "$DATA_HOME/applications/opencode-ask.desktop"
rm -f "$DATA_HOME/applications/opencode-ask-sel.desktop"
rm -f "$DATA_HOME/krunner/dbusplugins/opencode-runner.desktop"
rm -f "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
rm -f "$CONFIG_HOME/autostart/opencode-krunner-runner.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

say "Laufenden KRunner-Runner beenden"
pkill -f lumen_krunner.py >/dev/null 2>&1 || true

# stop any running app
pkill -f 'agent-app/ui/main.qml' >/dev/null 2>&1 || true

say "Entferne Programmdateien ($PREFIX)"
rm -rf "$PREFIX"

cat <<EOF

Entfernt. Hinweise:
  - opencode-Commands/Skill unter $CONFIG_HOME/opencode bleiben erhalten (manuell löschen, falls gewünscht):
      rm -f $CONFIG_HOME/opencode/command/{sync,sysreport,fix}.md
      rm -rf $CONFIG_HOME/opencode/skill/cachyos-admin
  - MCP-Eintrag 'cachyos' in $CONFIG_HOME/opencode/opencode.jsonc bei Bedarf manuell entfernen.
  - Cache/Reports: rm -rf ~/.cache/opencode-lumen
EOF
