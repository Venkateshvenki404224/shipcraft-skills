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
| 3 | Plan | `research` | scope agent + one reader per area + outside facts | `.agent/research.md` (via the planner) | every fact has path:line or a URL |
| 4 | Plan | `plan` | planner (`models.plan`) | `plan.md`, `tickets.json`, `test-plan.json`, `ui/pages.json` if UI | the files exist and parse |
| 5 | Plan | `approve` | approval agent (`models.approve`), ≤2 revisions | none (verdict in the result) | APPROVE, or REVISE reported to the owner |
| 6 | Plan | `h1` | **owner** | none | Approve |
| 7 | Tests first | `tests` | one agent per test ticket | test files | files written |
| 8 | Tests first | `red` | agent | none | every new case fails for the right reason (one test-fix retry) |
| 9 | UI + video | `ui-before` | agent (if `ui`) | `.agent/ui/before/` | shots taken on the base code |
| 10 | Implement | `implement` | one agent per ticket, in dependency waves | product files | files written |
| 11 | Gate + E2E | `gate` | agent runs; agent fixes | none | all checks green; ≤2 build fix rounds |
| 12 | Verify | `verify` | low: Sonnet ×1 · medium: Opus ×1 · high: Opus ×3 lenses | none | no blocker/major/minor left, or the budget is reported as spent |
| 13 | Agent QA | `qa` | one agent per role, in parallel, on video | `.agent/qa/<role>.json`, `.agent/video/` | the findings files are written |
| 14 | UI + video | `ui-after` | capture + UI review agent (Opus at high risk) | `.agent/ui/{after,diff,marked}/`, `shots.json`, `review.json` | review written |
| 15 | Agent QA | `qa-fix` | agent, ≤1 round | product files | QA majors and unexpected/broken shots fixed, gate green again |
| 16 | Ship | `evidence` | agent | `.agent/evidence.md` | the file exists |
| 17 | Ship | `h2` | **owner** | none | Ship, or "Fix then ship" |
| 18 | Ship | `ship` | orchestrator | the commit (or PR) | ship checks pass; the push is approved |

Models come from the profile's `models` (`plan`, `approve`, `research`, `work`). Record the model each alias resolved to (the board shows it per agent).

## Gate

The gate is the profile's `gate` list, run in order, all of them, then the profile's `e2e.cmd` with this feature's specs. When the project has one gate script (for example `make check` or `tools/gate.sh`), list only that. Run the full suite (`e2e.full`) at ship.

## Budgets

- **build: 2.** Fix rounds for a red gate plus the verify fixes, counted together.
- **qa: 1.** One round for QA blocker/major findings that are not existing bugs, plus unexpected/broken UI shots.

When a budget runs out, the run reports and stops. Only the owner grants another round, through "Fix then ship" (build.js `mode: "fixup"`).
