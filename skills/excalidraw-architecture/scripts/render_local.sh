#!/bin/bash
# Render a .excalidraw scene to a full-canvas PNG with the LOCAL Excalidraw (npm package, no hosted site).
#
# usage: render_local.sh <scene.excalidraw> <out.png> [scale=2] [y0 y1]
#
# First run installs the npm package and bundles it (needs network once); later runs are offline.
# The local server stays up between calls on 127.0.0.1:${EXCALIDRAW_LOCAL_PORT:-7331}.
# y0 y1 export only the elements whose centre lies in that canvas band — one chapter of a pack.
set -euo pipefail
SCENE="$(realpath "$1")"; OUT="$(realpath -m "$2")"; SCALE="${3:-2}"; Y0="${4:-}"; Y1="${5:-}"
REGION="null"; [ -n "$Y0" ] && REGION="[$Y0, $Y1]"
HERE="$(cd "$(dirname "$0")" && pwd)/local_excalidraw"
PORT="${EXCALIDRAW_LOCAL_PORT:-7331}"
B="${AGENT_BROWSER:-npx agent-browser@0.21.4} --session ${EXCALIDRAW_SESSION:-render-local}"

if [ ! -f "$HERE/dist/bundle.js" ]; then
  echo "building local excalidraw (first run)…" >&2
  (cd "$HERE" && npm install --no-audit --no-fund --loglevel=error && npm run build) >&2
fi
if ! curl -sf "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  # setsid + full redirection: otherwise the server inherits the caller's pipe and the caller never sees EOF
  (cd "$HERE" && setsid nohup python3 serve.py >/tmp/excalidraw-local-$PORT.log 2>&1 </dev/null &)
  for _ in $(seq 1 20); do curl -sf "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break; sleep 0.5; done
fi

$B set viewport 1800 1100 >/dev/null
$B open "http://127.0.0.1:$PORT/?scene=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$SCENE")" >/dev/null
for _ in $(seq 1 40); do
  READY=$($B eval "window.__sceneReady ? 'yes' : (window.__sceneError || 'no')" 2>/dev/null | tr -d '"')
  [ "$READY" = "yes" ] && break
  case "$READY" in *error*|*failed*) echo "scene error: $READY" >&2; exit 2;; esac
  sleep 0.5
done
[ "$READY" = "yes" ] || { echo "renderer did not become ready" >&2; exit 2; }
RESULT=$($B eval "window.exportPng('$OUT', $SCALE, $REGION)")
echo "export: $RESULT"
[ -s "$OUT" ] && echo "PNG $OUT ($(stat -c %s "$OUT") bytes)"
