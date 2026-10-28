# The architecture pack

A numbered, top-down document on one canvas. Readers scroll from the cover to the data model the
way they would read a design doc. Use this shape whenever the request is "design this before we
build it", "system design", "how are we going to build X", or a review deck for a senior.

## Cover (y < 0, above chapter 01)

- Eyebrow (who × who), title, one-paragraph summary, version line (`v0.x · date · owner · source doc`).
- **Roadmap**: a horizontal timeline of 5–6 phases, each a card with status chip
  DONE / IN PROGRESS / NEXT / LATER. Status colours: green, orange, blue, grey.
- **Contents**: one row per chapter, `NN  Title  one-line summary`.

## Chapters (each starts with `chapter("NN", "label", y - 44)` then a 36 px title and an 18 px subtitle)

| NN | Title | What belongs in it |
|---|---|---|
| 01 | Today | The current system as built. Columns = actors/systems left→right, numbered steps inside the system we own, real file paths in small grey text. |
| 02 | Target | The new flow as one round trip, same column language as 01. Colour legend: new / exists / outside company. |
| 03 | System design | Apps/modules per deployable unit, the tables or models (fields in small text), the sync contract between units, time budget, failure table. |
| 04 | Under load | Workers, caches, queues, isolation rules, capacity math in a note. Platform constraints stated as verified facts. |
| 05 | Data model | ER cards (`er_card`) with field types, link arrows labelled with the field name, the join key between systems, status lifecycles as chained cards. |
| 06 | Control panel / UI | Lo-fi wireframes (browser `frame` + lofi sidebar + ux widgets + dash charts), one per screen, plus sticky notes for stack, data, realtime, roles. |

Drop chapters that do not apply; never pad. A single diagram request gets no cover and no chapter
pills.

## Separators

A dashed grey line 60 px above each chapter title. Chapter pill at `title_y - 44`.

## Vertical rhythm used in the reference pack

```
COVER_TOP = -960 … -160
01  y = 0        today
02  TARGET_TOP = support_band_bottom + 330
03  DESIGN_TOP = questions_band_bottom + 290
04  LOAD_TOP   = failures_band_bottom + 320
05  DATA_TOP   = load_zone_bottom + 120
06  WF_TOP     = lifecycle_bottom + 440
```

Compute each top from the previous section's real bottom; never hard-code and hope.
