#!/usr/bin/env bash
# Build Lumen's desktop service (with native/engine, native/persona and native/sentence-encoder) from
# the frozen sources in native/service/vendor.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)/service"
target="$1"
mkdir -p "$(dirname "$target")"
# CARGO_TARGET_DIR, when set, keeps the build cache; otherwise the build uses a folder of its own.
build="${CARGO_TARGET_DIR:-}"
if [ -z "$build" ]; then
    build="$(mktemp -d "$(dirname "$target")/.lumen-service-build-XXXXXX")"
    trap 'rm -rf "$build"' EXIT
fi
(cd "$root" && cargo build --release --locked --offline --target-dir "$build" --bin lumen-service)
install -m 0755 "$build/release/lumen-service" "$target"
