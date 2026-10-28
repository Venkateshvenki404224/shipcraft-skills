#!/usr/bin/env python3
"""Download public Excalidraw libraries (alias=source pairs, or the defaults) into $EXCALIDRAW_LIBS;
`--list <alias>` prints the item names the builder's icon() accepts."""
import json
import os
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/excalidraw/excalidraw-libraries/main/libraries/{}.excalidrawlib"
CACHE = os.environ.get("EXCALIDRAW_LIBS") or os.path.expanduser("~/.cache/excalidraw-libs")

DEFAULTS = {
	"network": "dwelle/network-topology-icons",
	"aws": "stojanovic/aws-serverless-icons-v2",
	"locations": "jgodoy/network-locations",
	"people": "dhtoran/stick-people",
	"files": "xxxdeveloper/icons",
	"ux": "gabrielamacakova/basic-ux-wireframing-elements",
	"lofi": "spfr/lo-fi-wireframing-kit",
	"dash": "datavizfairy/dashboard-charts",
	"sticky": "ferminrp/post-it",
	"web": "dhaval_godwani/webpage-frames",
}


def fetch(alias, source):
	os.makedirs(CACHE, exist_ok=True)
	target = os.path.join(CACHE, alias + ".excalidrawlib")
	if os.path.exists(target):
		return target
	with urllib.request.urlopen(RAW.format(source), timeout=60) as response:
		open(target, "wb").write(response.read())
	return target


def items(alias):
	data = json.load(open(os.path.join(CACHE, alias + ".excalidrawlib")))
	return data.get("libraryItems") or [{"name": str(i), "elements": e} for i, e in enumerate(data.get("library", []))]


def main(argv):
	if argv[:1] == ["--list"]:
		for item in items(argv[1]):
			elements = item["elements"]
			width = max(e["x"] + e.get("width", 0) for e in elements) - min(e["x"] for e in elements)
			height = max(e["y"] + e.get("height", 0) for e in elements) - min(e["y"] for e in elements)
			print(f"{item.get('name') or '?'}  ({len(elements)} el, {int(width)}x{int(height)})")
		return
	wanted = dict(DEFAULTS)
	for pair in argv:
		alias, source = pair.split("=", 1)
		wanted[alias] = source
	for alias, source in wanted.items():
		try:
			print(alias, "->", fetch(alias, source))
		except Exception as error:  # noqa: BLE001 - report and keep going
			print(alias, "FAILED", error, file=sys.stderr)


if __name__ == "__main__":
	main(sys.argv[1:])
