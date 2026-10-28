# Layout rules learned the hard way

Each of these cost a render-fix-render cycle once. Apply them up front.

## Text

- Excalidraw's hand-drawn font is wide. The builder estimates width at `0.7 × fontSize` per
  character; with less, long titles get clipped by zone edges.
- `wrap(text, width_px, size)` before putting body text in a card. Cards with 3+ body lines need
  ≥ 90 px height at 15 px body; file-path lines in 13 px need another 20 px.
- Emoji do not render in the Excalidraw font (they become boxes). Use `*`, `→`, `·`, `≤`, `≫`.
- Arrow labels are centred on the arrow and sit 24 px above its top point. On a short or vertical
  arrow the label lands inside a card: pass `""` and place a `text()` yourself.

## Arrows

- `arrow(source, target, palette_key, start, end, label)` takes a **palette key** ("red", "blue"),
  not a hex colour. `text()` takes hex.
- Arrows are straight two-point lines. Anything between start and end gets crossed. Before drawing
  a cross-column arrow, check what sits in the band between the two y values and move it, or move
  the arrow's attach ratio (`point(card, "right", 0.85)`).
- Arrows out of a tall card fan better from different ratios (0.12, 0.2, 0.28 …) than from one.
- Keep stores (Redis, DB, queue) *below* the hot path, not beside it, so hot-path arrows to the
  next column travel through empty space.

## Cards and zones

- A zone's title occupies its top 50 px; the first card goes at `zone_y + 70`.
- Column cards that connect to the same target should share an x and stack with ≥ 14 px gaps.
- A badge (numbered circle) sits half outside the card at `card_x - 38, card_y - 16`.
- Compute every section's top from the real bottom of the previous one. Hard-coded gaps drift as
  content grows.

## Rendering and verifying

- Render at zoom 0.7–0.85 on a 2200-px-wide viewport to see a full chapter; the toolbar hides the
  first ~70 px, so look at the file render, not the room, for the title row.
- A blank or unstyled screenshot is almost always a slow load, not a broken scene. Re-check
  `document.querySelectorAll('canvas').length` (2 = rendered) and retry with a longer wait.
- `localStorage.excalidraw` is the *local* scene; a collaboration room keeps its scene elsewhere.
  Verify a room by screenshot/canvas count from a fresh session, never by reading localStorage.
- One shell `eval` with the whole scene fails with "Argument list too long" past ~130 KB; inject in
  40 KB chunks (render.sh does this).
- Each publish creates a **new** room URL. Tell the user which link is current; old links still
  show old content.
