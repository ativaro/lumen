#!/usr/bin/env bash
# build-package.sh — build the Arch/CachyOS package from this repo.
#
# Creates a source tarball from the working tree (git archive if available,
# otherwise tar), drops it next to the PKGBUILD and runs makepkg.
#
# Usage:
#   ./packaging/arch/build-package.sh            # build with makepkg
#   ./packaging/arch/build-package.sh --srcinfo  # just print .SRCINFO
#   ./packaging/arch/build-package.sh --install   # build and install (needs root)
#   LUMEN_GOOGLE_OAUTH_CLIENT_FILE=/path/desktop.json ./packaging/arch/build-package.sh
#
# Output: distro/ PKGBUILD build dir with the .pkg.tar.zst

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHDIR="$REPO/packaging/arch"
PKGVER="$(grep -m1 '^pkgver=' "$ARCHDIR/PKGBUILD" | cut -d= -f2)"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

DO_INSTALL=0
case "${1:-}" in
    --srcinfo) exec bash -c "cd '$ARCHDIR' && makepkg --printsrcinfo" ;;
    --install) DO_INSTALL=1 ;;
    "") ;;
    *) echo "Unbekannte Option: $1" >&2; exit 2 ;;
esac

say "Erzeuge Quell-Tarball lumen-$PKGVER.tar.gz"
rm -f "$ARCHDIR/lumen-$PKGVER.tar.gz"
BUILD_STAGE="$(mktemp -d)"
trap 'rm -rf "$BUILD_STAGE"' EXIT

# Only the maintainer's Desktop app identity is bundled, never a user's tokens.
GOOGLE_CLIENT="${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-$REPO/files/google-drive-client.json}"
if [[ -n "${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-}" || -f "$GOOGLE_CLIENT" ]]; then
    /usr/bin/python3 "$REPO/files/google_drive.py" --bundle-client "$GOOGLE_CLIENT" \
        "$BUILD_STAGE/lumen-$PKGVER/files/google-drive-client.json"
else
    say "Ohne Google-App-Konfiguration: zentrale Anmeldung bleibt deaktiviert."
fi

# Prefer git archive (only tracked files); fall back to tar with excludes.
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$REPO" archive --format=tar \
        --prefix="lumen-$PKGVER/" \
        -o "$BUILD_STAGE/source.tar" HEAD
else
    tar --exclude='.git' --exclude='__pycache__' --exclude='distro' \
        --exclude='packaging/arch/pkg' --exclude='packaging/arch/src' \
        --exclude='files/google-drive-client.json' --exclude='client_secret_*.json' \
        --transform "s,^,lumen-$PKGVER/," \
        -cf "$BUILD_STAGE/source.tar" -C "$REPO" .
fi
if [[ -f "$BUILD_STAGE/lumen-$PKGVER/files/google-drive-client.json" ]]; then
    tar -rf "$BUILD_STAGE/source.tar" -C "$BUILD_STAGE" "lumen-$PKGVER/files/google-drive-client.json"
fi
gzip -c "$BUILD_STAGE/source.tar" > "$ARCHDIR/lumen-$PKGVER.tar.gz"
say "Tarball: $(du -h "$ARCHDIR/lumen-$PKGVER.tar.gz" | cut -f1)"

say "Baue Paket mit makepkg (lokaler Quell-Tarball)"
cd "$ARCHDIR"
rm -rf src pkg
# -d: skip dependency checks so maintainers using the standalone opencode
# installer can build locally. Published builds use the real deps.
LUMEN_SOURCE_REVISION="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)" LOCALSRC=1 makepkg -d -f --noconfirm

echo
mapfile -t PACKAGES < <(LOCALSRC=1 makepkg --packagelist)
ls -1 "${PACKAGES[@]}"

if [ "$DO_INSTALL" = 1 ]; then
    say "Installiere Paket (pacman)"
    # Resolve dependencies before touching the existing installation.
    sudo -A pacman -U --downloadonly --noconfirm "${PACKAGES[@]}"
    sudo -A /usr/bin/python3 "$REPO/files/lumen_upgrade.py" before
    if [[ "$(pacman -Qq opencode-lumen 2>/dev/null || true)" == opencode-lumen ]]; then
        # Legacy scriptlets disable services and erase reports. Preserve both.
        sudo -A pacman -Rdd --noscriptlet --noconfirm opencode-lumen
    fi
    sudo -A pacman -U --noconfirm "${PACKAGES[@]}"
    sudo -A /usr/bin/python3 "$REPO/files/lumen_upgrade.py" after
    /usr/bin/python3 "$REPO/files/lumen_migrate.py" --bin /usr/bin
fi

say "Fertig."
