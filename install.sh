#!/usr/bin/env bash
# install.sh — install the opencode Agent OS-integration suite for the current user.
#
# Everything lands under $XDG_DATA_HOME/opencode-agent (default ~/.local/share/opencode-agent)
# except the config files that must live in XDG dirs (~/.local/share/applications, etc).
#
# Usage:
#   ./install.sh                # install for current user
#   PREFIX=... ./install.sh     # override install prefix (default: ~/.local/share/opencode-agent)
#   ./install.sh --no-timer     # skip the systemd user timer
#   ./install.sh --no-mcp       # skip opencode MCP/commands/skill wiring
#
# Uninstall:
#   ./uninstall.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local/share/opencode-agent}"
BIN="$PREFIX/bin"

SKIP_TIMER=0
SKIP_MCP=0
for arg in "$@"; do
    case "$arg" in
        --no-timer) SKIP_TIMER=1 ;;
        --no-mcp)   SKIP_MCP=1 ;;
        *) echo "Unbekannte Option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*"; }

# ---- dependency check ------------------------------------------------------
say "Prüfe Abhängigkeiten"
missing=()
for c in bash python3; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
[ ${#missing[@]} -gt 0 ] && { echo "Fehlende Pflicht-Abhängigkeiten: ${missing[*]}" >&2; exit 1; }

optional_missing=()
for c in jq qml6 notify-send kdialog wl-paste alacritty konsole dolphin pacman; do
    command -v "$c" >/dev/null 2>&1 || optional_missing+=("$c")
done
[ ${#optional_missing[@]} -gt 0 ] && warn "Optionale Tools fehlen (einzelne Features inaktiv): ${optional_missing[*]}"

# ---- copy files ------------------------------------------------------------
say "Installiere Dateien nach $PREFIX"
mkdir -p "$BIN"
install -m 0755 "$REPO/bin/"* "$BIN/"
mkdir -p "$PREFIX/agent-app/ui"
install -m 0644 "$REPO/agent-app/ui/"* "$PREFIX/agent-app/ui/"
chmod 0755 "$BIN/opencode-agent-app" "$BIN/opencode-agent-bridge" \
           "$BIN/opencode-context" "$BIN/opencode-quick" "$BIN/opencode-watch" \
           "$BIN/opencode_krunner.py" "$BIN/cachyos_mcp.py"

# ---- XDG data files --------------------------------------------------------
say "Installiere Desktop-Integration"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

subst() { sed "s|%INSTALL_BIN%|$BIN|g" "$1"; }

mkdir -p "$DATA_HOME/applications" "$DATA_HOME/kio/servicemenus" \
         "$DATA_HOME/krunner/dbusplugins" "$DATA_HOME/dbus-1/services" \
         "$CONFIG_HOME/autostart"

subst "$REPO/data/kio-servicemenus/opencode.desktop" > "$DATA_HOME/kio/servicemenus/opencode.desktop"
subst "$REPO/data/applications/opencode-agent.desktop" > "$DATA_HOME/applications/opencode-agent.desktop"
subst "$REPO/data/applications/opencode-ask.desktop"    > "$DATA_HOME/applications/opencode-ask.desktop"
subst "$REPO/data/applications/opencode-ask-sel.desktop" > "$DATA_HOME/applications/opencode-ask-sel.desktop"
subst "$REPO/data/krunner-dbusplugins/opencode-runner.desktop" > "$DATA_HOME/krunner/dbusplugins/opencode-runner.desktop"
subst "$REPO/data/dbus-1-services/org.kde.opencode-runner.service" > "$DATA_HOME/dbus-1/services/org.kde.opencode-runner.service"
subst "$REPO/data/autostart/opencode-krunner-runner.desktop" > "$CONFIG_HOME/autostart/opencode-krunner-runner.desktop"

# refresh caches
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

# ---- opencode MCP / commands / skill --------------------------------------
if [ "$SKIP_MCP" = 0 ] && { command -v opencode >/dev/null 2>&1 || [ -x "$HOME/.opencode/bin/opencode" ]; }; then
    say "Verdrahte opencode (MCP / Commands / Skill)"
    OPCFG="$CONFIG_HOME/opencode"
    mkdir -p "$OPCFG/command" "$OPCFG/skill/cachyos-admin"
    cp "$REPO/opencode-command/"*.md "$OPCFG/command/" 2>/dev/null || true
    cp -r "$REPO/opencode-skill/cachyos-admin/." "$OPCFG/skill/cachyos-admin/" 2>/dev/null || true

    # MCP: write/merge a small JSON config next to the user's opencode.jsonc
    python3 - "$OPCFG/opencode.jsonc" "$BIN/cachyos_mcp.py" <<'PY'
import json, os, re, sys
cfg_path, mcp_py = sys.argv[1], sys.argv[2]
raw = ""
if os.path.exists(cfg_path):
    raw = open(cfg_path).read()
stripped = re.sub(r'^\s*//.*$', '', raw, flags=re.M)
try:
    data = json.loads(stripped) if stripped.strip() else {}
except Exception:
    print("  (bestehende opencode.jsonc nicht parsebar – bitte manuell MCP ergänzen)")
    raise SystemExit(0)
data.setdefault("$schema", "https://opencode.ai/config.json")
mcp = data.setdefault("mcp", {})
mcp["cachyos"] = {"type": "local", "command": ["python3", mcp_py], "enabled": True}
open(cfg_path, "w").write(json.dumps(data, indent=2) + "\n")
print("  MCP 'cachyos' in", cfg_path, "eingetragen")
PY
else
    warn "opencode nicht gefunden – MCP/Commands/Skill übersprungen (--no-mcp)"
fi

# ---- systemd user timer ----------------------------------------------------
if [ "$SKIP_TIMER" = 0 ] && command -v systemctl >/dev/null 2>&1; then
    say "Richte systemd-User-Timer ein"
    UNITDIR="$CONFIG_HOME/systemd/user"
    mkdir -p "$UNITDIR"
    subst "$REPO/systemd/opencode-watch.service" > "$UNITDIR/opencode-watch.service"
    cp "$REPO/systemd/opencode-watch.timer" "$UNITDIR/opencode-watch.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    systemctl --user enable --now opencode-watch.timer >/dev/null 2>&1 || warn "Timer konnte nicht aktiviert werden"
fi

say "Fertig."
cat <<EOF

Nächste Schritte:
  1. opencode neu starten, damit MCP/Commands/Skill greifen.
  2. KRunner neu laden (falls der 'ai <Frage>'-Trigger fehlt):
       kquitapp6 krunner
  3. App starten:  $BIN/opencode-agent-app
     oder über das Startmenü: "opencode Agent"

Konfiguration (optional, per Umgebungsvariablen):
  OPENCODE_BIN        Pfad zur opencode-Binary
  OPENCODE_TERM       Terminal (alacritty/konsole/xterm)
  OPENCODE_WORKDIR    Standard-Arbeitsordner
  OPENCODE_WATCH_ANALYZE=0   Auto-Analyse im Wächter aus

Deinstallieren:  $REPO/uninstall.sh

Optional (braucht root, für den sudo-Credential-Cache):
  sudo $REPO/install-system.sh
EOF
