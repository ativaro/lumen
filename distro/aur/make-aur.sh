#!/usr/bin/env bash
# make-aur.sh — prepare an AUR-ready source tree for opencode-agent.
#
# Creates distro/aur/ containing PKGBUILD, .install, .SRCINFO and a source
# tarball, ready to `makepkg --printsrcinfo` / push to the AUR.
#
# Usage:
#   ./distro/aur/make-aur.sh
#
# For the AUR, the PKGBUILD should point at a real source URL (GitHub tag).
# This helper produces the layout and a .SRCINFO for review.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHDIR="$REPO/packaging/arch"
AURDIR="$REPO/distro/aur"
PKGVER="$(grep -m1 '^pkgver=' "$ARCHDIR/PKGBUILD" | cut -d= -f2)"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

mkdir -p "$AURDIR"
cp "$ARCHDIR/PKGBUILD" "$AURDIR/PKGBUILD"
cp "$ARCHDIR/opencode-agent.install" "$AURDIR/opencode-agent.install"

# build source tarball (git archive = only tracked files)
say "Erzeuge Quell-Tarball"
rm -f "$AURDIR/opencode-agent-$PKGVER.tar.gz"
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$REPO" archive --format=tar.gz \
        --prefix="opencode-agent-$PKGVER/" \
        -o "$AURDIR/opencode-agent-$PKGVER.tar.gz" HEAD
else
    tar --exclude='.git' --exclude='__pycache__' --exclude='distro' \
        --transform "s,^,opencode-agent-$PKGVER/," \
        -czf "$AURDIR/opencode-agent-$PKGVER.tar.gz" -C "$REPO" .
fi

# generate .SRCINFO
say "Erzeuge .SRCINFO"
( cd "$AURDIR" && makepkg --printsrcinfo > .SRCINFO )

cat <<EOF

$(say "AUR-Tree bereit: $AURDIR")
Dateien:
$(ls -1 "$AURDIR" | sed 's/^/  /')

Vor dem AUR-Upload den 'source='-Eintrag im PKGBUILD auf die echte
GitHub-Release-URL setzen und sha256sums aktualisieren:
  updpkgsums   # im AUR-Verzeichnis

Dann (als AUR-Maintainer):
  git clone ssh://aur@aur.archlinux.org/opencode-agent.git
  cp $AURDIR/{PKGBUILD,.SRCINFO,opencode-agent.install} opencode-agent/
  cd opencode-agent && git add -A && git commit -m 'Initial' && git push
EOF
