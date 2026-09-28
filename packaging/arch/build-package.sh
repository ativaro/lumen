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

say "Erzeuge Quell-Tarball opencode-lumen-$PKGVER.tar.gz"
rm -f "$ARCHDIR/opencode-lumen-$PKGVER.tar.gz"

# Prefer git archive (only tracked files); fall back to tar with excludes.
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$REPO" archive --format=tar.gz \
        --prefix="opencode-lumen-$PKGVER/" \
        -o "$ARCHDIR/opencode-lumen-$PKGVER.tar.gz" HEAD
else
    tar --exclude='.git' --exclude='__pycache__' --exclude='distro' \
        --exclude='packaging/arch/pkg' --exclude='packaging/arch/src' \
        --transform "s,^,opencode-lumen-$PKGVER/," \
        -czf "$ARCHDIR/opencode-lumen-$PKGVER.tar.gz" -C "$REPO" .
fi
say "Tarball: $(du -h "$ARCHDIR/opencode-lumen-$PKGVER.tar.gz" | cut -f1)"

say "Baue Paket mit makepkg (lokaler Quell-Tarball)"
cd "$ARCHDIR"
rm -rf src pkg
# -d: skip dependency checks so maintainers using the standalone opencode
# installer can build locally. Published builds use the real deps.
LOCALSRC=1 makepkg -d -f --noconfirm

echo
ls -1 "$ARCHDIR"/opencode-lumen-"$PKGVER"-*.pkg.tar.zst 2>/dev/null || true

if [ "$DO_INSTALL" = 1 ]; then
    say "Installiere Paket (pacman)"
    sudo -A pacman -U --noconfirm "$ARCHDIR"/opencode-lumen-"$PKGVER"-*.pkg.tar.zst
fi

say "Fertig."
