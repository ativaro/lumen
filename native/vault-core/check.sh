#!/usr/bin/env bash
# Requires Rust 1.89.0, rustfmt, clippy, keepassxc-cli and cargo-audit.
set -euo pipefail
cd "$(dirname "$0")"
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --release
cargo audit --file Cargo.lock
