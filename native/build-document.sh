#!/usr/bin/env bash
# Build Lumen's document reader from the frozen sources in native/document-core/vendor.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)/document-core"
target="$1"
mkdir -p "$(dirname "$target")"
build="$(mktemp -d "$(dirname "$target")/.lumen-document-build-XXXXXX")"
trap 'rm -rf "$build"' EXIT
(cd "$root" && cargo build --release --locked --offline --target-dir "$build" --bin lumen-document)
install -m 0755 "$build/release/lumen-document" "$target"
