#!/bin/bash
# Render a viewport of a .excalidraw scene inside a self-hosted Excalidraw and screenshot it.
#
# usage: render.sh <scene.excalidraw> <scrollY> <zoom> <out.png> [width height]
#   scrollY: negative numbers scroll DOWN the canvas (Excalidraw convention); 0 = canvas origin at top
#   zoom:    0.5–1.0 is readable for review
#
# env: EXCALIDRAW_SITE (default https://excalidraw.com), AGENT_BROWSER (default "npx agent-browser@0.21.4")
# The scene is injected into localStorage in 40 KB chunks: a single eval with the whole JSON hits
# "Argument list too long". The browser session "render" is kept open so publish_room.sh can reuse it.
set -euo pipefail
SCENE="$1"; SCROLL_Y="$2"; ZOOM="$3"; OUT="$4"; W="${5:-2200}"; H="${6:-1400}"
SITE="${EXCALIDRAW_SITE:-https://excalidraw.com}"
B="${AGENT_BROWSER:-npx agent-browser@0.21.4} --session ${EXCALIDRAW_SESSION:-render}"
WORK="$(mktemp -d)"

$B set viewport "$W" "$H" >/dev/null
$B open "$SITE" >/dev/null 2>&1
python3 - "$SCENE" "$WORK" <<'EOF'
import json, sys
scene, work = sys.argv[1], sys.argv[2]
elements = json.load(open(scene))["elements"]
text = json.dumps(elements, separators=(",", ":"))
for index in range(0, len(text), 40000):
    open(f"{work}/chunk{index // 40000:03d}.txt", "w").write(text[index:index + 40000])
EOF
$B eval "window.__scene='';'reset'" >/dev/null
for chunk in "$WORK"/chunk*.txt; do
  $B eval "window.__scene+=$(python3 -c "import json,sys;print(json.dumps(open(sys.argv[1]).read()))" "$chunk");'ok'" >/dev/null
done
$B eval "localStorage.setItem('excalidraw', window.__scene);localStorage.setItem('excalidraw-state', JSON.stringify({scrollX:30,scrollY:$SCROLL_Y,zoom:{value:$ZOOM}}));'ok'" >/dev/null
rm -rf "$WORK"
$B open "$SITE" >/dev/null 2>&1
$B wait 4000 >/dev/null
CANVASES=$($B eval "document.querySelectorAll('canvas').length")
if [ "$CANVASES" = '"0"' ] || [ "$CANVASES" = "0" ]; then
  echo "page did not render (0 canvases) — site hiccup, run again" >&2
  exit 2
fi
$B screenshot "$OUT" | tail -1
