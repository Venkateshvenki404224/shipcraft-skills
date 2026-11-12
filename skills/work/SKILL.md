---
name: work
description: Build a feature end to end with an agent pipeline, in any repository, and show it live on a run board. Starts from a GitHub issue number, an issue URL, or a plain-text request. It writes a run-specific workflow from its templates and runs it - research, a plan, an approval agent, the owner's approval, tests first, implementation, the gate and E2E, verification, per-role agent QA recorded on video, UI before/after screenshots when the UI changes, an evidence report, and the owner's ship decision. Every stage shows on the run board (dashboard.html; an Artifact in cloud sessions) and in a stage table. Use whenever the owner says "/work", "work on", "use the work skill", or "implement issue N". Also use it to continue a run - "/work approve", "/work ship", "/work status" - or to set a repo up for it - "/work setup".
---

# /work: the feature pipeline

You are the orchestrator. You do not write feature code yourself. You:
1. take in the request;
2. make sure the repo has a profile (`.claude/work.json`), and write one with the owner if it does not;
3. start the run board, so the owner sees every stage live;
4. write the workflow files for this run from the templates in `workflows/`, and run them with the Workflow tool;
5. stop at the two owner gates;
6. ship when the owner says so.

`S` = this skill's base directory (the Skill tool prints it when the skill loads; with the plugin installed it is inside the plugin cache, not the repo). Use the absolute path in every command. Run state lives in `<repo>/.agent/`; the layout is in `references/state.md`. The rules behind each stage are in `references/pipeline.md`. Read it once per session.

**Before you write or edit any workflow script, load the `workflow-authoring` skill** (Skill tool) if it is available. That includes the copies of the templates when the plan needs a stage they lack. It holds the script API and its traps: `meta` must be a pure literal, `Date.now()` and `Math.random()` throw, scripts are plain JavaScript, `args` must be passed as a JSON value. When it is not available, change only the args, never the scripts.

## 0. Read the invocation

| Invocation | Means |
|---|---|
| `/work 123`, `/work #123`, `/work <issue URL>` | New run from GitHub issue 123 |
| `/work <free text>` | New run from that text; no issue |
| `/work` alone | Ask what to build (one question), then start |
| `/work setup` | Write or update `.claude/work.json` only (`references/setup.md`) |
| `/work approve [changes…]` | Owner gate H1 passed → build. With text: one re-plan applying it, then build |
| `/work ship` · `/work fix then ship: <themes>` | Owner gate H2 → ship (§6), or one more fix round, then ship |
| `/work status` | Print the stage table (`state.py show`), the board link, and what waits on whom |
| `/work board` | Start the board again (or republish the snapshot) and give the link |

Do not post to GitHub issues or add CI workflows unless the owner asks. Reading an issue with `gh issue view` is fine.

## 1. Intake (inline, no agents)

1. **Check the base.**
   - `git status` must show no tracked changes, or only this run's changes.
   - Check `.agent/`. If it belongs to another unfinished run (`state.json` with `"finished": false` and another `run`), stop and ask. Never delete another run's state.
2. **Profile.** Read `.claude/work.json`. If it is missing, run the first-run setup in `references/setup.md` now and get the owner's OK before you go on. Never guess the gate, the app URL or the roles: a run without a profile is the run that gets lost.
3. **Write the request into `.agent/issue.md`.**
   - From an issue: `gh issue view <n> --json number,title,body,labels,comments,author`. Quote the title, body and comments verbatim under headings.
   - From free text: write the text verbatim, plus what you inferred (roles, pages, risk) marked as inferred.

   Add `.agent/` to `.git/info/exclude` (create the line once) so the run state can never be staged.
4. **Branch.** Create `<branch_prefix><n>-<slug>`, or `<branch_prefix>local-<slug>` without an issue, from the profile's `base` (default `main`) in the current checkout. Do not use a worktree when the local app serves this checkout.
5. **Manifest.** Run:

   ```
   python3 $S/scripts/state.py init --run <branch> --name "<title>" [--issue <n>] [--session <this session id, if known>] [--no-app]
   ```

   It writes `.agent/state.json` with all 18 stages as TODO (`--no-app` marks the app stages SKIP when the profile has no `app`). Mark `intake` DONE.
6. **Board.** Start it now, before any agent runs (`references/board.md`):
   - Local session: `python3 $S/scripts/board/wfboard.py --repo .` with `run_in_background: true`. Read its first line and give the owner the URL.
   - Cloud session (`CLAUDE_CODE_REMOTE` is set, or the owner cannot open localhost): write the snapshot (`--snapshot .agent/board.html`) and publish it with the Artifact tool; give the owner the link.
7. **App.** When the profile has `app`: run `app.check`. If the result is not `app.expect`, run `app.start` (tell the owner it takes about `app.start_minutes`), then check again. Then run `app.login` so each role's saved login exists. Record the result as the `stack` step.

## 2. Plan workflow → H1

1. Load `workflow-authoring` (see above). Copy `$S/workflows/plan.js` to `.agent/workflow/plan.js`.
2. Write `.agent/workflow/plan.args.json`:

   ```
   {"run": "<branch>", "issue": ".agent/issue.md", "title": "...", "today": "YYYY-MM-DD", "skill": "<absolute $S>", "profile": <the parsed .claude/work.json>}
   ```

   Pass the date from your context; scripts cannot read the clock.
3. Mark `research` RUN, then call `Workflow({scriptPath: ".agent/workflow/plan.js", args: <that object>})`. Pass `args` as a JSON value, not a string. The workflow shows on the board on its own while it runs.

The workflow researches in parallel, has the planner write `.agent/plan.md`, `tickets.json` and `test-plan.json` (plus `ui/pages.json` when the UI changes), and runs the approval agent with up to 2 revisions. It returns `{scope, plan, approval}`.

- Set `research`, `plan` and `approve` from the result, with one-line summaries and the files as `--artifact` (they then open on the board).
- If approval is still REVISE after 2 rounds, report the open issues to the owner. Do not hide them.
- **H1.** Set `h1` to WAIT. Refresh the board (republish the snapshot in a cloud session). In chat, print the stage table (`state.py show`) and the plan summary: tickets, test count, risk tier, `ui`, open questions with their defaults, and the approval agent's verdict. Ask with AskUserQuestion: "Approve" / "Approve with changes" / "Stop". Set `h1` DONE when approved. If the owner leaves, the run resumes later with `/work approve`.

## 3. Build workflow (after H1)

1. **Read the run's inputs:** `tickets.json`, `test-plan.json`, and the plan's `risk`, `ui`, `roles` and `specs`.
2. **Prepare the media layers** (`references/media.md`): when `ui` is true, put the ui-snap tool in place and build the `uiSnap` command. Check `command -v agent-browser ffmpeg`; when either is missing, or the profile says `"video": false`, video is off and the evidence says why.
3. **Write the files.** Load `workflow-authoring`. Copy `$S/workflows/build.js` to `.agent/workflow/build.js`, and write `build.args.json` with:
   - `run`, `today`, `skill` (absolute `$S`), `profile` (parsed);
   - `tickets` (verbatim from tickets.json), `roles`, `risk`, `ui`;
   - `e2e`: the profile's `e2e.cmd` with `{specs}` replaced by the plan's specs;
   - `uiSnap` (ui runs), `video`;
   - `budgets: {build: 2, qa: 1}`.

   The args make the generic template fit this run. Edit the copied script only when the plan needs a stage the template lacks, and note the edit in the evidence.
4. **Run it.** Mark `tests` RUN, then `Workflow({scriptPath: ".agent/workflow/build.js", args})`. When it returns, set each stage from the result (`tests`, `red`, `ui-before`, `implement`, `gate`, `verify`, `qa`, `ui-after`, `qa-fix`, `evidence`), with artifacts (`.agent/qa/<role>.json`, `.agent/evidence.md`). Read the `.agent/` files the stages wrote; never trust an agent's summary over the file it was meant to write.
5. **When the Workflow tool is missing** (a headless run), run the same stages with the Agent tool, in the order and with the prompts in `references/stages.md`, and record each stage as it finishes so the board stays current.

## 4. Media layers

`references/media.md` covers both.
- **UI before/after**, only when `ui` is true: before shots on the base code after the tests are written, after shots on the final code, then the UI review agent writes `.agent/ui/review.json` with expected / unexpected / broken per changed shot.
- **Video**, every run with an app: each QA agent records `demo-<role>.webm` (the happy path, for the owner) and `qa-<role>.webm` (its exploration), each with a contact sheet.

The board shows both under "◐ UI before / after" and "▶ Videos".

## 5. H2: evidence to the owner

Set `h2` to WAIT and refresh the board. Show the owner, in chat:
- the stage table;
- the pass table per role × browser, with NOT RUN where a browser did not run;
- gate results and the verify verdict;
- QA counts and open findings;
- UI shots that changed, with their verdicts, and the videos (on the board);
- time per stage, and cost, labelled as estimated unless billed per token;
- the board link.

Ask "Ship" / "One more fix round, then ship" / "Stop".

"Fix then ship" works as follows:
1. Run build.js once more with `mode: "fixup"` and `fixup: {themes}`. The owner has chosen to go over the budget.
2. It re-runs the gate (and the UI after capture and review if `ui`). Then run the full suite (`e2e.full`).
3. If everything is green, ship with no second ask. Otherwise stop and report again.

## 6. Ship

Ship only on the owner's `/work ship`, or a green "fix then ship".

1. Rebase the branch onto `origin/<base>`, then re-run the gate. A conflict or a red gate sends the run back to a fix round.
2. Run the ship checks. They must all pass:
   - No committed file points into the run state or a home folder:
     `git diff --name-only origin/<base>...HEAD | xargs grep -lE '\.agent/|/Users/|/home/[a-z]'` is empty (files of this skill itself excepted).
   - Nothing from the profile's `secrets`, `.agent/`, the ui-snap copy, `test-results/` or `node_modules/` is in the diff.
   - If `ui`: `.agent/ui/review.json` exists and is newer than `.agent/ui/shots.json`.
3. Land it by the profile's `ship.mode`:
   - `pr` (default): commit on the branch with a feature-level message, then ask once before `git push -u origin <branch>` and `gh pr create` (title from the request; body from the evidence summary, without `.agent/` paths).
   - `squash`: `git checkout <base> && git merge --squash <branch>`, commit with a feature-level message, then ask once before `git push origin <base>`.

   End the commit message with the attribution lines the session gives you.
4. Run `state.py step ship --status DONE` and `state.py finish`. Refresh the board one last time. If the run came from an issue, offer to comment the link on it. Do not comment unasked.

## Rules that always apply

- **Owner gates are never skipped.** Nothing is pushed without the owner's yes.
- **The board and the table stay current.** Every stage you start or finish goes through `state.py`; in a cloud session, republish the snapshot at H1, after QA and at H2.
- **Budgets:** build/verify fix rounds stop at 2; QA fix rounds stop at 1. When a budget runs out, stop and ask. Never loop silently.
- **Browsers.** A browser that did not run is reported as NOT RUN, never dropped. A test that fails once and then passes is a flake: repeat it 20 times and name it in the evidence.
- **QA scope.** QA agents change only their own role's state. They seed fixtures before they start and remove them afterwards.
- **Secrets.** Never print or commit anything in the profile's `secrets`. Agents read passwords from those files and never echo them. Videos and screenshots show only seeded test accounts.
- **Project rules.** Every agent follows the files in the profile's `rules`. Review findings cite `references/review-rules.md` or the project's `review_rules`.
- **Cost.** Record cost per stage where the workflow result has it. Otherwise mark it "estimated".
