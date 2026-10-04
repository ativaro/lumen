#!/usr/bin/env bash
# Real KWin/Xwayland/Plasma clipboard integration, isolated from the user's session.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
testroot="$(mktemp -d /tmp/lumen-vault-kde-test-XXXXXX)"
trap 'rm -rf -- "$testroot"' EXIT
mkdir -m700 "$testroot/runtime" "$testroot/config" "$testroot/data" "$testroot/cache"
cat > "$testroot/session" <<'SESSION'
#!/usr/bin/env bash
set -euo pipefail
export QT_QPA_PLATFORM=xcb
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
QT_QPA_PLATFORM=wayland plasmashell --no-respawn >"$LUMEN_TEST_ROOT/plasma.log" 2>&1 &
plasma_pid=$!
trap 'kill "$plasma_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
    if qdbus6 org.kde.klipper /klipper org.kde.klipper.klipper.getClipboardHistoryMenu >/dev/null 2>&1; then break; fi
    sleep 0.25
done
LUMEN_PRIVATE_KDE_TEST=1 "$LUMEN_TEST_BINARY" -o "$LUMEN_TEST_ROOT/result.txt",txt
SESSION
chmod +x "$testroot/session"
set +e
env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY HOME="$testroot" XDG_RUNTIME_DIR="$testroot/runtime" XDG_CONFIG_HOME="$testroot/config" XDG_DATA_HOME="$testroot/data" XDG_CACHE_HOME="$testroot/cache" LUMEN_TEST_ROOT="$testroot" LUMEN_TEST_BINARY="$here/build/vault-ui-test" QT_QPA_PLATFORM=offscreen KWIN_COMPOSE=Q XDG_CURRENT_DESKTOP=KDE timeout 90 dbus-run-session -- kwin_wayland --virtual --xwayland --no-lockscreen --no-global-shortcuts --no-kactivities --exit-with-session "$testroot/session" >"$testroot/kwin.log" 2>&1
result=$?
set -e
if [[ -f "$testroot/result.txt" ]]; then cat "$testroot/result.txt"; else tail -25 "$testroot/kwin.log"; fi
if ! grep -Eq "Totals:.* 0 failed,.* 0 skipped," "$testroot/result.txt" 2>/dev/null; then result=1; fi
if [[ "$result" != 0 ]]; then tail -15 "$testroot/plasma.log" 2>/dev/null || true; fi
exit "$result"
