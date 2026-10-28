#!/usr/bin/env python3
"""Export one PNG per chapter of an architecture pack: bands are cut at the full-width dashed
separator lines the builder draws above each chapter; names come from the chapter pills (01, 02 …)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def bands(scene):
	elements = [e for e in scene["elements"] if not e.get("isDeleted")]
	separators = sorted(e["y"] for e in elements if e["type"] == "line" and e.get("strokeStyle") == "dashed"
		and e.get("width", 0) >= 1500)
	top = min(e["y"] for e in elements) - 20
	bottom = max(e["y"] + e.get("height", 0) for e in elements) + 20
	edges = [top] + separators + [bottom]
	pills = sorted((e["y"], e["text"]) for e in elements if e["type"] == "text" and e["text"].strip().isdigit()
		and len(e["text"].strip()) == 2 and e.get("fontSize") == 16)
	result = []
	for y0, y1 in zip(edges, edges[1:]):
		label = next((t for y, t in pills if y0 <= y <= y1), None)
		result.append((label or "cover", y0 + 1, y1 - 1))
	return result


def main(scene_path, out_dir, scale="2"):
	scene = json.load(open(scene_path))
	stem = os.path.splitext(os.path.basename(scene_path))[0]
	os.makedirs(out_dir, exist_ok=True)
	for label, y0, y1 in bands(scene):
		out = os.path.join(out_dir, f"{stem}-{label}.png")
		subprocess.run([os.path.join(HERE, "render_local.sh"), scene_path, out, scale, str(y0), str(y1)], check=True)
		print(label, f"{int(y0)}..{int(y1)}", "->", out)


if __name__ == "__main__":
	main(*sys.argv[1:])
