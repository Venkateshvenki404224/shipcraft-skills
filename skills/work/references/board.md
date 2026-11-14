# The run board

`scripts/board/wfboard.py` + `scripts/board/dashboard.html`. It shows, live, every stage of the run: the owner's gates and inline stages from `.agent/state.json`, every workflow agent from the session's workflow journal (model, cost, time, last action, prompt, activity, result), the plan and evidence files, the UI before/after screenshots and the QA videos. It needs only Python 3; it reads files and never writes to the repo.

The page uses the same design as the `control-room` skill, in light and dark:
- **Header:** the run picker (R).
- **KPI cards:** steps done, current stage, what waits on the owner, models and estimated cost.
- **Stage stepper:** a step waiting on the owner pulses; click a step to filter by it.
- **Team and steps:** the team list and a steps table with status filters. Click a row for that step's result, activity and prompt.
- **Evidence:** cards that open the UI before/after review (side by side, slider, diff) and the QA videos.
- **Deliverables:** a reader for the plan and evidence.

## Local session: live board

Start it at intake, from the repo root, with the Bash tool's `run_in_background: true`:

```
python3 $S/scripts/board/wfboard.py --repo .
```

Its first output line is the URL (`http://127.0.0.1:8765/dashboard.html`, or the next free port). Give the owner that URL once, and again at H1 and H2. Leave it running for the whole run; it polls every 2 s. `--once` prints one summary line per run and exits, which is how to check it without a browser.

The board finds the session transcripts by the folder the Claude Code session started in (the repo or a folder above it). If it prints "no Claude Code project folder found", pass `--project <config dir>/projects/<slug>` where the slug is that folder's absolute path with every non-alphanumeric character replaced by `-`.

## Cloud or remote session: snapshot as an Artifact

When the owner cannot open the session's localhost (Claude Code on the web sets `CLAUDE_CODE_REMOTE=true`; or the owner says so), publish snapshots instead:

```
python3 $S/scripts/board/wfboard.py --repo . --snapshot .agent/board.html
```

This writes one self-contained HTML file: every file the board would fetch is inlined, and screenshots, contact sheets and (within a 12 MB budget) videos become data URIs. Then publish `.agent/board.html` with the Artifact tool (icon `chart`, title "Run board"), and give the owner the link. The page is finished: publish it as it is, without restyling it.

The snapshot carries the agents' prompts, activity and reports, which can name local paths and code. Artifacts are private by default; read it before you share the link with anyone.

Republish the same file path after each stage that changes what the owner looks at: after the plan (H1), after Agent QA, after the UI review, and at H2. Republishing the same path keeps the same link.

If the Artifact tool is not available, say so, and point the owner at `.agent/evidence.md` and the stage table instead.

## The stage table

`python3 $S/scripts/state.py show` prints the run's 18 stages as a markdown table (status, phase, step, summary). Print it in chat at H1, at H2, and for `/work status`, so the owner has the table even without the board.
