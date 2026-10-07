#!/usr/bin/env bash
# make-repo.sh — build the package and add it to a local pacman repository.
#
# Creates a pacman repo under distro/cachyos/repo/ and prints the pacman.conf
# snippet so users can install/update via `pacman -Sy lumen`.
#
# Usage:
#   ./distro/cachyos/make-repo.sh            # build + repo-add
#   ./distro/cachyos/make-repo.sh --sign     # sign the package (needs GPG key)
#
# For a real distribution, host repo/ on a server/WebDAV and point pacman at it.
# For local installs the repo directory is enough (Server = file:///path).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHDIR="$REPO/packaging/arch"
REPODIR="$REPO/distro/cachyos/repo"
DBNAME="lumen"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

SIGN=0
[ "${1:-}" = "--sign" ] && SIGN=1

# 1) build
say "Baue Paket"
bash "$ARCHDIR/build-package.sh" >/dev/null
PKG="$(ls -1 "$ARCHDIR"/lumen-*.pkg.tar.zst | head -1)"
[ -n "$PKG" ] || { echo "Kein Paket gebaut." >&2; exit 1; }

# 2) repo dir
mkdir -p "$REPODIR"
cp -f "$PKG" "$REPODIR/"

# 3) repo-add
say "Aktualisiere Repo-Datenbank"
if [ "$SIGN" = 1 ]; then
    repo-add --sign -R "$REPODIR/$DBNAME.db.tar.zst" "$REPODIR/$(basename "$PKG")"
else
    repo-add -R "$REPODIR/$DBNAME.db.tar.zst" "$REPODIR/$(basename "$PKG")"
fi

cat <<EOF

$(say "Fertig")
Repo:   $REPODIR
Paket:  $(basename "$PKG")

pacman.conf-Eintrag (Beispiel, lokal):

  [lumen]
  SigLevel = Optional TrustAll
  Server = file://$REPODIR

Dann:
  sudo pacman -Sy
  sudo pacman -S lumen

Hinweis: Für eine echte Distro-Integration muss $REPODIR auf einem
Server/WebDAV liegen und die URL entsprechend gesetzt werden.
EOF
