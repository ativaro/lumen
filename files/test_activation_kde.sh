#!/usr/bin/env bash
# Private compositor and home: never touches the user's windows or settings.
set -euo pipefail
source_files="$(cd "$(dirname "$0")" && pwd)"
testroot="$(mktemp -d /tmp/lumen-activation-kde-XXXXXX)"
trap 'rm -rf -- "$testroot"' EXIT
mkdir -m700 "$testroot/runtime" "$testroot/config" "$testroot/data" "$testroot/cache"
cat > "$testroot/session" <<'SESSION'
#!/usr/bin/env bash
set -euo pipefail
export QT_QPA_PLATFORM=wayland
export QT_QUICK_BACKEND=software
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
python3 "$LUMEN_TEST_FILES/test_lumen_activation.py" --kde >"$LUMEN_TEST_ROOT/result.txt" 2>&1
SESSION
chmod +x "$testroot/session"
result=0
env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY HOME="$testroot" XDG_RUNTIME_DIR="$testroot/runtime" \
    XDG_CONFIG_HOME="$testroot/config" XDG_DATA_HOME="$testroot/data" XDG_CACHE_HOME="$testroot/cache" \
    LUMEN_TEST_ROOT="$testroot" LUMEN_TEST_FILES="$source_files" LUMEN_PRIVATE_KDE_TEST=1 \
    QT_QPA_PLATFORM=offscreen KWIN_COMPOSE=Q XDG_CURRENT_DESKTOP=KDE \
    timeout 60 dbus-run-session -- kwin_wayland --virtual --no-lockscreen --no-global-shortcuts \
    --no-kactivities --exit-with-session "$testroot/session" >"$testroot/kwin.log" 2>&1 || result=$?
cat "$testroot/result.txt" 2>/dev/null || true
if ! rg -q LUMEN_KDE_FOCUS_OK "$testroot/result.txt"; then result=1; fi
if [[ "$result" != 0 ]]; then tail -20 "$testroot/kwin.log"; fi
exit "$result"
