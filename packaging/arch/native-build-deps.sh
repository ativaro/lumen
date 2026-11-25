# Sourced by both user-install entry points. A working user-managed Rust
# toolchain can build the vendored crates without installing Arch's rust package.
native_packages=(gcc pkgconf make cmake qt6-base qt6-declarative layer-shell-qt libdbusmenu-glib)
if ! cargo --version >/dev/null 2>&1 || ! rustc --version >/dev/null 2>&1; then
    native_packages+=(rust)
fi
