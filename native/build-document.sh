#!/usr/bin/env bash
# Build Lumen's document reader from the frozen sources in native/document-core/vendor.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)/document-core"
target="$1"
mkdir -p "$(dirname "$target")"
# CARGO_TARGET_DIR, when set, keeps the build cache; otherwise the build uses a folder of its own.
build="${CARGO_TARGET_DIR:-}"
if [ -z "$build" ]; then
    build="$(mktemp -d "$(dirname "$target")/.lumen-document-build-XXXXXX")"
    trap 'rm -rf "$build"' EXIT
fi
(cd "$root" && cargo build --release --locked --offline --target-dir "$build" --bin lumen-document)
install -m 0755 "$build/release/lumen-document" "$target"
