#!/usr/bin/env bash
# Download first, install the native runtime, then finish in the graphical wizard.
# Keep execution in a function so a truncated curl | bash stream cannot install.
set -euo pipefail

bootstrap() {
    message() {
        case "${LUMEN_LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}" in
            de*) printf '%s\n' "$1";;
            *) printf '%s\n' "$2";;
        esac
    }
    local use_local=0 source='' stage='' prefix
    if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != --local ]; }; then
        message 'Aufruf: bootstrap.sh [--local]' 'Usage: bootstrap.sh [--local]' >&2
        return 1
    fi
    # A downloaded/streamed script has no checkout. A local script must use its
    # own sources, including authenticated private clones, rather than download again.
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
        source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [ -f "$source/install.sh" ]; then use_local=1; fi
    fi
    if [ "${1:-}" = --local ] && [ "$use_local" = 0 ]; then
        message 'Lokale Installationsdateien fehlen.' 'Local installation files are missing.' >&2
        return 1
    fi
    if [ "$(id -u)" = 0 ]; then
        message 'Bitte als normaler Benutzer starten, ohne sudo vor dem Einzeiler.' 'Run as your normal user, without sudo before the one-line command.' >&2
        return 1
    fi
    if ! command -v pacman >/dev/null; then
        message 'Der Einzeiler unterstützt derzeit Arch/CachyOS. Andere Systeme: INSTALL.md im Lumen-Repository.' 'This installer currently supports Arch/CachyOS. For other systems, see INSTALL.md in the Lumen repository.' >&2
        return 1
    fi
    case ":${XDG_CURRENT_DESKTOP:-}:" in
        *:KDE:*) ;;
        *) message 'Bitte in einer angemeldeten KDE-Plasma-6-Sitzung starten.' 'Run inside a logged-in KDE Plasma 6 session.' >&2; return 1 ;;
    esac
    if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] || { [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; }; then
        message 'Für den Einrichtungsassistenten wird eine grafische Sitzung benötigt.' 'The setup wizard needs a graphical session.' >&2
        return 1
    fi
    prefix="${PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/lumen}"
    export PREFIX="$prefix"
    if [ "$use_local" = 0 ]; then
        stage="$(mktemp -d)"
        trap "$(printf 'rm -rf -- %q' "$stage")" EXIT
        message 'Lumen wird heruntergeladen …' 'Downloading Lumen …'
        source="$stage/lumen"
        if ! command -v git >/dev/null; then sudo pacman -S --needed --noconfirm -- git; fi
        if ! git clone --depth=1 --branch main --single-branch https://github.com/ativaro/lumen.git "$source"; then
            message 'Download fehlgeschlagen. Prüfe den Git-Zugriff auf das private GitHub-Repository.' 'Download failed. Check Git access to the private GitHub repository.' >&2
            return 1
        fi
    fi

    local packages=(git python pyside6 python-gobject python-pillow python-dbus python-markdown-it-py openssl
        qt6-tools kde-cli-tools breeze-icons polkit gcc pkgconf qt6-base)
    if ! pacman -T "${packages[@]}" >/dev/null; then
        message 'Die grafische Basis wird installiert. Dafür ist gegebenenfalls dein Systempasswort nötig.' 'Installing the graphical runtime. Your system password may be required.'
        sudo pacman -S --needed --noconfirm -- "${packages[@]}"
    fi
    "${LUMEN_PYTHON:-/usr/bin/python3}" -c 'import PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtQuick, PySide6.QtQuickWidgets, PySide6.QtDBus, gi, PIL, dbus, markdown_it'
    if ! qdbus6 org.kde.plasmashell /PlasmaShell >/dev/null 2>&1; then
        message 'Plasma 6 ist nicht erreichbar. Bitte in deiner Desktop-Sitzung erneut starten.' 'Plasma 6 is unavailable. Try again inside your desktop session.' >&2
        return 1
    fi
    bash "$source/install.sh"
    message 'Lumen ist lokal installiert. Der Einrichtungsassistent wird geöffnet …' 'Lumen is installed locally. Opening the setup wizard …'
    # Explicit start also works after a previously skipped/completed first-run setup.
    "$prefix/bin/lumen-setup-wizard"
}

bootstrap "$@"
