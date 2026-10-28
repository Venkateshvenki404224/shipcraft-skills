"""Build .excalidraw scenes in code: zones, cards, arrows, badges, ER cards, wireframe frames and
icons from cached public libraries; `save(path)` writes the scene. Import with `from excalidraw_builder import *`."""
import copy
import json
import os
import random
import textwrap

random.seed(7)
elements = []
by_id = {}

FONT = 5  # Excalifont (hand-drawn)
PALETTE = {
	# key: (stroke, zone fill, card fill)
	"green": ("#2f9e44", "#ebfbee", "#d3f9d8"),
	"blue": ("#1971c2", "#e7f5ff", "#d0ebff"),
	"purple": ("#6741d9", "#f3f0ff", "#e5dbff"),
	"orange": ("#e8590c", "#fff4e6", "#ffe8cc"),
	"red": ("#e03131", "#fff5f5", "#ffffff"),
	"grey": ("#868e96", "#f8f9fa", "#ffffff"),
}
INK, MUTED, CODE = "#1e1e1e", "#495057", "#868e96"
LIB_DIR = os.environ.get("EXCALIDRAW_LIBS") or os.path.expanduser("~/.cache/excalidraw-libs")


# ── primitives ────────────────────────────────────────────────────────────────
def base(element_type, x, y, width, height, **extra):
	element = {
		"id": f"{element_type}-{len(elements)}",
		"type": element_type,
		"x": x, "y": y, "width": width, "height": height, "angle": 0,
		"strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
		"strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
		"groupIds": [], "frameId": None, "roundness": {"type": 3},
		"seed": random.randint(1, 2**31), "version": 1, "versionNonce": random.randint(1, 2**31),
		"isDeleted": False, "boundElements": [], "updated": 1, "link": None, "locked": False,
	}
	element.update(extra)
	elements.append(element)
	by_id[element["id"]] = element
	return element


def text(x, y, content, size, color=INK, align="left", width=None, group=None):
	lines = content.split("\n")
	measured = max(len(line) for line in lines) * size * 0.7
	return base(
		"text", x, y, width or measured, len(lines) * size * 1.25,
		text=content, originalText=content, fontSize=size, fontFamily=FONT, textAlign=align,
		verticalAlign="top", containerId=None, autoResize=True, lineHeight=1.25,
		strokeColor=color, roundness=None, groupIds=[group] if group else [],
	)


def wrap(content, width, size):
	return "\n".join(textwrap.wrap(content, max(10, int(width / (size * 0.55)))))


def line(x, y, width, height=0, color="#adb5bd", dashed=False, end_arrow=False):
	return base("line", x, y, width, height, points=[[0, 0], [width, height]], lastCommittedPoint=None,
		startArrowhead=None, endArrowhead="arrow" if end_arrow else None, strokeColor=color,
		strokeStyle="dashed" if dashed else "solid", roundness=None)


# ── blocks ────────────────────────────────────────────────────────────────────
def zone(x, y, width, height, title, color, dashed=False):
	stroke, fill, _ = PALETTE[color]
	base("rectangle", x, y, width, height, strokeColor=stroke, backgroundColor=fill,
		strokeStyle="dashed" if dashed else "solid", strokeWidth=1, roughness=0)
	text(x + 20, y + 14, title, 24, color=stroke)


def card(x, y, width, height, title, body="", code="", color="blue", dashed=False, art=None, art_height=56):
	"""Rounded card: 20px title, 15px grey body, 13px code line; `art=(library, item)` sits top-right."""
	stroke, _, fill = PALETTE[color]
	group = f"g{len(elements)}"
	rectangle = base("rectangle", x, y, width, height, strokeColor=stroke, backgroundColor=fill,
		strokeStyle="dashed" if dashed else "solid", groupIds=[group])
	inner = width - 28
	if art:
		art_width = icon(art[0], art[1], 0, 0, art_height, group, keep_text=False)
		for element in elements[-1::-1]:
			if not element["id"].startswith("icon-"):
				break
			element["x"] += x + width - 14 - art_width
			element["y"] += y + 14
		inner -= art_width + 12
	cursor = y + 14
	title_text = wrap(title, inner, 20)
	text(x + 14, cursor, title_text, 20, group=group)
	cursor += title_text.count("\n") * 25 + 30
	if body:
		body_text = wrap(body, inner, 15)
		text(x + 14, cursor, body_text, 15, color=MUTED, group=group)
		cursor += (body_text.count("\n") + 1) * 19 + 6
	if code:
		text(x + 14, cursor, wrap(code, inner, 13), 13, color=CODE, group=group)
	return rectangle


def badge(x, y, number, color="blue"):
	group = f"g{len(elements)}"
	stroke = PALETTE[color][0]
	base("ellipse", x, y, 36, 36, strokeColor=stroke, backgroundColor=stroke, groupIds=[group])
	text(x + 12, y + 6, str(number), 20, color="#ffffff", group=group)


def pill(x, y, label_text, color):
	stroke, _, fill = PALETTE[color]
	base("rectangle", x, y, 10 + len(label_text) * 7, 18, strokeColor=stroke, backgroundColor=fill, roughness=0,
		roundness={"type": 3})
	text(x + 5, y + 2, label_text, 11, color=stroke)


def chapter(number, label_text, y):
	"""Black numbered pill + small-caps label; place at title_y - 44 so packs read like a document."""
	group = f"g{len(elements)}"
	base("rectangle", 0, y, 54, 30, strokeColor=INK, backgroundColor=INK, groupIds=[group], roundness={"type": 3})
	text(12, y + 5, number, 16, color="#ffffff", group=group)
	text(66, y + 6, label_text.upper(), 13, color=MUTED, group=group)


def er_card(x, y, width, fields, title, color, key_fields=()):
	"""Entity card for data models: 40px header band, one 13px row per field, `*` marks key fields."""
	height = 50 + len(fields) * 20 + 16
	group = f"g{len(elements)}"
	stroke, _, fill = PALETTE[color]
	base("rectangle", x, y, width, height, strokeColor=stroke, backgroundColor="#ffffff", groupIds=[group], roughness=0)
	base("rectangle", x, y, width, 40, strokeColor=stroke, backgroundColor=fill, groupIds=[group], roughness=0)
	text(x + 12, y + 10, title, 17, group=group)
	for index, field in enumerate(fields):
		is_key = field.split(" ")[0] in key_fields
		text(x + 10, y + 52 + index * 20, ("*  " if is_key else "    ") + field, 13,
			color=INK if is_key else MUTED, group=group)
	return base("rectangle", x, y, width, height, strokeColor="transparent", backgroundColor="transparent",
		groupIds=[group], roughness=0)


def frame(x, y, width, height, url_text):
	"""Browser-window chrome for wireframes: grey title bar with three dots and a URL."""
	group = f"g{len(elements)}"
	base("rectangle", x, y, width, height, strokeColor="#495057", backgroundColor="#ffffff", roughness=0, groupIds=[group])
	base("rectangle", x, y, width, 30, strokeColor="#495057", backgroundColor="#e9ecef", roughness=0, groupIds=[group])
	for index in range(3):
		base("ellipse", x + 12 + index * 16, y + 9, 12, 12, strokeColor="#adb5bd", backgroundColor="#ced4da", groupIds=[group])
	text(x + 70, y + 7, url_text, 12, color=MUTED, group=group)


# ── arrows ────────────────────────────────────────────────────────────────────
def point(element, side, ratio=0.5):
	"""A point on a card edge: side in right/left/top/bottom, ratio 0..1 along that edge."""
	if side == "right":
		return (element["x"] + element["width"], element["y"] + element["height"] * ratio)
	if side == "left":
		return (element["x"], element["y"] + element["height"] * ratio)
	if side == "bottom":
		return (element["x"] + element["width"] * ratio, element["y"] + element["height"])
	return (element["x"] + element["width"] * ratio, element["y"])


def arrow(source, target, color, start, end, label="", dashed=False, both=False):
	"""Straight bound arrow; `color` is a PALETTE key. Label sits 24px above the top point."""
	stroke = PALETTE[color][0]
	element = base(
		"arrow", start[0], start[1], end[0] - start[0], end[1] - start[1],
		points=[[0, 0], [end[0] - start[0], end[1] - start[1]]], lastCommittedPoint=None,
		startBinding={"elementId": source["id"], "focus": 0, "gap": 6},
		endBinding={"elementId": target["id"], "focus": 0, "gap": 6},
		startArrowhead="arrow" if both else None, endArrowhead="arrow", elbowed=False,
		strokeColor=stroke, strokeStyle="dashed" if dashed else "solid", roundness={"type": 2},
	)
	source["boundElements"].append({"id": element["id"], "type": "arrow"})
	target["boundElements"].append({"id": element["id"], "type": "arrow"})
	if label:
		middle_x = (start[0] + end[0]) / 2
		text(middle_x - len(label) * 13 * 0.55 / 2, min(start[1], end[1]) - 24, label, 13, color=stroke)
	return element


def connect(source, target, color, label="", source_ratio=0.5, target_ratio=0.5, dashed=False, both=False):
	"""Arrow between two cards' facing vertical edges; picks left/right automatically."""
	if source["x"] + source["width"] <= target["x"]:
		return arrow(source, target, color, point(source, "right", source_ratio), point(target, "left", target_ratio),
			label, dashed, both)
	return arrow(source, target, color, point(source, "left", source_ratio), point(target, "right", target_ratio),
		label, dashed, both)


def chain(cards, color, gap_ratio=0.5):
	"""Vertical top→bottom arrows through a column of cards."""
	for upper, lower in zip(cards, cards[1:]):
		arrow(upper, lower, color, point(upper, "bottom", gap_ratio), point(lower, "top", gap_ratio))


# ── library icons ─────────────────────────────────────────────────────────────
_libraries = {}


def _library_item(library, name):
	if library not in _libraries:
		data = json.load(open(os.path.join(LIB_DIR, library + ".excalidrawlib")))
		items = data.get("libraryItems") or [{"name": str(i), "elements": e} for i, e in enumerate(data.get("library", []))]
		_libraries[library] = items
	try:
		return next(item for item in _libraries[library] if (item.get("name") or "") == name)
	except StopIteration:
		names = ", ".join((item.get("name") or "?") for item in _libraries[library][:40])
		raise KeyError(f"{library!r} has no item {name!r}. Items: {names}") from None


def icon(library, name, x, y, height, group=None, keep_text=True):
	"""Place a library item scaled to `height`; returns its width. keep_text=False drops sample labels."""
	source = copy.deepcopy(_library_item(library, name)["elements"])
	if not keep_text:
		source = [e for e in source if e["type"] != "text"]
		for e in source:
			e["boundElements"] = [b for b in (e.get("boundElements") or []) if b.get("type") != "text"]
	min_x = min(e["x"] for e in source)
	min_y = min(e["y"] for e in source)
	max_y = max(e["y"] + e.get("height", 0) for e in source)
	scale = height / (max_y - min_y)
	id_map = {e["id"]: f"icon-{len(elements)}-{index}" for index, e in enumerate(source)}
	group_map = {}
	for e in source:
		e["id"] = id_map[e["id"]]
		e["x"] = x + (e["x"] - min_x) * scale
		e["y"] = y + (e["y"] - min_y) * scale
		e["width"] = e.get("width", 0) * scale
		e["height"] = e.get("height", 0) * scale
		if "points" in e:
			e["points"] = [[px * scale, py * scale] for px, py in e["points"]]
		if "fontSize" in e:
			e["fontSize"] = e["fontSize"] * scale
		e["strokeWidth"] = max(1, min(e.get("strokeWidth", 1), 2))
		e["groupIds"] = [group_map.setdefault(g, f"{g}-{len(elements)}") for g in e.get("groupIds", [])] + (
			[group] if group else [])
		e["boundElements"] = [b for b in (e.get("boundElements") or []) if b["id"] in id_map]
		for bound in e["boundElements"]:
			bound["id"] = id_map[bound["id"]]
		if e.get("containerId"):
			e["containerId"] = id_map.get(e["containerId"])
		for key in ("startBinding", "endBinding"):
			if e.get(key):
				e[key] = None
		e.setdefault("frameId", None)
		e["locked"] = False
		e["isDeleted"] = False
		elements.append(e)
		by_id[e["id"]] = e
	return max(e["x"] + e["width"] for e in elements[-len(source):]) - x


# ── output ────────────────────────────────────────────────────────────────────
def bounds():
	xs = [e["x"] for e in elements] + [e["x"] + e.get("width", 0) for e in elements]
	ys = [e["y"] for e in elements] + [e["y"] + e.get("height", 0) for e in elements]
	return min(xs), min(ys), max(xs), max(ys)


def _text_box(e):
	longest = max((len(l) for l in e["text"].split("\n")), default=0)
	return e["x"], e["y"], e["x"] + longest * e["fontSize"] * 0.5, e["y"] + e["height"]


def lint():
	"""Warn about text that collides with other text or spills out of the card it starts in."""
	labels = [e for e in elements if e["type"] == "text" and e.get("text", "").strip()
		and not e["id"].startswith("icon-")]
	cards = [e for e in elements if e["type"] == "rectangle" and e.get("strokeColor") != "transparent"
		and 60 <= e.get("width", 0) <= 900 and 40 <= e.get("height", 0) <= 900]
	problems = []
	for i, a in enumerate(labels):
		ax0, ay0, ax1, ay1 = _text_box(a)
		for b in labels[i + 1:]:
			bx0, by0, bx1, by1 = _text_box(b)
			if min(ax1, bx1) - max(ax0, bx0) > 4 and min(ay1, by1) - max(ay0, by0) > 4:
				problems.append(f"text overlap: {a['text'][:30]!r} × {b['text'][:30]!r} near ({int(ax0)}, {int(ay0)})")
		home = next((c for c in cards if c["x"] <= ax0 <= c["x"] + c["width"] and c["y"] <= ay0 <= c["y"] + c["height"]), None)
		if home and (ax1 > home["x"] + home["width"] + 2 or ay1 > home["y"] + home["height"] + 2):
			problems.append(f"spills out of its card: {a['text'][:40]!r} at ({int(ax0)}, {int(ay0)})")
	return problems


def save(path):
	for problem in lint():
		print("LINT", problem)
	scene = {
		"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
		"elements": elements,
		"appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
		"files": {},
	}
	with open(path, "w") as handle:
		json.dump(scene, handle, indent=1)
	x0, y0, x1, y1 = bounds()
	print(f"{len(elements)} elements → {path}  canvas x {int(x0)}..{int(x1)}  y {int(y0)}..{int(y1)}")
