#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
# pkg-config emits compiler flags, never user-provided paths or shell code.
read -r -a flags <<< "$(pkg-config --cflags --libs Qt6Core Qt6DBus)"
g++ -std=c++17 -O2 -fPIC "$root/window-capture.cpp" "${flags[@]}" -o "$1"
