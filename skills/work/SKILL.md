---
name: work
description: Build a feature end to end with an agent pipeline, in any repository, and show it live on a run board. Starts from a GitHub issue number, an issue URL, or a plain-text request. It writes a run-specific workflow from its templates and runs it with an agent team - research, a PM brief, a CEO scope check, an architect's plan, a UI/UX design, senior developer feasibility, PM decisions, a verifier and an approval agent, the owner's approval, tests first, implementation by backend, frontend and UI developers, the gate and E2E, verification, per-role agent QA recorded on video, UI before/after screenshots reviewed by the designer when the UI changes, an evidence report, a PM acceptance report, a CEO sign-off, and the owner's ship decision. Every stage shows on the run board (dashboard.html; an Artifact in cloud sessions) and in a stage table. Use whenever the owner says "/work", "work on", "use the work skill", or "implement issue N". Also use it to continue a run - "/work approve", "/work ship", "/work status" - or to set a repo up for it - "/work setup".
---

# /work: the feature pipeline

You are the orchestrator. You do not write feature code yourself. You:
1. take in the request;
2. make sure the repo has a profile (default `.work-profile/work.json`; the location is resolved, see `references/setup.md`), with models detected from the host and confirmed by the owner, and write one with the owner if it does not;
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
| `/work setup [path]` | Write or update the profile only (`references/setup.md`); `path` picks where it is read and saved |
| `/work approve [changes…]` | Owner gate H1 passed → build. With text: one re-plan applying it, then build |
| `/work ship` · `/work fix then ship: <themes>` | Owner gate H2 → ship (§6), or one more fix round, then ship |
| `/work status` | Print the stage table (`state.py show`), the board link, and what waits on whom |
| `/work resume` | A workflow stopped (network drop, API error, closed laptop): continue it from where it stopped (§ Recovery) |
| `/work board` | Start the board again (or republish the snapshot) and give the link |

Do not post to GitHub issues or add CI workflows unless the owner asks. Reading an issue with `gh issue view` is fine.

## 1. Intake (inline, no agents)

1. **Check the base.**
   - `git status` must show no tracked changes, or only this run's changes.
   - Check `.agent/`. If it belongs to another unfinished run (`state.json` with `"finished": false` and another `run`), stop and ask. Never delete another run's state.
2. **Profile.** Resolve `PROFILE_PATH` (`references/setup.md`, "Where the profile lives": invocation path, `WORK_PROFILE`, `.work-profile/work.json`). Do not ask where to save it; tell the owner the path. Read it. If it is missing, run the first-run setup now and get the owner's OK before you go on. Then check the models: if `plan`, `approve`, `research` or `work` has no value and there is no `model_fallback`, run `scripts/detect_models.py` and confirm the models with the owner ("Models" in setup.md). Never guess the gate, the app URL, the roles or the models: a run without a profile is the run that gets lost.
3. **Write the request into `.agent/issue.md`.**
   - From an issue: `gh issue view <n> --json number,title,body,labels,comments,author`. Quote the title, body and comments verbatim under headings.
   - From free text: write the text verbatim, plus what you inferred (roles, pages, risk) marked as inferred.

   Add `.agent/` to `.git/info/exclude` (create the line once) so the run state can never be staged.
4. **Branch.** Create `<branch_prefix><n>-<slug>`, or `<branch_prefix>local-<slug>` without an issue, from the profile's `base` (default `main`) in the current checkout, after `git fetch origin <base>`, starting from `origin/<base>` and never from whatever branch happens to be checked out. Do not use a worktree when the local app serves this checkout.
5. **Manifest.** Run:

   ```
   python3 $S/scripts/state.py init --run <branch> --name "<title>" [--issue <n>] [--session <this session id, if known>] [--no-app] [--team-off pm,ceo,design,senior|all]
   ```

   It writes `.agent/state.json` with all 26 stages as TODO. `--no-app` marks the app stages SKIP when the profile has no `app`; `--team-off` marks the stages of the team members the profile's `team` turns off (`"team": false` = `all`). Mark `intake` DONE.
6. **Board.** Start it now, before any agent runs (`references/board.md`):
   - Local session: `python3 $S/scripts/board/wfboard.py --repo .` with `run_in_background: true`. Read its first line and give the owner the URL.
   - Cloud session (`CLAUDE_CODE_REMOTE` is set, or the owner cannot open localhost): write the snapshot (`--snapshot .agent/board.html`) and publish it with the Artifact tool; give the owner the link.
7. **App.** When the profile has `app`: run `app.check`. If the result is not `app.expect`, run `app.start` (tell the owner it takes about `app.start_minutes`), then check again. Then run `app.login` so each role's saved login exists. Record the result as the `stack` step. Give the owner the app's address (`app.url`) next to the board link, every time you give the board link; the board also shows it at the top with whether it answers.

## 2. Plan workflow → H1

1. Load `workflow-authoring` (see above). Copy `$S/workflows/plan.js` to `.agent/workflow/plan.js`.
2. Write `.agent/workflow/plan.args.json`:

   ```
   {"run": "<branch>", "issue": ".agent/issue.md", "title": "...", "today": "YYYY-MM-DD", "skill": "<absolute $S>", "profile": <the parsed profile>, "profilePath": "<PROFILE_PATH>"}
   ```

   Pass the date from your context; scripts cannot read the clock.
3. Mark `research` RUN, then call `Workflow({scriptPath: ".agent/workflow/plan.js", args: <that object>})`. Pass `args` as a JSON value, not a string. Record the run id the tool returns at once: `python3 $S/scripts/state.py workflow plan <runId> --script .agent/workflow/plan.js --args-file .agent/workflow/plan.args.json`. The workflow shows on the board on its own while it runs.

The workflow runs the agent team (`references/team.md`):
1. **Research** in parallel (one reader per area, plus outside facts).
2. **PM: product brief** → `.agent/prd.md` (acceptance criteria, entry point, non-goals). **CEO: scope** → `.agent/ceo.md` (GO / CUT / NO_GO, must-haves, never-claim list).
3. **Architect: plan** → `plan.md`, `tickets.json` (each ticket has a developer `role`), `test-plan.json`, `ui/pages.json` when the UI changes.
4. **UI/UX designer** → `.agent/ui/design.md` (UI runs), then **CEO: design review** (one revision).
5. **Senior developers: feasibility** (`Senior dev`, plus `Senior <stack> dev` when the profile names a stack), in parallel.
6. **PM: decisions** → `.agent/pm.md` answers every open question and every developer issue; **Architect: apply decisions**.
7. **Verifier** (adversarial, fixes small mistakes in place) and **approval agent** in parallel; both must APPROVE; up to 2 revisions.

It returns `{scope, prd, ceo, design, designReview, feasibility, decisions, plan, approval, verifier, team, autonomy, stopped}`.

- Set `research`, `prd`, `ceo-scope`, `plan`, `design`, `feasibility`, `pm-decisions` and `approve` from the result, with one-line summaries and the files as `--artifact` (they then open on the board). A member the profile turned off, or `design` on a run without UI, is SKIP.
- **CEO NO_GO** (`stopped: "ceo"`): the workflow stops before the plan. Show the owner `.agent/ceo.md` and ask "Build anyway" / "Change the request" / "Stop". "Build anyway" re-runs plan.js with `profile.team.ceo` set to false for this run.
- If the verifier or the approval agent still says REVISE after 2 rounds, report the open issues to the owner. Do not hide them.
- **H1.** Set `h1` to WAIT. Refresh the board (republish the snapshot in a cloud session). In chat, print the stage table (`state.py show`) and the plan summary: the CEO's verdict and cuts, the PM's acceptance criteria and decisions (`pm.md`), tickets by developer role, test count, risk tier, `ui` and the design summary, the senior developers' verdicts, any question still open, and the verifier's and approval agent's verdicts. Ask with AskUserQuestion: "Approve" / "Approve with changes" / "Stop". Set `h1` DONE when approved. If the owner leaves, the run resumes later with `/work approve`.

## 3. Build workflow (after H1)

1. **Read the run's inputs:** `tickets.json`, `test-plan.json`, and the plan's `risk`, `ui`, `roles` and `specs`.
2. **Prepare the media layers** (`references/media.md`): when `ui` is true, put the ui-snap tool in place and build the `uiSnap` command. Check `command -v agent-browser ffmpeg`; when either is missing, or the profile says `"video": false`, video is off and the evidence says why.
3. **Write the files.** Load `workflow-authoring`. Copy `$S/workflows/build.js` to `.agent/workflow/build.js`, and write `build.args.json` with:
   - `run`, `today`, `skill` (absolute `$S`), `profile` (parsed), `profilePath`;
   - `tickets` (verbatim from tickets.json), `testPlan` (verbatim from test-plan.json; build.js checks that every frontend and ui ticket has an end-to-end case), `roles`, `risk`, `ui`;
   - `e2e`: the profile's `e2e.cmd` with `{specs}` replaced by the plan's specs;
   - `uiSnap` (ui runs), `video`;
   - `budgets: {build: 2, qa: 1}`.

   The args make the generic template fit this run. Edit the copied script only when the plan needs a stage the template lacks, and note the edit in the evidence.
4. **Run it.** Mark `tests` RUN, then `Workflow({scriptPath: ".agent/workflow/build.js", args})`, and record its run id: `python3 $S/scripts/state.py workflow build <runId> --script .agent/workflow/build.js --args-file .agent/workflow/build.args.json`. When it returns, set each stage from the result (`tests`, `red`, `ui-before`, `implement`, `gate`, `verify`, `qa`, `ui-after`, `qa-fix`, `garden`, `evidence`, `pm-report`, `ceo-signoff`), with artifacts (`.agent/qa/<role>.json`, `.agent/evidence.md`, `.agent/pm-report.md`, `.agent/ceo-signoff.md`). Read the `.agent/` files the stages wrote; never trust an agent's summary over the file it was meant to write.
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
- the PM's acceptance report (criteria met / not met, entry point) and the CEO's sign-off (SHIP or HOLD, with must-fix items);
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
   - `pr` (default): run `python3 $S/scripts/branch_guard.py --base <base>` first; on `stale`, run it with `--new <a new branch name>` so the commit never lands on a merged or closed branch. Then commit on the branch with a feature-level message, then ask once before `git push -u origin <branch>` and `gh pr create` (title from the request; body from the evidence summary, without `.agent/` paths).
   - `squash`: `git checkout <base> && git merge --squash <branch>`, commit with a feature-level message, then ask once before `git push origin <base>`.

   End the commit message with the attribution lines the session gives you.
4. **Wait for CI before anything else** (`pr` mode): run `python3 $S/scripts/ci_wait.py <pr number>` (it waits up to 30 minutes and prints one verdict).
   - `green`: go on.
   - `red`: read the failing checks' logs (`gh run view <id> --log-failed`), fix on the same branch while the build budget lasts, push (the PR updates), and wait again. When the budget is spent, report the failures to the owner and stop.
   - `none`: the repository runs no CI on pull requests; say so.
   - `pending`: still running after 30 minutes; say which checks, and ask the owner whether to keep waiting.
5. Run `state.py step ship --status DONE` (with the CI verdict in the summary) and `state.py finish`. Refresh the board one last time. Then report in one message: the PR link, the CI verdict per check, and what the owner does next (merge on green). Ask a closing question only when it changes something: do not offer to comment on the issue when the PR body already says `Closes #<n>` (GitHub links them and closes the issue on merge). Never comment unasked.

## Recovery: `/work resume`

A single agent that dies (a network drop, an API error) is retried by the workflow up to 3 times, and the board says "Recovered". When the whole workflow stops, the board says "Stopped" or "Stalled" (no agent has written anything for 15 minutes) with the reason. Then:

1. Read the recorded run: `python3 $S/scripts/state.py show` prints `workflow plan|build: <runId> (<script>)`.
2. If that run is still listed as running in this session, stop it first (TaskStop), so two copies do not edit the same files.
3. Resume it in this session: `Workflow({scriptPath: <script>, resumeFromRunId: <runId>, args: <the JSON in its args file>})`. Every agent that finished returns its cached result at once; only the failed and unstarted ones run again. Record the new run id with `state.py workflow`.
4. A resume works only in the session that started the run. If that session is gone, start the same workflow again with the same args file and say in the evidence that it ran twice. Check `git status` first: files the first run already changed stay, and the agents build on them.
5. Tell the owner, in one sentence, what stopped, what you resumed and what runs next.

## Unattended runs (`"autonomy": "agents"`)

Only when the profile says `"autonomy": "agents"`. Setup asks this on first use and the default is `"owner"` (the owner decides at H1 and H2); `agents` is written only when the owner picks it, and that choice is their standing OK. Then the team stands in for the owner:
- **H1** passes when the verifier and the approval agent both APPROVE, after the PM's decisions. If they still say REVISE after 2 rounds, stop and report.
- **H2** passes when the gate is green and the CEO signs off SHIP. A CEO HOLD gets one fix round on its `must_fix` items (build.js `mode: "fixup"`), then a second sign-off; still HOLD = stop and report.
- **Ship** = commit on the run branch, in small commits. Push the branch only when `ship.auto_push` is true. Never merge into the base branch, never open a pull request, never post anywhere: those wait for the owner.
- Log every decision the owner would have made, with the reason and any dissent, in `.agent/decisions.md`, and mark the gates `DONE` with "agents" in the summary.
- A model that does not answer (an agent hangs or returns nothing three times): change that role's model in the args, say so in `decisions.md`, and go on.

## Rules that always apply

- **No commit on a stale branch.** Before every commit (setup, ship, a fix round the owner asks for), run `python3 $S/scripts/branch_guard.py --base <base>`. `stale` means the current branch is the base, or its pull request is merged or closed, or all its commits are already in the base: run it with `--new <name>` and commit there. The one exception is `ship.mode: squash`, which commits on the base by design. `ok` with an open PR means the commit joins that PR: after pushing, rewrite the PR description so it covers every commit on the branch, not only the first ones (`gh pr edit <n> --body-file <file>`).
- **Owner gates are never skipped** in the default `"autonomy": "owner"`. Nothing is pushed without the owner's yes; with `"agents"`, only the run branch, and only with `ship.auto_push`.
- **The board and the table stay current.** Every stage you start or finish goes through `state.py`; in a cloud session, republish the snapshot at H1, after QA and at H2.
- **The team.** Agents are labelled "<Role>: <task>" (PM, CEO, Architect, UI/UX designer, Senior dev, Backend dev, Frontend dev, UI dev, Tester, Verifier, QA, Fixer), so the board shows who did what. Every agent call is retried up to 3 times when it returns nothing. `references/team.md` has each role's job and output.
- **Budgets:** build/verify fix rounds stop at 2; QA fix rounds stop at 1. When a budget runs out, stop and ask. Never loop silently.
- **Browsers.** A browser that did not run is reported as NOT RUN, never dropped. A test that fails once and then passes is a flake: repeat it 20 times and name it in the evidence.
- **QA scope.** QA agents change only their own role's state. They seed fixtures before they start and remove them afterwards.
- **Secrets.** Never print or commit anything in the profile's `secrets`. Agents read passwords from those files and never echo them. Videos and screenshots show only seeded test accounts.
- **Project rules.** Every agent follows the files in the profile's `rules`. Review findings cite `references/review-rules.md` or the project's `review_rules`.
- **Cost.** Record cost per stage where the workflow result has it. Otherwise mark it "estimated".
