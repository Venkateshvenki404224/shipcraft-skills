#!/bin/bash
# Start a live-collaboration room from the scene loaded in the render session (run render.sh first),
# print the room URL, then verify it from a brand-new browser session.
#
# usage: publish_room.sh [verify-screenshot.png]
# env: EXCALIDRAW_SITE, AGENT_BROWSER, EXCALIDRAW_SESSION (see render.sh)
#
# agent-browser's daemon intermittently answers "Resource temporarily unavailable (os error 11)"
# when several sessions run at once, and a fresh page can take 30–60 s to style itself. Every browser
# step therefore retries, and verification polls for a styled page with canvases instead of
# sleeping a fixed time. A blank screenshot is a slow load, not an empty room.
set -uo pipefail
OUT="${1:-/tmp/excalidraw-room-verify.png}"
SESSION="${EXCALIDRAW_SESSION:-render}"
AB="${AGENT_BROWSER:-npx agent-browser@0.21.4}"
VERIFY="$SESSION-verify-$$"

retry() {  # retry <attempts> <command...>: re-run on failure with a short backoff
	local attempts=$1; shift
	for n in $(seq 1 "$attempts"); do
		"$@" && return 0
		sleep $((n * 2))
	done
	return 1
}
host() { $AB --session "$SESSION" "$@"; }
probe() { $AB --session "$VERIFY" "$@"; }
ref() { host snapshot -i 2>&1 | grep "$1" | grep -oE 'ref=e[0-9]+' | head -1 | cut -d= -f2; }
click_ref() { local r; r=$(ref "$1"); [ -n "$r" ] && host click "@$r" >/dev/null; }

retry 3 click_ref 'button "Share"' || { echo "no Share button — is a scene loaded? run render.sh first" >&2; exit 2; }
sleep 2
retry 3 click_ref 'button "Start session"' || { echo "could not start a session" >&2; exit 2; }
sleep 5
NAME_REF=$(ref 'textbox "Your name"'); [ -n "$NAME_REF" ] && host fill "@$NAME_REF" "Claude" >/dev/null
host press Escape >/dev/null
sleep 15   # let the collab server receive the full scene before anyone else joins
URL=$(retry 3 host get url) || { echo "could not read the room URL" >&2; exit 2; }
echo "ROOM $URL"

retry 3 probe set viewport 1600 1000 >/dev/null
retry 3 probe open "$URL" >/dev/null 2>&1
STATE=""
for _ in $(seq 1 18); do   # up to ~90 s
	STATE=$(probe eval "document.querySelectorAll('canvas').length + ':' + (document.styleSheets.length > 1)" 2>/dev/null | tr -d '"')
	[ "$STATE" = "2:true" ] && break
	sleep 5
done
echo "verify: canvases:styled = ${STATE:-no answer}"
retry 3 probe screenshot "$OUT" | tail -1
probe close >/dev/null 2>&1 || true
[ "$STATE" = "2:true" ] || { echo "room did not render in a fresh session within 90 s — re-run the check before republishing" >&2; exit 3; }
echo "host session '$SESSION' still open — close it with: $AB --session $SESSION close"
