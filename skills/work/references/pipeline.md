# Pipeline rules

The planner, the approval agent and the orchestrator follow these rules. They come from real runs of this pipeline; each rule names the failure it prevents.

## Plan check

The owner sees the plan only after it passes these checks (the approval agent runs them, with up to 2 revisions):

- **Every sentence of the request maps to a ticket or to "out of scope".** The plan shows the mapping as a table. Without it, planners drop sentences such as "walk page by page", and the owner has to add them at H1.
- **At most 4 open questions, each with a proposed default.** The owner can then answer with "Approve" alone.
- **The test contract is fixed in the plan.** For UI: the exact hooks the tests use (for example `data-test="<key>"` on each target) and which component gets each one. For an API or CLI: the exact calls and outputs. When tests guess locators, most fix rounds are spent repairing the tests, not the feature.
- **Cross-page state and role-gated steps are listed.** A feature that navigates gets tests for state that crosses pages: resume, Back, reload, Esc on a later page. A step that only some roles see gets a test that it is skipped for the others.
- **Tickets that share a file depend on each other**, and test tickets come before implementation tickets.
- **The risk tier fits.** Shared layout, auth, session, payment and data-migration code is at least medium.

## Owner gates

- **H1 (plan):** "Approve", "Approve with changes: <text>" (one re-plan that applies the text, then build, with no second H1), or "Stop".
- **H2 (evidence):** "Ship", "Fix then ship: <themes>", or "Stop". "Fix then ship" is a conditional approval: one extra fix round on those themes, even past the budget, because the owner chose to go over it. Then the gate and the full end-to-end suite run again. If both are green, ship with no second ask. Otherwise stop and report again.
- A push is outward-facing: ask for it separately, even after "Ship".

## Fix rounds

Two separate budgets, so a problem QA finds does not always land on the owner:
- **Build/verify: at most 2 rounds.** Failing tests, a red gate and the verifier's findings share it.
- **QA: at most 1 round.** QA blocker and major findings, plus unexpected or broken UI shots. The gate runs again after it.

When a budget runs out, the run stops and asks. It never loops silently.

## Test rules

- **Test accounts come from a script**, never by hand (the profile's `app.login` and `app.fixtures`). Passwords live only in gitignored files.
- **The red run uses no retries and a short timeout (about 3 s).** It only has to show that every case fails for the right reason. With the default timeout, each missing element waits it out, and a red run can take half an hour.
- **A browser that did not run is reported as NOT RUN**, never left out of the table.
- **A test that fails once and then passes is a flake.** Repeat it 20 times. If all 20 pass, name it in the evidence. If any fails, it is a failure.
- **Parallel end-to-end tests need one account set per worker.** With one set, run with one worker.
- **One checkout, not a worktree per ticket,** when the local app serves the checkout (bind mounts, a dev server). A ticket in another worktree is not what the app serves.
- **A fix never weakens an assertion, widens a timeout or deletes a test** to go green.

## Agent QA rules

- **Fixture lifecycle.** QA seeds what it needs before it starts and removes it afterwards. It leaves nothing in the repo.
- **QA changes only its own role's state.** Never other users or global settings.
- **Output:** `.agent/qa/<role>.json`, one entry per finding with `id`, `severity` (blocker / major / minor / nit), `title`, `steps`, `expected`, `actual`, `url`, `screenshot` and `existing_bug`.
- **Bugs that exist without the feature are labelled "existing bug".** QA proves it by repeating the steps with the feature off. They do not block the ship.

## UI before / after

Any feature that changes what a user sees gets a screenshot of each affected page **before** and **after** the change. An agent reviews every pair that differs, and the owner sees the pairs on the run board at H2.

**When.** Whenever a ticket touches UI files (templates, components, styles, copy). The plan then sets `ui: true`, writes `.agent/ui/pages.json` (pages, roles, viewports, themes; format at the top of `scripts/ui-snap/spec.ts`), and lists the expected visible changes, one line per page.

| Step | When | Writes |
|---|---|---|
| Before | After tests first, before Implement: only test files have changed, so the pages show the base code. | `before/<id>.png`, `run.json` (commit, dirty count) |
| After | After the last fix round, and again after any later round that touched UI files. | `after/`, `diff/` (changed pixels in red), `marked/` (the after image with a red box around each changed area), `shots.json` |
| UI review | Right after the After step (Sonnet; Opus at high risk) | `review.json` |

Shot id: `<page>--<role>--<viewport>--<theme>`. Status in `shots.json`: `unchanged` (fewer than `min_pixels` differ), `changed`, `new` (no before), `removed` (no after). The final URL path is recorded for both captures, so a redirect shows up.

The UI review writes `{"verdict": "PASS|CHANGES", "summary": "...", "shots": {"<id>": {"verdict": "expected|unexpected|broken", "note": "..."}}}`:
- `expected`: the change is in the plan;
- `unexpected`: a change the plan did not ask for;
- `broken`: overlap, clipping, sideways scroll, unreadable text, an empty state where data belongs, wrong data for the role.

PASS only when nothing is unexpected or broken. Those count as QA findings, so they use the QA round. A new After capture deletes `review.json`, so a stale review is never shown against new screenshots. A `ui: true` run does not ship without a `review.json` newer than `shots.json`, and an `unexpected` shot ships only when the owner accepts it.

**Stability.** Animations off and reduced motion; wait for network idle, fonts and a 400 ms settle; `mask` paints over dynamic text; `hide` makes overlays invisible; a per-channel difference of 24 or less counts as equal. Two captures of the same code should differ by 0 pixels. If they do not, add masks before you trust any diff.
