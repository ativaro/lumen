#!/usr/bin/env bash
# Explicit per-user laboratory installation; excluded from production installer.
set -euo pipefail
cd "$(dirname "$0")"
root="$(cd ../.. && pwd)"
build="${LUMEN_VAULT_BUILD_DIR:-$root/native/vault-ui/build}"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
python3 "$root/packaging/source-identity.py" "$root" > "$stage/source.json"
epoch="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_date_epoch"])' "$stage/source.json")"
python3 ../vault-core/check-licenses.py
./build.sh
prefix="${XDG_DATA_HOME:-$HOME/.local/share}/lumen/vault-lab"
umask 077
mkdir -p "$prefix/bin" "$prefix/share"
for binary in lumen-vault-lab lumen-vault-lab-broker; do
    install -m0755 "$build/$binary" "$prefix/bin/$binary.next"
    mv -f "$prefix/bin/$binary.next" "$prefix/bin/$binary"
done
cp ../../LICENSE ../../THIRD_PARTY_NOTICES.md LICENSES.md README.md WEB-LOGIN.md SSH.md HTTP-ACCESS.md SESSION-UNLOCK.md "$prefix/share/"
cp -R licenses "$prefix/share/"
mkdir -p "$prefix/share/rust-dependencies"
cp -R ../vault-core/licenses/. "$prefix/share/rust-dependencies/"
# Rebuildable native sources also work from a release archive without .git.
tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
    --exclude=build --exclude=target --exclude=__pycache__ --exclude='*.pyc' \
    -cf "$stage/source.tar" -C "$root" LICENSE THIRD_PARTY_NOTICES.md LICENSE-PLAN.md \
    native/vault-core native/vault-ui packaging/source-identity.py
tar --append --file "$stage/source.tar" --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
    --mode=0644 -C "$stage" source.json
gzip -n -c "$stage/source.tar" > "$prefix/share/lumen-vault-source.tar.gz"
install -m0644 "$stage/source.json" "$prefix/share/source.json"
printf 'Laboratory installed. Start with lumen-vault --lab. Synthetic credentials only.\n'
{
    cat "$stage/source.json"
    (cd ../vault-core && rustc --version)
    pkg-config --modversion Qt6Widgets Qt6DBus Qt6Network Qt6WebEngineWidgets libssh
    sha256sum "$prefix/bin/"*
} > "$prefix/share/build-info.txt"
