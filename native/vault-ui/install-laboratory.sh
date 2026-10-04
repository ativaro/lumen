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
cp ../../LICENSE LICENSES.md README.md "$prefix/share/"
cp -R licenses "$prefix/share/"
mkdir -p "$prefix/share/rust-dependencies"
cp -R ../vault-core/licenses/. "$prefix/share/rust-dependencies/"
# Exact rebuildable Lumen source; never archives local vault data or build outputs.
(cd ../.. && git ls-files -z -- LICENSE LICENSE-PLAN.md PUBLISHING.md native/vault-core native/vault-ui files bin/lumen-vault bin/lumen-python | tar --null -T - -czf "$prefix/share/lumen-vault-source.tar.gz")
printf 'Laboratory installed. Start with lumen-vault --lab. Synthetic credentials only.\n'
{
    git rev-parse HEAD
    (cd ../vault-core && rustc --version)
    pkg-config --modversion Qt6Widgets Qt6DBus Qt6Network
    sha256sum "$prefix/bin/"*
} > "$prefix/share/build-info.txt"
