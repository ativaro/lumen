#!/bin/sh
set -eu
umask 077
export PLAYWRIGHT_BROWSERS_PATH
base=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
# A private temporary working directory also bounds files exposed by MCP roots.
PLAYWRIGHT_BROWSERS_PATH="$base/browsers"
session=$(mktemp -d "${LUMEN_BROWSER_SESSIONS:-$base}/session.XXXXXXXX")
node=${LUMEN_BROWSER_NODE:-$base/node}
browser=$("$node" -e 'console.log(require(process.argv[1]).chromium.executablePath())' "$base/node_modules/playwright")
child=''
cleanup() {
  if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
  rm -rf -- "$session"
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
cd -- "$session"
"$node" "$base/node_modules/@playwright/mcp/cli.js" --executable-path "$browser" --headless --isolated --sandbox --caps vision --no-webmcp --viewport-size 1280x800 --ignore-roots --output-dir "$session" --output-max-size 16777216 --redact-url-params access_token,token,code <&0 &
child=$!
wait "$child"
