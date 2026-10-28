---
name: excalidraw-architecture
description: Design architecture before building it, as Excalidraw diagrams generated from code, rendered locally with the Excalidraw npm package to PNG, attached to the plan.md or design doc, and reviewed until every review lens approves. Use this whenever a plan, feature request, PRD or "how are we going to build X" needs a picture — current integrations, a target flow, a sync contract, data models and their links, a UI wireframe, a roadmap, or a full numbered "architecture pack" — and whenever the user says draw, diagram, sketch, map, wireframe, architect, Excalidraw, draw.io or Figma-style design doc, or wants to "see it" rather than read it. Also use it to revise a diagram made earlier with this skill or to share one as a live Excalidraw room.
---

# Excalidraw architecture diagrams

A design that exists only as prose gets agreed by nobody. This skill makes the picture, puts it in
the plan, and has reviewers argue with it while it is still cheap to change. Scenes are generated
from a small Python builder (hand-placing hundreds of elements is slow and inconsistent), rendered
by a local copy of Excalidraw (text widths, arrow crossings and library quirks are only visible once
drawn), and attached as PNG + source to the document that will drive implementation.

## 1. Decide the shape

- **One diagram** — a flow, an integration map, one ER view: title + subtitle, 2–5 colour zones
  left→right, cards carrying real file paths in grey, numbered badges on the steps we own.
- **Architecture pack** — the user wants to design before building, or present to a senior: a
  cover with roadmap and contents, then numbered chapters 01 Today → 02 Target → 03 System design
  → 04 Under load → 05 Data model → 06 UI. `references/architecture-pack.md` says what each holds.
  Include only chapters the subject needs.

Ground every box in the code first: grep the modules, read the hooks, name the files. The small
grey file paths are what make reviewers trust the picture.

## 2. Build the scene

`S` below is this skill's `scripts/` folder (the directory this SKILL.md was loaded from, plus
`/scripts`).

```bash
python3 $S/fetch_libraries.py            # once per machine: public icon/wireframe libraries
```

Write the builder in `docs/architecture/_build/<name>.py` (next to the output, so the diagram stays
editable — edit the script, never the JSON) with `from excalidraw_builder import *`
(`references/example-builder.md`):

| Need | Call |
|---|---|
| swimlane / column | `zone(x, y, w, h, title, colour)` |
| box with title / body / file path | `card(x, y, w, h, title, body, code, colour, art=(lib, item))` |
| numbered step | `badge(x, y, n)` half outside the card's top-left |
| flow between cards | `connect(a, b, colour, label)` or `arrow(a, b, colour, point(a,"bottom"), point(b,"top"))` |
| column of steps | `chain([c1, c2, c3], colour)` |
| data model | `er_card(x, y, w, fields, title, colour, key_fields)` |
| document chapters | `chapter("03", "System design", title_y - 44)` |
| wireframe | `frame(...)` + `icon("lofi","18",…,keep_text=False)` + `icon("ux",…)` + `icon("dash",…)` |
| status / state | `pill(x, y, "Live", "green")` |

Colour language, kept consistent across chapters: green = data coming in / the customer's side,
blue = exists in our system, red = new to build, purple = outside company, orange = third parties,
decisions, open questions, grey = supporting. Icons come from public libraries
(`references/libraries.md`); pass `keep_text=False` on wireframe and chart items so their sample
labels do not fight yours.

`save(path)` writes `docs/architecture/<name>.excalidraw`, prints element count + bounds, and
prints `LINT` lines for text that overlaps other text or spills out of its card. Fix every LINT
line before rendering; they are the collisions a reviewer would otherwise spot in the PNG.

## 3. Render locally, look, fix

```bash
$S/render_local.sh docs/architecture/<name>.excalidraw docs/architecture/<name>.png 2     # full canvas
$S/export_chapters.py docs/architecture/<name>.excalidraw docs/architecture 2           # one PNG per chapter
```

`export_chapters.py` cuts at the dashed separators above each chapter and names files by the
chapter pills (`<name>-01.png`, `<name>-02.png` …). Re-run both commands after the last change so
no PNG in the plan is stale.

The first run installs `@excalidraw/excalidraw` from npm and bundles it (network once); after
that it is offline on `127.0.0.1:7331` (`EXCALIDRAW_LOCAL_PORT` to change it). The scripts drive
the page with `agent-browser` (`AGENT_BROWSER` to override). Open the PNG with Read and inspect it.
The recurring faults and their fixes are in `references/layout-rules.md`: arrows through cards,
clipped titles, labels inside cards, emoji boxes. Fix the builder, rebuild, re-render — two or
three cycles is normal. Set `EXCALIDRAW_SESSION=<name>` when several diagram jobs may run at once.

## 4. Attach to the plan

Put the PNG(s) and the `.excalidraw` under `docs/architecture/`, and in the plan.md / design doc:

```markdown
## Architecture
![Target architecture](docs/architecture/<name>-02-target.png)
Source: docs/architecture/<name>.excalidraw · builder: docs/architecture/_build/<name>.py
```

One PNG per chapter the plan refers to; the full-canvas export is for the appendix.

## 5. Review before anyone builds

An explanatory diagram of something that already exists needs no review. When the diagram is part
of a plan or feature request, run the review loop in `references/architecture-review.md`. It runs
in this session, with TypeSafe Jev as the checker when `TYPESAFE_API_KEY` is set. Do not spawn
reviewer agents.

1. Check every code claim in the design yourself: file paths, lines, functions and framework
   behaviour.
2. Write yes/no questions for three lenses: seams & reuse, failure & scale, data & privacy. Use the
   standing checklist, the design's own promises, and every earlier finding.
3. Run `scripts/jev_review.py`. Fix every fail, and check every unsure point in the code yourself.
4. Repeat until all three lenses approve.

Record the verdict table and the list of checked code claims in the plan. A plan without three
approvals is not ready to implement. Never send personal or customer data to an external reviewer.
Spawn reviewer agents only when the user asks for a deep code review.

## 6. Share (optional)

If the user wants a link for people outside the repo, `scripts/render.sh` + `scripts/publish_room.sh`
load the scene into a hosted Excalidraw (`$EXCALIDRAW_SITE`, default excalidraw.com, or a
self-hosted copy) and start a live room. Every publish is a new URL; collaboration runs through
Excalidraw's public servers — fine for architecture, never for personal or customer data.

## 7. Report

Room link if any, repo paths, the review table, the code claims you checked, and a short reading
guide. Say what you could not verify. Files stay uncommitted unless asked.
