#!/usr/bin/env bash
# Explicit per-user laboratory installation; excluded from production installer.
set -euo pipefail
cd "$(dirname "$0")"
python3 ../vault-core/check-licenses.py
./build.sh
prefix="${XDG_DATA_HOME:-$HOME/.local/share}/lumen/vault-lab"
umask 077
mkdir -p "$prefix/bin" "$prefix/share"
for binary in lumen-vault-lab lumen-vault-lab-broker; do
    install -m0755 "build/$binary" "$prefix/bin/$binary.next"
    mv -f "$prefix/bin/$binary.next" "$prefix/bin/$binary"
done
cp ../../LICENSE ../../THIRD_PARTY_NOTICES.md LICENSES.md README.md WEB-LOGIN.md SSH.md HTTP-ACCESS.md SESSION-UNLOCK.md "$prefix/share/"
cp -R licenses "$prefix/share/"
mkdir -p "$prefix/share/rust-dependencies"
cp -R ../vault-core/licenses/. "$prefix/share/rust-dependencies/"
# Exact rebuildable Lumen source; never archives local vault data or build outputs.
(cd ../.. && {
    git ls-files -z -- LICENSE THIRD_PARTY_NOTICES.md LICENSE-PLAN.md PUBLISHING.md native/vault-core native/vault-ui opencode-skill files install.sh bin/lumen-setup bin/lumen-vault bin/lumen-python bin/lumen_mcp.py
    # Include new native source files in an uncommitted development build too.
    git ls-files -z --others --exclude-standard -- 'native/vault-ui/*.cpp' 'native/vault-ui/*.h' 'native/vault-ui/*.js' 'native/vault-ui/*.qrc' 'native/vault-ui/*.md' 'native/vault-ui/*.html' 'native/vault-ui/*.css' 'native/vault-ui/*.mjs' 'native/vault-ui/licenses/libssh/*.txt' 'opencode-skill/lumen-service-access/SKILL.md'
} | sort -zu | tar --null -T - -czf "$prefix/share/lumen-vault-source.tar.gz")
printf 'Laboratory installed. Start with lumen-vault --lab. Synthetic credentials only.\n'
{
    git rev-parse HEAD
    (cd ../vault-core && rustc --version)
    pkg-config --modversion Qt6Widgets Qt6DBus Qt6Network Qt6WebEngineWidgets libssh
    sha256sum "$prefix/bin/"*
} > "$prefix/share/build-info.txt"
