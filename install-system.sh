#!/usr/bin/env bash
# install-system.sh — OPTIONAL system-wide tweaks. Requires root.
#
# Currently installs:
#   /etc/sudoers.d/20-opencode-sudo-cache
#     - timestamp_type=global + timestamp_timeout=15, so opencode's non-TTY
#       tool calls don't re-prompt for a password every time and GUI askpass
#       (ksshaskpass) works reliably.
#
# It also ensures sudo uses a graphical askpass if none is configured.
#
# Usage:
#   sudo ./install-system.sh
#   sudo ./install-system.sh --uninstall
#
# Safety: the sudoers file is validated with `visudo -cf` before it is put in
# place. On failure nothing is changed.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/etc/sudoers.d/20-opencode-sudo-cache"
DST="/etc/sudoers.d/20-opencode-sudo-cache"

if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte mit root ausführen:  sudo $0 $*" >&2
    exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
    echo "==> Entferne $DST"
    rm -f "$DST"
    echo "Fertig. (askpass-Konfiguration in /etc/sudo.conf bleibt unverändert.)"
    exit 0
fi

echo "==> Prüfe sudoers-Datei"
if ! visudo -cf "$SRC"; then
    echo "Validierung fehlgeschlagen – nichts geändert." >&2
    exit 1
fi

echo "==> Installiere $DST"
install -m 0440 -o root -g root "$SRC" "$DST"

# ensure a graphical askpass is configured (KDE first, then GNOME/OpenSSH)
if ! grep -qE '^\s*Path\s+askpass' /etc/sudo.conf 2>/dev/null; then
    askpass=""
    for c in /usr/bin/ksshaskpass /usr/libexec/openssh/gnome-ssh-askpass /usr/bin/ssh-askpass; do
        [ -x "$c" ] && { askpass="$c"; break; }
    done
    if [ -n "$askpass" ]; then
        echo "==> Konfiguriere askpass: $askpass"
        printf '\n# Added by opencode-agent\nPath askpass %s\n' "$askpass" >> /etc/sudo.conf
    else
        echo "Hinweis: kein grafisches askpass gefunden – übersprungen." >&2
    fi
fi

echo
echo "Fertig. Wirkung: sudo-Credentials werden user-weit 15 Minuten gecacht."
echo "Rückgängig:  sudo $0 --uninstall"
