# Run state: `<repo>/.agent/`

One run per checkout. The folder is never committed: add `.agent/` to `.git/info/exclude` at intake (local, not shared) so it cannot be staged by accident. The ship check fails if a committed file points into it.

```
.agent/
  issue.md            the request, verbatim (issue title/body/comments, or the owner's text)
  state.json          run manifest for the board and the stage table (scripts/state.py)
  research.md         merged research, with path:line / URL evidence
  plan.md             plan, request→ticket map, test contract, risk, expected visible changes, ≤4 questions
  tickets.json        [{id, title, kind: test|impl|docs, files, deps, acceptance, model}]
  test-plan.json      unit/script + end-to-end cases with ids, roles, browsers, ticket
  workflow/           this run's workflow files: plan.js, build.js and their *.args.json (what actually ran)
  qa/<role>.json      agent QA findings per role; qa/<role>/*.png screenshots
  video/              demo-<role>.webm, qa-<role>.webm, *.contact-sheet.png   (agent-browser record)
  ui/                 pages.json, before/, after/, diff/, marked/, shots.json, run.json, review.json   (scripts/ui-snap)
  ui-snap/            the UI tool's runner, only when the project has no Playwright of its own
  board.html          the board snapshot, only in cloud sessions (scripts/board/wfboard.py --snapshot)
  evidence.md         the H2 report
```

## state.json

`scripts/board/wfboard.py` reads this format (`export_pipeline`). Statuses: RUN, DONE, PASS, FAIL, CHANGES, WAIT (the owner's turn), TODO, SKIP, STOPPED.

```json
{"run": "agent/12-tour", "name": "Getting started tour", "session": "<orchestrator session uuid>", "issue": "12",
 "phases": ["Intake", "Plan", "Tests first", "Implement", "Gate + E2E", "Verify", "Agent QA", "UI + video", "Ship"],
 "steps": [{"phase": "Plan", "key": "plan", "title": "Plan + approval", "status": "DONE", "who": "planner",
            "summary": "8 tickets, 55 cases, risk medium", "artifacts": [".agent/plan.md"], "deps": ["research"]}],
 "artifacts": [".agent/issue.md"], "finished": false}
```

- `init` writes all 18 stages as TODO, so the board and `show` have the full table from the first minute.
- Workflow runs also appear on the board on their own (`wf_*`, read from the session's workflow journal). The manifest adds what a journal cannot show: the owner's gates, the stages the orchestrator runs inline, the screenshots and the videos.
- The board serves `.agent/ui/` and `.agent/video/` through symlinks, so new screenshots and videos show up as soon as they are written.
