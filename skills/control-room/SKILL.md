---
name: control-room
description: Give the owner a live "project control room" page for multi-agent work run with the Workflow tool - KPIs, a stage stepper, the team of roles, every agent with status, model, time and result, the environment's health, and a reader for the Markdown deliverables, in light and dark. One self-contained HTML file, rebuilt every few seconds from the session's workflow journals; no server. Use whenever you start a multi-stage or multi-run Workflow project (a product build, a migration, an audit, an agent "team" with PM/CEO/dev/QA roles), when the owner asks for a dashboard, dashboard.html, a control room or a way to watch the agents, or asks "where can I see progress?". Also use it to publish a snapshot of the page as an Artifact in a cloud session.
---

# Control room

A live page for the owner while a team of agents works. It reads what the Workflow tool already writes (one journal per run, one transcript per agent), so the work itself needs no changes. It is read-only: it writes one HTML file and nothing else.

`S` = this skill's base directory (the Skill tool prints it when the skill loads). Use the absolute path in commands.

## 1. Name things so the page can group them

The page groups agents by **stage** (the workflow's `phase`) and by **role** (a prefix of the agent's `label`). Before you write the workflow scripts:

- give every agent a label `"<Role>: <task>"`, e.g. `"QA: security audit"`, `"Senior dev: T-12 queue API"`;
- use the same short phase titles in every script (`phase('Build')`, `{phase: 'QA'}`), one per stage of the plan;
- add retries as `"<label> (retry 2)"`; the page folds them into one row with an "attempt N" tag.

## 2. Write the config (optional)

Without a config the page still works: the stages are the phases in the order they first appear, and the roles are the label prefixes. For a project the owner will watch for hours, write `control-room.json` next to the project (in its `tools/` folder or root) from `assets/control-room.json.example`. It sets:

- **title and subtitle**: the project's name and one line on what it is;
- **stages**: the plan's stages in order. Each stage lists the phase titles that belong to it, plus a one-line detail;
- **roles**: name, model and one line each, plus regexes on the label;
- **environment**: a health URL, the docker compose project, and links;
- **docs**: which Markdown files to show.

Every key is described in `references/config.md`. Never put a password, token or key in it: the page shows it.

## 3. Start it

Local session: run it in the background (Bash `run_in_background: true`) and leave it running for the whole project:

```
python3 $S/scripts/control_room.py --config <project>/tools/control-room.json --watch 10
```

Its first output line is the HTML path. Give it to the owner as a clickable path; they open it in a browser and it reloads itself (Pause and Theme buttons in the header). It reads the session with the newest workflow run in this folder's Claude Code project. Pass `--session <id>` to pin this session (needed when other sessions run in the same folder), or `--all-sessions` to merge every session. `--once --print` writes once and prints a one-line summary: use it to check the page without a browser.

Cloud or remote session (the owner cannot open your files): write a static snapshot and publish it with the Artifact tool (icon `chart`), then republish the same path after each stage:

```
python3 $S/scripts/control_room.py --config control-room.json --refresh 0 --out control-room.html
```

The page contains the agents' results and the deliverables, which can name local paths and code. Artifacts are private by default; read the page before the owner shares the link.

## 4. Keep it honest

The page shows what the journals say. When reality differs, say so in the config, never by editing journals:

- An agent that wrote nothing for `stale_after_seconds` (default 20 min) is shown as **Failed** with "Ended without a result": usage limits, network drops and stopped runs leave no journal entry.
- A run you stopped and re-ran: add it to `superseded` with one line on why; its in-flight agents show as failed.
- A task whose agent died but whose work another agent finished and you **verified**: add the label to `covered` with the evidence. It shows as "Covered later". Never use this for work you have not checked.
- A resumed or follow-up run that re-does a task: nothing to do. Only the newest attempt of each label is listed.
- A run whose script name the page cannot find: name it in `run_names`.
- Agents run outside workflows (a background Agent call): list them in the `extra_agents` JSON file.

When the owner says the page shows something wrong ("why is it still in progress?"), fix it in the config or the script. Explaining the error is not enough.

## 5. Stop it

When the project ends or the owner pauses it, stop the background loop (TaskStop) and tell the owner that the page is now a static record.
