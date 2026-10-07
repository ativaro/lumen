#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
(cd ../vault-core && cargo build --locked --release --bins)
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
install -m0755 ../vault-core/target/release/lumen-vault-lab-broker build/
ctest --test-dir build --output-on-failure
