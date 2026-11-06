#!/bin/sh
set -eu
umask 077
base=${1:?Usage: install.sh /absolute/private/lumen-browser}
case "$base" in /*) ;; *) echo 'Use an absolute directory.' >&2; exit 2;; esac
[ ! -e "$base" ] || { echo 'Destination already exists; choose a new directory.' >&2; exit 2; }
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
mkdir -m 700 -- "$base"
cp -- "$source_dir/package.json" "$source_dir/package-lock.json" "$base/"
cd -- "$base"
npm ci --ignore-scripts --no-audit --no-fund
PLAYWRIGHT_BROWSERS_PATH="$base/browsers" ./node_modules/.bin/playwright install chromium
ln -s "$(command -v node)" "$base/node"
cp -- "$source_dir/start.sh" "$base/start.sh"
chmod 700 "$base/start.sh"
printf 'Browser starter: %s/start.sh\n' "$base"
