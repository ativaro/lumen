#!/usr/bin/env bash
# install.sh — install the Lumen OS-integration suite for the current user.
#
# Everything lands under $XDG_DATA_HOME/lumen (default ~/.local/share/lumen)
# except the config files that must live in XDG dirs (~/.local/share/applications, etc).
#
# Usage:
#   ./install.sh                # install for current user
#   PREFIX=... ./install.sh     # override install prefix (default: ~/.local/share/lumen)
#   ./install.sh --no-timer     # skip the systemd user timer
#   ./install.sh --no-mcp       # skip opencode MCP/commands/skill wiring
#   ./install.sh --desktop      # activate themes/wallpaper and replace panels (with backup)
#
# Uninstall:
#   ./uninstall.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/lumen}"
BIN="$PREFIX/bin"

message() {
    case "${LUMEN_LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}" in
        de*) printf '%s\n' "$1";;
        *) printf '%s\n' "$2";;
    esac
}
say() { printf '\033[1;36m==>\033[0m %s\n' "$(message "$1" "$2")"; }
warn() { printf '\033[1;33m%s:\033[0m %s\n' "$(message Warnung Warning)" "$(message "$1" "$2")"; }

SKIP_TIMER=0
SKIP_MCP=0
DESKTOP=0
for arg in "$@"; do
    case "$arg" in
        --no-timer) SKIP_TIMER=1 ;;
        --no-mcp)   SKIP_MCP=1 ;;
        --desktop)  DESKTOP=1 ;;
        *) message "Unbekannte Option: $arg" "Unknown option: $arg" >&2; exit 2 ;;
    esac
done


say "Lizenz: Lumen-EULA unter $REPO/LICENSE; Fremdlizenzen bleiben gültig." "License: Lumen EULA at $REPO/LICENSE; third-party licenses remain in effect."

# ---- dependency check ------------------------------------------------------
say "Prüfe Abhängigkeiten" "Checking dependencies"
missing=()
for c in bash python3 git; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
[ ${#missing[@]} -gt 0 ] && { message "Fehlende Pflicht-Abhängigkeiten: ${missing[*]}" "Missing required dependencies: ${missing[*]}" >&2; exit 1; }

"$REPO/bin/lumen-python" -c "import PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtQuick, PySide6.QtQuickWidgets, gi, PIL" || { message "Benötigt: PySide6 mit QtQuick/QtSvg, PyGObject und Pillow" "Required: PySide6 with QtQuick/QtSvg, PyGObject and Pillow" >&2; exit 1; }
if [ "$DESKTOP" = 1 ]; then
    for c in qdbus6 kreadconfig6 kwriteconfig6 plasma-apply-desktoptheme kbuildsycoca6; do
        command -v "$c" >/dev/null || { message "Desktop-Einrichtung benötigt $c und eine KDE-Plasma-6-Sitzung." "Desktop setup requires $c and a KDE Plasma 6 session." >&2; exit 1; }
    done
fi

optional_missing=()
for c in notify-send dolphin spectacle; do
    command -v "$c" >/dev/null 2>&1 || optional_missing+=("$c")
done
[ ${#optional_missing[@]} -gt 0 ] && warn "Optionale Tools fehlen (einzelne Features inaktiv): ${optional_missing[*]}" "Optional tools missing (some features unavailable): ${optional_missing[*]}"
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/.opencode/bin/opencode" ]; then
    warn "OpenCode kann anschließend im Einrichtungsassistenten ergänzt werden; Dateien und native Aufträge sind bereits verfügbar." "OpenCode can be added in the setup wizard; files and native tasks are already available."
fi

# ---- copy files ------------------------------------------------------------
say "Installiere Dateien nach $PREFIX" "Installing files into $PREFIX"
mkdir -p "$BIN"
install -m 0644 "$REPO/LICENSE" "$REPO/THIRD_PARTY_NOTICES.md" "$PREFIX/"
install -m 0755 "$REPO/uninstall.sh" "$PREFIX/uninstall.sh"
for bin_file in "$REPO/bin/"*; do
    [ -f "$bin_file" ] && install -m 0755 "$bin_file" "$BIN/"
done
mkdir -p "$PREFIX/agent-app"
install -m 0644 "$REPO/agent-app/main.py" "$PREFIX/agent-app/"
mkdir -p "$PREFIX/files"
install -m 0644 "$REPO/files/"*.py "$REPO/files/"*.qss "$REPO/files/"*.svg "$PREFIX/files/"
mkdir -p "$PREFIX/files/translations"
cp -R "$REPO/files/translations/." "$PREFIX/files/translations/"
mkdir -p "$PREFIX/files/qml"
cp -R "$REPO/files/qml/." "$PREFIX/files/qml/"
mkdir -p "$PREFIX/desktop"
cp -R "$REPO/desktop/." "$PREFIX/desktop/"
for plugin in agent islands system search control; do
    APPLET="${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/org.lumen.$plugin"
    mkdir -p "$APPLET/contents/ui" "$APPLET/contents/config"
    METADATA=metadata.json
    [ "$plugin" = agent ] || METADATA="$plugin-metadata.json"
    install -m 0644 "$REPO/plasmoid/$METADATA" "$APPLET/metadata.json"
    install -m 0644 "$REPO/LICENSE" "$APPLET/LICENSE"
    install -m 0644 "$REPO/plasmoid/contents/ui/"*.qml "$REPO/plasmoid/contents/ui/"*.js "$APPLET/contents/ui/"
    install -m 0644 "$REPO/plasmoid/contents/config/"* "$APPLET/contents/config/"
    case "$plugin" in system) SURFACE=home;; search|control) SURFACE="$plugin";; *) SURFACE=tasks;; esac
    sed -i "s|<default>tasks</default>|<default>$SURFACE</default>|" "$APPLET/contents/config/main.xml"
    # Plasma does not inherit additions to an interactive shell's PATH.
    /usr/bin/python3 - "$APPLET/contents/ui" "$BIN/lumen-panel" <<'PYCODE'
import json, shlex, sys
from pathlib import Path
for name in ('main.qml', 'ConfigGeneral.qml'):
    path = Path(sys.argv[1]) / name
    path.write_text(path.read_text().replace('property string helper: "/usr/bin/lumen-panel"',
        'property string helper: ' + json.dumps(shlex.quote(sys.argv[2]))))
PYCODE
done
chmod 0755 "$BIN"/lumen-* "$BIN"/lumen_krunner.py "$BIN"/lumen_mcp.py 2>/dev/null || true

# ---- XDG data files --------------------------------------------------------
say "Installiere Desktop-Integration" "Installing desktop integration"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

subst() { sed "s|%INSTALL_BIN%|$BIN|g" "$1"; }

mkdir -p "$DATA_HOME/applications" "$DATA_HOME/kio/servicemenus" \
         "$DATA_HOME/krunner/dbusplugins" "$DATA_HOME/dbus-1/services" \
         "$DATA_HOME/icons/hicolor/scalable/apps" \
         "$CONFIG_HOME/autostart"

# icon
install -m 0644 "$REPO/icons/hicolor/scalable/apps/lumen.svg" "$DATA_HOME/icons/hicolor/scalable/apps/lumen.svg"
install -m 0644 "$REPO/icons/hicolor/scalable/apps/lumen-files.svg" "$DATA_HOME/icons/hicolor/scalable/apps/lumen-files.svg"
for tool in meetings household workbench radio vault inbox reader sound wissen translate system; do
    install -m 0644 "$REPO/icons/hicolor/scalable/apps/lumen-$tool.svg" "$DATA_HOME/icons/hicolor/scalable/apps/"
done

subst "$REPO/data/kio-servicemenus/lumen.desktop" > "$DATA_HOME/kio/servicemenus/lumen.desktop"
subst "$REPO/data/applications/lumen.desktop" > "$DATA_HOME/applications/lumen.desktop"
# Plasma's icon widget launches its private copy, which must be executable.
if [ -f "$DATA_HOME/plasma_icons/lumen.desktop" ]; then
    install -m 0755 "$DATA_HOME/applications/lumen.desktop" "$DATA_HOME/plasma_icons/lumen.desktop"
fi
subst "$REPO/data/applications/lumen-ask.desktop" > "$DATA_HOME/applications/lumen-ask.desktop"
subst "$REPO/data/applications/lumen-ask-sel.desktop" > "$DATA_HOME/applications/lumen-ask-sel.desktop"
subst "$REPO/data/applications/lumen-vision.desktop" > "$DATA_HOME/applications/lumen-vision.desktop"
subst "$REPO/data/applications/lumen-sel.desktop" > "$DATA_HOME/applications/lumen-sel.desktop"
subst "$REPO/data/applications/lumen-files.desktop" > "$DATA_HOME/applications/lumen-files.desktop"
subst "$REPO/data/applications/lumen-open.desktop" > "$DATA_HOME/applications/lumen-open.desktop"
subst "$REPO/data/applications/lumen-search.desktop" > "$DATA_HOME/applications/lumen-search.desktop"
subst "$REPO/data/applications/lumen-updater.desktop" > "$DATA_HOME/applications/lumen-updater.desktop"
subst "$REPO/data/applications/lumen-apps.desktop" > "$DATA_HOME/applications/lumen-apps.desktop"
subst "$REPO/data/applications/lumen-search-preview.desktop" > "$DATA_HOME/applications/lumen-search-preview.desktop"
for tool in meetings household workbench radio vault inbox reader sound wissen translate system; do
    subst "$REPO/data/applications/lumen-$tool.desktop" > "$DATA_HOME/applications/lumen-$tool.desktop"
done
subst "$REPO/data/krunner-dbusplugins/lumen-runner.desktop" > "$DATA_HOME/krunner/dbusplugins/lumen-runner.desktop"
subst "$REPO/data/dbus-1-services/org.lumen.runner.service" > "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
subst "$REPO/data/autostart/lumen-krunner-runner.desktop" > "$CONFIG_HOME/autostart/lumen-krunner-runner.desktop"
subst "$REPO/data/autostart/lumen-versions.desktop" > "$CONFIG_HOME/autostart/lumen-versions.desktop"

# refresh caches
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && /usr/bin/python3 -c 'import dbus' 2>/dev/null; then
        "$BIN/lumen-python" "$PREFIX/files/desktop_settings.py" refresh-shortcuts <<< '{}' \
            || warn "Lumen-Tastenkürzel konnten nicht neu geladen werden; beim nächsten Anmelden erneut prüfen." "Lumen shortcuts could not be reloaded; check again after your next login."
    else
        kbuildsycoca6 >/dev/null 2>&1 || true
    fi
fi

# ---- opencode MCP / commands / skill --------------------------------------
if [ "$SKIP_MCP" = 0 ]; then
    say "Verdrahte opencode (MCP / Commands / Skill)" "Configuring OpenCode (MCP / commands / skill)"
    LUMEN_MCP_PY="$BIN/lumen_mcp.py" LUMEN_SHARE="$REPO" \
        "$BIN/lumen-setup" || warn "lumen-setup fehlgeschlagen" "lumen-setup failed"
else
    say "OpenCode-Konfiguration unverändert (--no-mcp)" "OpenCode configuration unchanged (--no-mcp)"
fi

# Preserve reports, keep legacy shell imports available, and install opt-in jobs.
/usr/bin/python3 "$PREFIX/files/lumen_migrate.py" --bin "$BIN"
mkdir -p "$PREFIX/shell" "$PREFIX/opencode-command" "$PREFIX/opencode-skill/lumen-admin"
cp "$REPO/shell/"* "$PREFIX/shell/"
cp "$REPO/opencode-command/"*.md "$PREFIX/opencode-command/"
for skill in lumen-admin lumen-projects; do
    mkdir -p "$PREFIX/opencode-skill/$skill"
    cp "$REPO/opencode-skill/$skill/SKILL.md" "$PREFIX/opencode-skill/$skill/"
done
UNITDIR="$CONFIG_HOME/systemd/user"
mkdir -p "$UNITDIR"
subst "$REPO/system/systemd/user/lumen-jobs.service" > "$UNITDIR/lumen-jobs.service"
cp "$REPO/system/systemd/user/lumen-jobs.timer" "$UNITDIR/"
systemctl --user daemon-reload >/dev/null 2>&1 || true

# ---- systemd user timer ----------------------------------------------------
if [ "$SKIP_TIMER" = 0 ] && command -v systemctl >/dev/null 2>&1; then
    say "Richte systemd-User-Timer ein" "Installing systemd user timer"
    UNITDIR="$CONFIG_HOME/systemd/user"
    mkdir -p "$UNITDIR"
    subst "$REPO/systemd/lumen-watch.service" > "$UNITDIR/lumen-watch.service"
    cp "$REPO/systemd/lumen-watch.timer" "$UNITDIR/lumen-watch.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    say "Timer installiert; bestehenden Aktivierungszustand beibehalten." "Timer installed; existing activation state preserved."
fi

say "Fertig." "Done."
if [ "$DESKTOP" = 1 ]; then
    "$BIN/lumen-desktop-setup" --apply --replace-panels
else
    "$BIN/lumen-desktop-setup"
fi
case "${LUMEN_LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}" in de*)
cat <<EOF

Nächste Schritte:
  1. opencode neu starten, damit MCP/Commands/Skill greifen.
  2. KRunner neu laden (falls der 'ai <Frage>'-Trigger fehlt):
       kquitapp6 krunner
  3. App starten:  $BIN/lumen-agent-app
     oder über das Startmenü: "Lumen"
  4. Desktop bewusst aktivieren (ersetzt Panels nach Sicherung):
       $BIN/lumen-desktop-setup --apply --replace-panels

Konfiguration (optional, per Umgebungsvariablen):
  LUMEN_OPENCODE_BIN      Pfad zur opencode-Binary
  LUMEN_WORKDIR           Standard-Arbeitsordner
  LUMEN_WATCH_ANALYZE=0   Auto-Analyse im Wächter aus

Deinstallieren:  $PREFIX/uninstall.sh
EOF
;;
*)
cat <<EOF

Next steps:
  1. Restart OpenCode to load MCP, commands and skill.
  2. Reload KRunner if the 'ai <question>' trigger is missing:
       kquitapp6 krunner
  3. Start the app:  $BIN/lumen-agent-app
     or choose "Lumen" in the application menu.
  4. Activate the desktop when ready (replaces panels after a backup):
       $BIN/lumen-desktop-setup --apply --replace-panels

Optional environment variables:
  LUMEN_OPENCODE_BIN      Path to the OpenCode executable
  LUMEN_WORKDIR           Default working directory
  LUMEN_WATCH_ANALYZE=0   Disable automatic watcher analysis

Uninstall:  $PREFIX/uninstall.sh
EOF
;;
esac

# Local installation identity for the native updater (never personal app data).
/usr/bin/python3 - "$REPO" "$PREFIX" <<'PYCODE'
import json, os, pathlib, subprocess
import sys
repo, prefix = map(pathlib.Path, sys.argv[1:])
revision = os.environ.get('LUMEN_SOURCE_REVISION', '')
if not revision:
    result = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, capture_output=True)
    if result.returncode == 0: revision = result.stdout.strip()
staged = prefix / 'install.json.next'
staged.write_text(json.dumps({'revision': revision, 'kind': 'user'}))
os.replace(staged, prefix / 'install.json')
PYCODE
