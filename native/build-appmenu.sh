#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
target="$1"
mkdir -p "$(dirname "$target")"
build="$(mktemp -d "$(dirname "$target")/.lumen-appmenu-build-XXXXXX")"
trap 'rm -rf "$build"' EXIT
cmake -S "$root/appmenu" -B "$build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build" --parallel 2
install -m 0755 "$build/org.lumen.appmenu.so" "$target"
