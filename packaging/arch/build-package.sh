#!/usr/bin/env bash
# build-package.sh — build the Arch/CachyOS package from this repo.
#
# Creates a checked source tarball from a clean commit, then runs makepkg.
#
# Usage:
#   ./packaging/arch/build-package.sh            # build with makepkg
#   ./packaging/arch/build-package.sh --srcinfo  # just print .SRCINFO
#   ./packaging/arch/build-package.sh --source-only # archive + checksum only
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
SOURCE_ONLY=0
case "${1:-}" in
    --srcinfo) cd "$ARCHDIR"; LOCALSRC=1 exec makepkg --printsrcinfo ;;
    --source-only) SOURCE_ONLY=1 ;;
    --install) DO_INSTALL=1 ;;
    "") ;;
    *) echo "Unbekannte Option: $1" >&2; exit 2 ;;
esac

# An archive must identify exactly the source that was reviewed.
if [[ "$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null || true)" != "$REPO" ]]; then
    echo 'Für ein neues Releasearchiv wird ein Git-Checkout benötigt.' >&2; exit 1
fi
if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=all)" ]]; then
    echo 'Quelländerungen zuerst prüfen und committen; kein Archiv aus einem gemischten Stand.' >&2; exit 1
fi
say "Erzeuge Quell-Tarball lumen-$PKGVER.tar.gz"
BUILD_STAGE="$(mktemp -d)"
trap 'rm -rf "$BUILD_STAGE"' EXIT
mkdir -p "$BUILD_STAGE/lumen-$PKGVER"
/usr/bin/python3 "$REPO/packaging/source-identity.py" "$REPO" > "$BUILD_STAGE/lumen-$PKGVER/source.json"
SOURCE_DATE_EPOCH="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_date_epoch"])' "$BUILD_STAGE/lumen-$PKGVER/source.json")"
export SOURCE_DATE_EPOCH

# Only the maintainer's Desktop app identity is bundled, never a user's tokens.
GOOGLE_CLIENT="${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-$REPO/files/google-drive-client.json}"
if [[ -n "${LUMEN_GOOGLE_OAUTH_CLIENT_FILE:-}" || -f "$GOOGLE_CLIENT" ]]; then
    /usr/bin/python3 "$REPO/files/google_drive.py" --bundle-client "$GOOGLE_CLIENT" \
        "$BUILD_STAGE/lumen-$PKGVER/files/google-drive-client.json"
else
    say "Ohne Google-App-Konfiguration: zentrale Anmeldung bleibt deaktiviert."
fi

git -C "$REPO" archive --format=tar --prefix="lumen-$PKGVER/" -o "$BUILD_STAGE/source.tar" HEAD
tar --append --file "$BUILD_STAGE/source.tar" --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
    --mode=0644 -C "$BUILD_STAGE" "lumen-$PKGVER/source.json"
if [[ -f "$BUILD_STAGE/lumen-$PKGVER/files/google-drive-client.json" ]]; then
    tar --append --file "$BUILD_STAGE/source.tar" --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
        --mode=0644 -C "$BUILD_STAGE" "lumen-$PKGVER/files/google-drive-client.json"
fi
gzip -n -c "$BUILD_STAGE/source.tar" > "$BUILD_STAGE/source.tar.gz"
mv "$BUILD_STAGE/source.tar.gz" "$ARCHDIR/lumen-$PKGVER.tar.gz"
cd "$ARCHDIR"
sha256sum "lumen-$PKGVER.tar.gz" > "lumen-$PKGVER.tar.gz.sha256"
say "Tarball: $(du -h "$ARCHDIR/lumen-$PKGVER.tar.gz" | cut -f1)"
[[ "$SOURCE_ONLY" = 0 ]] || exit 0

say "Baue Paket mit makepkg (lokaler Quell-Tarball)"
cd "$ARCHDIR"
rm -rf src pkg
LOCALSRC=1 makepkg -f --noconfirm

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
