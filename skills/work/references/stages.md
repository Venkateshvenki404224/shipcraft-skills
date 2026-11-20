# Stages: what each produces, and how to run them without the Workflow tool

The stage prompts live in `workflows/plan.js` and `workflows/build.js`, so there is one copy. When the Workflow tool is unavailable, run the same `agent(...)` calls with the Agent tool:
- keep the same order;
- copy each prompt from the script, filling in `args` and the profile by hand;
- run in parallel where the script uses `parallel()`;
- respect the same budgets.

After every stage: `python3 $S/scripts/state.py step <key> --status <status> --summary "<one line>"` (the phase and title are already set by `init`).

| # | Phase (board column) | Step key | Who | Writes | Passes when |
|---|---|---|---|---|---|
| 1 | Intake | `intake` | orchestrator | `.agent/issue.md`, branch, `state.json` | issue.md exists; the branch is off the base branch |
| 2 | Intake | `stack` | orchestrator | none | the profile's `app.check` gives `app.expect`; logins saved (skip when there is no app) |
| 3 | Plan | `research` | Scope + one Researcher per area + outside facts | `.agent/research.md` (via the architect) | every fact has path:line or a URL |
| 4 | Plan | `prd` | PM (`models.pm`) | `.agent/prd.md` | acceptance criteria are testable; the entry point is named |
| 5 | Plan | `ceo-scope` | CEO (`models.ceo`) | `.agent/ceo.md` | GO or CUT; NO_GO stops the run and goes to the owner |
| 6 | Plan | `plan` | Architect (`models.plan`) | `plan.md`, `tickets.json` (with a developer `role` per ticket), `test-plan.json`, `ui/pages.json` if UI | the files exist and parse |
| 7 | Plan | `design` | UI/UX designer (`models.design`) + CEO design review, ≤1 revision (UI runs) | `.agent/ui/design.md` | every state and the exact copy for each changed page |
| 8 | Plan | `feasibility` | Senior dev + Senior `<stack>` dev (`models.senior`), in parallel | none (issues in the result) | FEASIBLE, or issues passed to the PM |
| 9 | Plan | `pm-decisions` | PM, then Architect applies | `.agent/pm.md`, updated plan files | no open question left without a decision |
| 10 | Plan | `approve` | Verifier (`models.verify`) + Approver (`models.approve`) in parallel, ≤2 revisions | fixes in place | both APPROVE, or REVISE reported to the owner |
| 11 | Plan | `h1` | **owner** (with `autonomy: agents`: the step above) | none | Approve |
| 12 | Tests first | `tests` | Tester, one per test ticket | test files | files written |
| 13 | Tests first | `red` | Gate | none | every new case fails for the right reason (one test-fix retry) |
| 14 | UI + video | `ui-before` | UI snap (if `ui`) | `.agent/ui/before/` | shots taken on the base code |
| 15 | Implement | `implement` | Backend dev / Frontend dev / UI dev / Data dev / Tech writer, by ticket `role`, in dependency waves | product files | files written |
| 16 | Gate + E2E | `gate` | Gate runs; Fixer fixes | none | all checks green; ≤2 build fix rounds |
| 17 | Verify | `verify` | low: `models.work` ×1 · medium: `models.verify` ×1 · high: `models.verify` ×3 lenses | none | no blocker/major/minor left, or the budget is reported as spent |
| 18 | Agent QA | `qa` | one QA agent per role, in parallel, on video | `.agent/qa/<role>.json`, `.agent/video/` | the findings files are written |
| 19 | UI + video | `ui-after` | capture + UI/UX designer review (UI reviewer when the designer is off) | `.agent/ui/{after,diff,marked}/`, `shots.json`, `review.json` | review written |
| 20 | Agent QA | `qa-fix` | Fixer, ≤1 round | product files | QA majors and unexpected/broken shots fixed, gate green again |
| 21 | Verify | `garden` | Gardener (`models.work`), when there are findings and the profile's `garden` is not false | lint rules or structure tests, the garden log | repeated patterns are checks, first sightings logged, gate green |
| 22 | Ship | `evidence` | Evidence | `.agent/evidence.md` | the file exists |
| 23 | Ship | `pm-report` | PM | `.agent/pm-report.md` | every acceptance criterion has a verdict and evidence |
| 24 | Ship | `ceo-signoff` | CEO | `.agent/ceo-signoff.md` | SHIP, or HOLD with must-fix items |
| 25 | Ship | `h2` | **owner** (with `autonomy: agents`: CEO SHIP + green gate) | none | Ship, or "Fix then ship" |
| 26 | Ship | `ship` | orchestrator | the commit (or PR) | ship checks pass; the push is approved |

Models come from the profile's `models` (`plan`, `approve`, `research`, `work`, and for the team `pm`, `ceo`, `design`, `senior`, `verify`). Record the model each alias resolved to (the board shows it per agent). Roles and their jobs: `references/team.md`.

## Gate

The gate is the profile's `gate` list, run in order, all of them, then the profile's `e2e.cmd` with this feature's specs. When the project has one gate script (for example `make check` or `tools/gate.sh`), list only that. Run the full suite (`e2e.full`) at ship. When the profile has `evals`, the gate also runs `evals.cmd` if a changed file is under `evals.paths`; a failing eval makes the gate red, the same as a failing test.

## Budgets

- **build: 2.** Fix rounds for a red gate plus the verify fixes, counted together.
- **qa: 1.** One round for QA blocker/major findings that are not existing bugs, plus unexpected/broken UI shots.

When a budget runs out, the run reports and stops. Only the owner grants another round, through "Fix then ship" (build.js `mode: "fixup"`).
