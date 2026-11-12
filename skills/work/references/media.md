# Media layers: UI before/after screenshots, and video

Both need a running app (`app.url` in the profile). A library or CLI project skips them: `ui: false`, and QA explores through the CLI or API instead of a browser.

## UI before / after (only when the plan says `ui: true`)

The rules are in `pipeline.md`, "UI before / after". The tool is `$S/scripts/ui-snap/` (Playwright, Chromium, one worker; diffs are computed in the browser, so no image library is needed).

**Where it runs.** Playwright resolves `@playwright/test` from the config's folder, so the tool must sit where that package is installed:
- The project has Playwright (`ui_snap.dir` in the profile, e.g. `tests/e2e/ui-snap`): copy the tool there once per run, `cp $S/scripts/ui-snap/*.ts <ui_snap.dir>/`, and leave it uncommitted. The ship check refuses it if it gets staged.
- No Playwright in the project: copy the folder to `.agent/ui-snap/` and run `npm install && npx playwright install chromium` there once.

**Command** (the orchestrator builds it once and passes it to build.js as `uiSnap`, with `{phase}` for before/after):

```
cd <runner dir> && UI_SNAP={phase} UI_SNAP_BASE=<app.url> UI_SNAP_AUTH=<app.auth> UI_SNAP_REPO=<repo root> \
  [UI_SNAP_CHANNEL=chrome] npx playwright test -c ui-snap.config.ts
```

1. The planner writes `.agent/ui/pages.json` with the pages, roles, viewports, themes, `hide` and `mask` (format at the top of `spec.ts`). Mask relative times and ids. Hide overlays that open for test accounts (tours, cookie banners) unless the feature is the overlay.
2. **Before:** after the tests are written, before any product change.
3. **After:** on the final code, and again after any later fix round that touched UI files. It writes the diffs and `shots.json`, and deletes the old `review.json`.
4. **UI review agent:** for each shot that is not `unchanged`, it reads the before image, the marked image and the diff, then writes `review.json` with `expected`, `unexpected` or `broken` per shot.
5. The board shows it all under "◐ UI before / after", with side-by-side, slider and diff views.

Logging in is the project's job: `setup.ts` only checks that each role's saved login (Playwright storageState at `app.auth` with `{role}` filled in) exists, and stops with a clear message if one is missing. Run the profile's `app.login` first.

## Video (every run with an app; agent-browser 0.41+, needs ffmpeg)

Each QA agent records two takes with [agent-browser](https://www.npmjs.com/package/agent-browser), using its role's saved login:

```
agent-browser --session qa-<role> --ignore-https-errors --state <app.auth for role> open <start url>
agent-browser --session qa-<role> record start .agent/video/demo-<role>.webm --cursor --contact-sheet
  … happy path, under 90 s …
agent-browser --session qa-<role> record stop
agent-browser --session qa-<role> record start .agent/video/qa-<role>.webm --fps 10 --contact-sheet
  … exploration …
agent-browser --session qa-<role> record stop
agent-browser --session qa-<role> close
```

- Signed-out runs use no `--state`.
- Each `record stop` writes the video and `<name>.contact-sheet.png`, a strip of the distinct visual changes.
- **demo-\<role\>** is for the owner: what the feature looks like for that role. Keep it short and calm.
- **qa-\<role\>** is the evidence behind the QA findings. 10 fps keeps long sessions small.
- If `ffmpeg` or `agent-browser` is missing (`command -v agent-browser ffmpeg`), set `video: false` in the build args. QA still runs, and the evidence says "video: not recorded (reason)".
- Videos show only seeded test accounts and fake fixtures, never real customer data. `.agent/video/` is never committed.

The board shows the videos under "▶ Videos": a player per take, with its contact sheet.
