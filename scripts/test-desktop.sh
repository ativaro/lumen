#!/usr/bin/env bash
# Lumen's desktop test gate. Builds the native programs the tests use, runs every test file of files/
# and tests/ on its own in a throwaway profile (HOME, XDG folders, runtime folder, TMPDIR and a private
# session bus), fails a file that leaves a process behind, writes a summary and exits non-zero on any
# failure. PUBLISHING.md ("Verify locally") lists what a CI image needs.
#
# usage: scripts/test-desktop.sh [-j JOBS] [TEST_FILE...]
#   TEST_FILE           files/test_x.py or tests/test_y.py; default: all of them
#   -j JOBS             test files run at the same time (default: LUMEN_TEST_JOBS or 4)
# environment (all optional):
#   LUMEN_TEST_PYTHON   interpreter with PySide6 (QtWidgets, QtQuick, QtWebEngine, QtDBus, QtSvg) and
#                       pytest 9 (default: python3); PYTHONPATH is passed through
#   LUMEN_BIN_DIR       folder holding lumen-service and lumen-document; when unset both are built
#                       into LUMEN_TEST_OUT/bin with native/build-*.sh (cargo, offline)
#   CARGO_TARGET_DIR    cargo cache for those builds (default: a fresh temporary folder)
#   LUMEN_TEST_OUT      binaries, logs and summary.txt (default: <repo>/.test-desktop)
#   LUMEN_TEST_TMP      parent of the throwaway profiles (default: TMPDIR or /tmp); keep it short,
#                       socket paths are limited to 108 bytes
#   LUMEN_TEST_TIMEOUT  seconds per test file (default: 300)
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
self=$repo/scripts/$(basename "$0")

if [ "${1:-}" = --one ]; then
    # One test file in a profile of its own; prints its result line.
    file=$2
    name=${file//\//-}; log=$LUMEN_TEST_OUT/logs/${name%.py}.log
    h=$(mktemp -d "$LUMEN_TEST_TMP/lt.XXXXXX")
    mkdir -p "$h"/{home,config,data,state,cache,run,lumen,tools,fixtures,host,tmp}
    chmod 700 "$h/run"
    case $file in
        tests/*) dir=$repo; target=$file; path=$repo/files${PYTHONPATH:+:$PYTHONPATH};;
        *) dir=$repo/files; target=${file#files/}; path=${PYTHONPATH:-};;
    esac
    start=$(date +%s)
    (cd "$dir" && env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$h/home" USER="${USER:-lumen}" \
        XDG_CONFIG_HOME="$h/config" XDG_DATA_HOME="$h/data" XDG_STATE_HOME="$h/state" \
        XDG_CACHE_HOME="$h/cache" XDG_RUNTIME_DIR="$h/run" TMPDIR="$h/tmp" \
        LUMEN_DATA="$h/lumen" LUMEN_TOOLS_DATA="$h/tools" LUMEN_IMPORT_FIXTURES="$h/fixtures" \
        LUMEN_HOST_TEST_ROOT="$h/host" LUMEN_BIN_DIR="$LUMEN_BIN_DIR" LUMEN_PYTHON="$LUMEN_TEST_PYTHON" \
        LUMEN_LANGUAGE=de LANG=de_DE.UTF-8 PYTHONPATH="$path" PYTHONDONTWRITEBYTECODE=1 \
        QT_QPA_PLATFORM="offscreen:configfile=$repo/tests/offscreen-screen.json" \
        dbus-run-session --config-file="$repo/tests/session-bus.conf" -- timeout -k 5 "$LUMEN_TEST_TIMEOUT" nice -n 5 "$LUMEN_TEST_PYTHON" -m pytest \
        -p no:cacheprovider --basetemp="$h/pytest" -q --show-capture=no --tb=short -rfEs "$target") \
        >"$log" 2>&1
    code=$?
    seconds=$(( $(date +%s) - start ))
    # The session ends: its runtime folder goes, and the Lumen service started in it ends by itself.
    rm -rf "$h/run"
    leaks=
    for _ in $(seq 20); do
        leaks=$( { grep -lsZzF "=$h/" /proc/[0-9]*/environ | tr '\0' '\n' | cut -d/ -f3
                   find /proc/[0-9]*/cwd -maxdepth 0 -lname "$h/*" 2>/dev/null | cut -d/ -f3; } | sort -un)
        [ -z "$leaks" ] && break
        sleep 0.5
    done
    status=pass
    # 5: nothing to collect (a helper module, or a module skipped as a whole).
    [ $code -ne 0 ] && [ $code -ne 5 ] && status=fail
    [ $code -eq 124 ] || [ $code -eq 137 ] && status=timeout
    for pid in $leaks; do
        echo "LEAK $file pid $pid: $(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" >> "$log"
        kill -KILL "$pid" 2>/dev/null
        status=leak
    done
    rm -rf "$h"
    echo "$status ${seconds}s $file"
    exit 0
fi

jobs=${LUMEN_TEST_JOBS:-4}
if [ "${1:-}" = -j ]; then jobs=$2; shift 2; fi
export LUMEN_TEST_PYTHON=${LUMEN_TEST_PYTHON:-python3}
export LUMEN_TEST_OUT=${LUMEN_TEST_OUT:-$repo/.test-desktop}
export LUMEN_TEST_TIMEOUT=${LUMEN_TEST_TIMEOUT:-300}
rm -rf "$LUMEN_TEST_OUT/logs"; mkdir -p "$LUMEN_TEST_OUT/logs"
export LUMEN_TEST_TMP
LUMEN_TEST_TMP=$(mktemp -d "${LUMEN_TEST_TMP:-${TMPDIR:-/tmp}}/lumen-gate.XXXXXX") || exit 2
trap 'rm -rf "$LUMEN_TEST_TMP"' EXIT
began=$(date +%s)

if [ -z "${LUMEN_BIN_DIR:-}" ]; then
    LUMEN_BIN_DIR=$LUMEN_TEST_OUT/bin
    for program in service document; do
        echo "building lumen-$program"
        nice -n 10 bash "$repo/native/build-$program.sh" "$LUMEN_BIN_DIR/lumen-$program" \
            >"$LUMEN_TEST_OUT/logs/build-$program.log" 2>&1 \
            || { tail -n 30 "$LUMEN_TEST_OUT/logs/build-$program.log"; exit 2; }
    done
fi
LUMEN_BIN_DIR=$(cd "$LUMEN_BIN_DIR" && pwd) || exit 2; export LUMEN_BIN_DIR
built=$(date +%s)

cd "$repo" || exit 2
# The largest (usually the longest) files start first.
if [ $# -gt 0 ]; then printf '%s\n' "$@"; else ls -S files/test_*.py tests/test_*.py tests/test-*.py; fi |
    xargs -P "$jobs" -I{} "$self" --one {} | tee "$LUMEN_TEST_OUT/results.txt"

summary=$LUMEN_TEST_OUT/summary.txt
{
    echo "Lumen desktop tests at $(git -C "$repo" rev-parse --short HEAD 2>/dev/null)$(git -C "$repo" diff --quiet HEAD 2>/dev/null || echo ' (modified)')"
    echo "build $((built - began))s, tests $(( $(date +%s) - built ))s, $jobs jobs"
    grep -hE '^=* ?[0-9]+ [a-z]+.* in [0-9.]+s' "$LUMEN_TEST_OUT"/logs/*-test*.log | awk '{for (i = 1; i < NF; i++) if ($(i+1) ~ /^(passed|failed|errors?|skipped)/) { k = $(i+1); sub(/[^a-z].*/, "", k); sub(/s$/, "", k); n[k] += $i } }
        END { printf "passed %d, failed %d, errors %d, skipped %d\n", n["passed"], n["failed"], n["error"], n["skipped"] }'
    echo "files: $(grep -c '^pass ' "$LUMEN_TEST_OUT/results.txt") passed, $(grep -vc '^pass ' "$LUMEN_TEST_OUT/results.txt") failed"
    grep -v '^pass ' "$LUMEN_TEST_OUT/results.txt"
    grep -h '^LEAK ' "$LUMEN_TEST_OUT"/logs/*.log
    grep -h '^\(FAILED\|ERROR\|SUBFAILED\)' "$LUMEN_TEST_OUT"/logs/*.log | sed 's/ - .*//'
    echo "skipped:"
    grep -h '^SKIPPED' "$LUMEN_TEST_OUT"/logs/*.log
} > "$summary"
cat "$summary"
! grep -qv '^pass ' "$LUMEN_TEST_OUT/results.txt"
