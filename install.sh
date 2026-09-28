#!/usr/bin/env bash
# install.sh — install the Lumen OS-integration suite for the current user.
#
# Everything lands under $XDG_DATA_HOME/opencode-lumen (default ~/.local/share/opencode-lumen)
# except the config files that must live in XDG dirs (~/.local/share/applications, etc).
#
# Usage:
#   ./install.sh                # install for current user
#   PREFIX=... ./install.sh     # override install prefix (default: ~/.local/share/opencode-lumen)
#   ./install.sh --no-timer     # skip the systemd user timer
#   ./install.sh --no-mcp       # skip opencode MCP/commands/skill wiring
#
# Uninstall:
#   ./uninstall.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local/share/opencode-lumen}"
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
for c in jq qml6 notify-send kdialog wl-paste alacritty konsole dolphin spectacle; do
    command -v "$c" >/dev/null 2>&1 || optional_missing+=("$c")
done
[ ${#optional_missing[@]} -gt 0 ] && warn "Optionale Tools fehlen (einzelne Features inaktiv): ${optional_missing[*]}"
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/.opencode/bin/opencode" ]; then
    warn "opencode nicht gefunden – Lumen ist ohne den Agenten nutzlos. Siehe https://opencode.ai"
fi

# ---- copy files ------------------------------------------------------------
say "Installiere Dateien nach $PREFIX"
mkdir -p "$BIN"
install -m 0755 "$REPO/bin/"* "$BIN/"
mkdir -p "$PREFIX/agent-app/ui"
install -m 0644 "$REPO/agent-app/ui/"* "$PREFIX/agent-app/ui/"
chmod 0755 "$BIN"/lumen-* "$BIN"/lumen_krunner.py "$BIN"/lumen_mcp.py 2>/dev/null || true

# ---- XDG data files --------------------------------------------------------
say "Installiere Desktop-Integration"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

subst() { sed "s|%INSTALL_BIN%|$BIN|g" "$1"; }

mkdir -p "$DATA_HOME/applications" "$DATA_HOME/kio/servicemenus" \
         "$DATA_HOME/krunner/dbusplugins" "$DATA_HOME/dbus-1/services" \
         "$DATA_HOME/icons/hicolor/scalable/apps" \
         "$CONFIG_HOME/autostart"

# icon
install -m 0644 "$REPO/icons/hicolor/scalable/apps/lumen.svg" "$DATA_HOME/icons/hicolor/scalable/apps/lumen.svg"

subst "$REPO/data/kio-servicemenus/lumen.desktop" > "$DATA_HOME/kio/servicemenus/lumen.desktop"
subst "$REPO/data/applications/lumen.desktop" > "$DATA_HOME/applications/lumen.desktop"
subst "$REPO/data/applications/lumen-ask.desktop" > "$DATA_HOME/applications/lumen-ask.desktop"
subst "$REPO/data/applications/lumen-ask-sel.desktop" > "$DATA_HOME/applications/lumen-ask-sel.desktop"
subst "$REPO/data/applications/lumen-vision.desktop" > "$DATA_HOME/applications/lumen-vision.desktop"
subst "$REPO/data/applications/lumen-sel.desktop" > "$DATA_HOME/applications/lumen-sel.desktop"
subst "$REPO/data/krunner-dbusplugins/lumen-runner.desktop" > "$DATA_HOME/krunner/dbusplugins/lumen-runner.desktop"
subst "$REPO/data/dbus-1-services/org.lumen.runner.service" > "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
subst "$REPO/data/autostart/lumen-krunner-runner.desktop" > "$CONFIG_HOME/autostart/lumen-krunner-runner.desktop"

# refresh caches
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

# ---- opencode MCP / commands / skill --------------------------------------
if [ "$SKIP_MCP" = 0 ] && { command -v opencode >/dev/null 2>&1 || [ -x "$HOME/.opencode/bin/opencode" ]; }; then
    say "Verdrahte opencode (MCP / Commands / Skill)"
    LUMEN_MCP_PY="$BIN/lumen_mcp.py" LUMEN_SHARE="$REPO" \
        "$BIN/lumen-setup" || warn "lumen-setup fehlgeschlagen"
else
    warn "opencode nicht gefunden – MCP/Commands/Skill übersprungen"
fi

# ---- systemd user timer ----------------------------------------------------
if [ "$SKIP_TIMER" = 0 ] && command -v systemctl >/dev/null 2>&1; then
    say "Richte systemd-User-Timer ein"
    UNITDIR="$CONFIG_HOME/systemd/user"
    mkdir -p "$UNITDIR"
    subst "$REPO/systemd/lumen-watch.service" > "$UNITDIR/lumen-watch.service"
    cp "$REPO/systemd/lumen-watch.timer" "$UNITDIR/lumen-watch.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    systemctl --user enable --now lumen-watch.timer >/dev/null 2>&1 || warn "Timer konnte nicht aktiviert werden"
fi

say "Fertig."
cat <<EOF

Nächste Schritte:
  1. opencode neu starten, damit MCP/Commands/Skill greifen.
  2. KRunner neu laden (falls der 'ai <Frage>'-Trigger fehlt):
       kquitapp6 krunner
  3. App starten:  $BIN/lumen-agent-app
     oder über das Startmenü: "Lumen"

Konfiguration (optional, per Umgebungsvariablen):
  LUMEN_OPENCODE_BIN      Pfad zur opencode-Binary
  LUMEN_TERM              Terminal (alacritty/konsole/xterm)
  LUMEN_WORKDIR           Standard-Arbeitsordner
  LUMEN_WATCH_ANALYZE=0   Auto-Analyse im Wächter aus

Deinstallieren:  $BIN/lumen-setup --uninstall && $REPO/uninstall.sh

Optional (braucht root, für den sudo-Credential-Cache):
  sudo $REPO/install-system.sh
EOF
