#!/usr/bin/env bash
# make-aur.sh — prepare an AUR-ready source tree for lumen.
#
# Creates distro/aur/ containing PKGBUILD, lumen.install and .SRCINFO, ready
# to push to the AUR. The PKGBUILD's remote source (_srcurl) is used, so the
# AUR build fetches the release tarball from the git host — not a local file.
#
# Usage:
#   ./distro/aur/make-aur.sh            # prepare + generate .SRCINFO
#   ./distro/aur/make-aur.sh --sums     # also run updpkgsums (needs the tag to exist)
#
# Before running, make sure you tagged the release (v$pkgver) and pushed it,
# and that _srcurl in the PKGBUILD points at the real repository.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHDIR="$REPO/packaging/arch"
AURDIR="$REPO/distro/aur"
PKGVER="$(grep -m1 '^pkgver=' "$ARCHDIR/PKGBUILD" | cut -d= -f2)"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

mkdir -p "$AURDIR"
cp "$ARCHDIR/PKGBUILD" "$AURDIR/PKGBUILD"
cp "$ARCHDIR/lumen.install" "$AURDIR/lumen.install"

# The AUR build fetches the remote release tarball. Fetch the real checksum.
if [ "${1:-}" = "--sums" ]; then
    say "updpkgsums (lädt Quell-Tarball von _srcurl)"
    ( cd "$AURDIR" && updpkgsums )
fi

say "Erzeuge .SRCINFO"
( cd "$AURDIR" && makepkg --printsrcinfo > .SRCINFO )

cat <<EOF

$(say "AUR-Tree bereit: $AURDIR")
Dateien:
$(ls -1 "$AURDIR" | sed 's/^/  /')

Prüfe vor dem Upload:
  - 'url=' und '_srcurl=' im PKGBUILD zeigen auf das echte Repo
  - der Release-Tag v$PKGVER existiert und ist gepusht
  - sha256sums gesetzt (./distro/aur/make-aur.sh --sums)

Upload (als AUR-Maintainer):
  git clone ssh://aur@aur.archlinux.org/lumen.git
  cp $AURDIR/{PKGBUILD,.SRCINFO,lumen.install} lumen/
  cd lumen && git add -A && git commit -m 'Initial' && git push
EOF
