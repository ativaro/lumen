#!/usr/bin/env bash
# Download first, install the native runtime, then finish in the graphical wizard.
# Keep execution in a function so a truncated curl | bash stream cannot install.
set -euo pipefail

bootstrap() {
    if [ "$(id -u)" = 0 ]; then
        echo 'Bitte als normaler Benutzer starten, ohne sudo vor dem Einzeiler.' >&2
        return 1
    fi
    if ! command -v pacman >/dev/null; then
        echo 'Der Einzeiler unterstützt derzeit Arch/CachyOS. Andere Systeme: INSTALL.md im Lumen-Repository.' >&2
        return 1
    fi
    case ":${XDG_CURRENT_DESKTOP:-}:" in
        *:KDE:*) ;;
        *) echo 'Bitte in einer angemeldeten KDE-Plasma-6-Sitzung starten.' >&2; return 1 ;;
    esac
    if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] || { [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; }; then
        echo 'Für den Einrichtungsassistenten wird eine grafische Sitzung benötigt.' >&2
        return 1
    fi
    local stage prefix
    stage="$(mktemp -d)"
    trap "$(printf 'rm -rf -- %q' "$stage")" EXIT
    prefix="${PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/lumen}"
    export PREFIX="$prefix"
    echo 'Lumen wird heruntergeladen …'
    curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 \
        --connect-timeout 20 --max-time 300 \
        https://codeload.github.com/ativaro/lumen/tar.gz/refs/heads/main -o "$stage/lumen.tar.gz"

    local packages=(python python-pyqt5 qt5-svg python-gobject python-pillow python-dbus
        qt6-tools kde-cli-tools breeze-icons polkit)
    if ! pacman -T "${packages[@]}" >/dev/null; then
        echo 'Die grafische Basis wird installiert. Dafür ist gegebenenfalls dein Systempasswort nötig.'
        sudo pacman -S --needed --noconfirm -- "${packages[@]}"
    fi
    # Use Python's safe archive filter; never extract downloaded paths as root.
    /usr/bin/python3 - "$stage" <<'PY'
from pathlib import Path
import sys, tarfile
folder = Path(sys.argv[1])
with tarfile.open(folder / 'lumen.tar.gz') as archive:
    archive.extractall(folder, filter='data')
if not (folder / 'lumen-main/install.sh').is_file():
    raise SystemExit('Das heruntergeladene Lumen-Archiv ist unvollständig.')
PY
    /usr/bin/python3 -c 'import PyQt5.QtWidgets, PyQt5.QtSvg, gi, PIL, dbus'
    if ! qdbus6 org.kde.plasmashell /PlasmaShell >/dev/null 2>&1; then
        echo 'Plasma 6 ist nicht erreichbar. Bitte in deiner Desktop-Sitzung erneut starten.' >&2
        return 1
    fi
    bash "$stage/lumen-main/install.sh"
    echo 'Lumen ist lokal installiert. Der Einrichtungsassistent wird geöffnet …'
    # Explicit start also works after a previously skipped/completed first-run setup.
    "$prefix/bin/lumen-setup-wizard"
}

bootstrap "$@"
