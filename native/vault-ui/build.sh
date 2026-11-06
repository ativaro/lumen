#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
build="${LUMEN_VAULT_BUILD_DIR:-$root/build}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$root/../vault-core/target}"
(cd "$root/../vault-core" && cargo build --locked --release --bins)
cmake -S "$root" -B "$build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build" -j2
install -m0755 "$CARGO_TARGET_DIR/release/lumen-vault-lab-broker" "$build/"
ctest --test-dir "$build" --output-on-failure
