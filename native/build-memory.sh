#!/usr/bin/env bash
# Build Lumen's memory meaning search from the frozen sources in native/memory-search/vendor.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)/memory-search"
target="$1"
mkdir -p "$(dirname "$target")"
build="$(mktemp -d "$(dirname "$target")/.lumen-memory-build-XXXXXX")"
trap 'rm -rf "$build"' EXIT
(cd "$root" && cargo build --release --locked --offline --target-dir "$build" --bin lumen-memory)
install -m 0755 "$build/release/lumen-memory" "$target"
