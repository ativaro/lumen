#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
target="$1"
mkdir -p "$(dirname "$target")"
build="$(mktemp -d "$(dirname "$target")/.lumen-topbar-build-XXXXXX")"
trap 'rm -rf "$build"' EXIT
cmake -S "$root/topbar" -B "$build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build "$build" --target lumen-topbar --parallel 2
install -m 0755 "$build/lumen-topbar" "$target"
