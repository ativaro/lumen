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

"$REPO/bin/lumen-python" -c "import PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtQuick, PySide6.QtQuickWidgets, gi, PIL, yaml, markdown_it" || { message "Benötigt: PySide6 mit QtQuick/QtSvg, PyGObject, Pillow, PyYAML und markdown-it-py" "Required: PySide6 with QtQuick/QtSvg, PyGObject, Pillow, PyYAML and markdown-it-py" >&2; exit 1; }
if ! command -v g++ >/dev/null || ! command -v pkg-config >/dev/null || ! pkg-config --exists Qt6Core Qt6DBus; then
    if command -v pacman >/dev/null && command -v pkexec >/dev/null; then
        say "Richte den nativen Aufnahmehelfer ein" "Preparing the native capture helper"
        pkexec pacman -S --needed --noconfirm -- gcc pkgconf qt6-base
    else
        message "Benötigt: g++, pkg-config und Qt-6-Core/DBus-Entwicklungsdateien." "Required: g++, pkg-config and Qt 6 Core/DBus development files." >&2
        exit 1
    fi
fi
if ! command -v cargo >/dev/null; then
    if command -v pacman >/dev/null && command -v pkexec >/dev/null; then
        say "Richte den Dokumentleser ein" "Preparing the document reader"
        pkexec pacman -S --needed --noconfirm -- rust
    else
        message "Benötigt: Rust mit cargo (ab 1.89) für den Dokumentleser." "Required: Rust with cargo (1.89 or newer) for the document reader." >&2
        exit 1
    fi
fi
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
# Validate before changing the installation. Source updates without a client
# preserve the existing app identity and all separately stored user tokens.
GOOGLE_CLIENT="${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-$REPO/files/google-drive-client.json}"
GOOGLE_STAGE="$(mktemp -d)"
trap 'rm -rf "$GOOGLE_STAGE"' EXIT
/usr/bin/python3 "$REPO/packaging/source-identity.py" "$REPO" --kind user > "$GOOGLE_STAGE/install.json"
if [[ -n "${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-}" || -f "$GOOGLE_CLIENT" ]]; then
    /usr/bin/python3 "$REPO/files/google_drive.py" --bundle-client "$GOOGLE_CLIENT" "$GOOGLE_STAGE/client.json"
fi
say "Installiere Dateien nach $PREFIX" "Installing files into $PREFIX"
mkdir -p "$BIN"
install -m 0644 "$REPO/LICENSE" "$REPO/THIRD_PARTY_NOTICES.md" "$PREFIX/"
install -m 0755 "$REPO/uninstall.sh" "$PREFIX/uninstall.sh"
for bin_file in "$REPO/bin/"*; do
    [ -f "$bin_file" ] && install -m 0755 "$bin_file" "$BIN/"
done
bash "$REPO/native/build-capture.sh" "$BIN/lumen-window-capture"
bash "$REPO/native/build-topbar.sh" "$BIN/lumen-topbar"
bash "$REPO/native/build-document.sh" "$BIN/lumen-document"
mkdir -p "$PREFIX/agent-app"
install -m 0644 "$REPO/agent-app/main.py" "$PREFIX/agent-app/"
mkdir -p "$PREFIX/files"
/usr/bin/python3 "$REPO/packaging/retire-desktop.py" "$PREFIX"
for module in "$REPO/files/"*.py; do
    [[ "$(basename "$module")" == test_* ]] || install -m 0644 "$module" "$PREFIX/files/"
done
install -m 0644 "$REPO/files/"*.qss "$REPO/files/"*.svg "$PREFIX/files/"

if [[ -f "$GOOGLE_STAGE/client.json" ]]; then
    install -m 0644 "$GOOGLE_STAGE/client.json" "$PREFIX/files/google-drive-client.json"
fi
for asset in translations qml fonts notes_icons memory-runtime browser-runtime engine-plugins; do
    mkdir -p "$PREFIX/files/$asset"
    cp -R "$REPO/files/$asset/." "$PREFIX/files/$asset/"
done
mkdir -p "$PREFIX/desktop"
cp -R "$REPO/desktop/." "$PREFIX/desktop/"
APPLET="${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/org.lumen.notificationhost"
STAGED_APPLET="$GOOGLE_STAGE/notificationhost"
mkdir -p "$STAGED_APPLET"
cp -R "$REPO/plasmoid/." "$STAGED_APPLET/"
/usr/bin/python3 - "$STAGED_APPLET/contents/ui/main.qml" "$BIN/lumen-panel" <<'PYCODE'
import json, shlex, sys
from pathlib import Path
path=Path(sys.argv[1])
path.write_text(path.read_text().replace('"/usr/bin/lumen-panel"',json.dumps(shlex.quote(sys.argv[2]))))
PYCODE
if [ -d "$APPLET" ]; then PACKAGE_ACTION=--upgrade; else PACKAGE_ACTION=--install; fi
kpackagetool6 --type Plasma/Applet "$PACKAGE_ACTION" "$STAGED_APPLET"
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
install -m 0644 "$REPO/icons/hicolor/scalable/apps/"*.svg "$DATA_HOME/icons/hicolor/scalable/apps/"

subst "$REPO/data/kio-servicemenus/lumen.desktop" > "$DATA_HOME/kio/servicemenus/lumen.desktop"
subst "$REPO/data/applications/lumen.desktop" > "$DATA_HOME/applications/lumen.desktop"
# Plasma's icon widget launches its private copy, which must be executable.
if [ -f "$DATA_HOME/plasma_icons/lumen.desktop" ]; then
    install -m 0755 "$DATA_HOME/applications/lumen.desktop" "$DATA_HOME/plasma_icons/lumen.desktop"
fi
subst "$REPO/data/applications/lumen-toggle.desktop" > "$DATA_HOME/applications/lumen-toggle.desktop"
subst "$REPO/data/applications/lumen-ask.desktop" > "$DATA_HOME/applications/lumen-ask.desktop"
subst "$REPO/data/applications/lumen-ask-sel.desktop" > "$DATA_HOME/applications/lumen-ask-sel.desktop"
subst "$REPO/data/applications/lumen-companion.desktop" > "$DATA_HOME/applications/lumen-companion.desktop"
subst "$REPO/data/applications/lumen-server-connect.desktop" > "$DATA_HOME/applications/lumen-server-connect.desktop"
mkdir -p "$CONFIG_HOME/systemd/user"
subst "$REPO/system/systemd/user/lumen-topbar.service" > "$CONFIG_HOME/systemd/user/lumen-topbar.service"
subst "$REPO/system/systemd/user/lumen-server-connector.service" > "$CONFIG_HOME/systemd/user/lumen-server-connector.service"
command -v xdg-mime >/dev/null 2>&1 && xdg-mime default lumen-server-connect.desktop x-scheme-handler/lumen-server || true
subst "$REPO/data/applications/lumen-window-capture.desktop" > "$DATA_HOME/applications/lumen-window-capture.desktop"
subst "$REPO/data/applications/lumen-vision.desktop" > "$DATA_HOME/applications/lumen-vision.desktop"
subst "$REPO/data/applications/lumen-sel.desktop" > "$DATA_HOME/applications/lumen-sel.desktop"
subst "$REPO/data/applications/lumen-files.desktop" > "$DATA_HOME/applications/lumen-files.desktop"
subst "$REPO/data/applications/lumen-open.desktop" > "$DATA_HOME/applications/lumen-open.desktop"
subst "$REPO/data/applications/lumen-search.desktop" > "$DATA_HOME/applications/lumen-search.desktop"
subst "$REPO/data/applications/lumen-updater.desktop" > "$DATA_HOME/applications/lumen-updater.desktop"
subst "$REPO/data/applications/lumen-notification.desktop" > "$DATA_HOME/applications/lumen-notification.desktop"
subst "$REPO/data/applications/lumen-apps.desktop" > "$DATA_HOME/applications/lumen-apps.desktop"
subst "$REPO/data/applications/lumen-search-preview.desktop" > "$DATA_HOME/applications/lumen-search-preview.desktop"
for tool in meetings household workbench radio vault inbox reader sound wissen translate system code; do
    subst "$REPO/data/applications/lumen-$tool.desktop" > "$DATA_HOME/applications/lumen-$tool.desktop"
done
subst "$REPO/data/krunner-dbusplugins/lumen-runner.desktop" > "$DATA_HOME/krunner/dbusplugins/lumen-runner.desktop"
subst "$REPO/data/dbus-1-services/org.lumen.runner.service" > "$DATA_HOME/dbus-1/services/org.lumen.runner.service"
subst "$REPO/data/autostart/lumen-krunner-runner.desktop" > "$CONFIG_HOME/autostart/lumen-krunner-runner.desktop"
subst "$REPO/data/autostart/lumen-versions.desktop" > "$CONFIG_HOME/autostart/lumen-versions.desktop"

# refresh caches
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache --force --ignore-theme-index "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
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
for skill in lumen-admin lumen-projects lumen-vault-http; do
    mkdir -p "$PREFIX/opencode-skill/$skill"
    cp "$REPO/opencode-skill/$skill/SKILL.md" "$PREFIX/opencode-skill/$skill/"
done
# Retired stock skill is replaced by the server catalogue; custom text survives.
/usr/bin/python3 - "$PREFIX/opencode-skill/lumen-service-access/SKILL.md" <<'PY_SKILL'
from pathlib import Path
from hashlib import sha256
import sys
path = Path(sys.argv[1])
if path.is_file() and not path.is_symlink() and sha256(path.read_bytes()).hexdigest() in (
        'b49193b08585240dbe8df6b30857d7cfed5c79bbdb94950bbee956fd13c652cc',
        '821b7405f5c2f434963dc5f79421def9987e20187c894b226e9bb30150269160'):
    path.unlink()
    if not any(path.parent.iterdir()): path.parent.rmdir()
PY_SKILL
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
    "$BIN/lumen-desktop-setup" --apply
else
    "$BIN/lumen-desktop-setup" --refresh-decoration
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
       $BIN/lumen-desktop-setup --apply

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
       $BIN/lumen-desktop-setup --apply

Optional environment variables:
  LUMEN_OPENCODE_BIN      Path to the OpenCode executable
  LUMEN_WORKDIR           Default working directory
  LUMEN_WATCH_ANALYZE=0   Disable automatic watcher analysis

Uninstall:  $PREFIX/uninstall.sh
EOF
;;
esac

# Local installation identity for the native updater (never personal app data).
install -m0644 "$GOOGLE_STAGE/install.json" "$PREFIX/install.json.next"
mv -f "$PREFIX/install.json.next" "$PREFIX/install.json"
