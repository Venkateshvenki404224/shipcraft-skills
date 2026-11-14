# control-room.json

Every key is optional. Relative paths are relative to the folder that holds the config. Keys that start with `_` are ignored, so use them for comments.

| Key | Default | What it does |
|---|---|---|
| `title` | `"Project control room"` | Page title and header. The two-letter mark is made from its initials. |
| `subtitle` | `""` | One line under the title: what is being built, for whom, on what. |
| `team_note` | `"You · Claude (orchestrator)"` | The "Whole team" line in the roles list: who the humans are. |
| `accent`, `accent_dark` | `#0f766e`, `#2dd4bf` | Brand colour in light and dark themes (hex only). |
| `output` | `"control-room.html"` | Where the page is written. `--out` overrides it. |
| `refresh_seconds` | `10` | How often the open page reloads itself. `0` = static (snapshots). `--refresh` overrides it. |
| `stale_after_seconds` | `1200` | A "running" agent whose transcript has not changed for this long is shown as failed. |
| `stages` | phases in first-seen order | `[{"title", "detail", "phases": ["Build", "Backend"]}]`, in plan order. A stage is *done* when all its agents finished, *active* while any runs, *pending* before any started. List stages that have not started yet too, so the owner sees the whole plan. |
| `roles` | label prefixes | `[{"key", "name", "model", "desc", "match": ["^qa\\b"]}]`. `match` is a list of case-insensitive regexes tried on the agent label, in order across all roles; the first hit wins. Agents that match no role go to `default_role`, or to a role made from their label prefix. |
| `default_role` | `""` | Role key for labels that match no regex. |
| `environment` | none | The block for the system under work. See below. Leave it out and the fifth KPI shows the run count. |
| `docs` | `{"root": ".", "include": ["**/*.md"], "exclude": [...]}` | The deliverables reader. `exclude` takes glob patterns on the path relative to `root`. `"enabled": false` hides it; `max_bytes` (400000) truncates very large files. |
| `run_names` | `{}` | `{"wf_…": "name"}` for runs whose script file is not `<name>-<run id>.js`. |
| `superseded` | `{}` | `{"wf_…": "why it was stopped"}`. Running agents in that run show as failed with this reason. |
| `covered` | `{}` | `{"<agent label>": "evidence"}`. Agents with that label that did not finish show as "Covered later" with the evidence. Only for work you verified. |
| `include_runs` | `[]` | Regexes on the run name (script name) or run id. When set, only matching runs are shown: one page per project when several projects share a session. |
| `extra_agents` | `""` | Path to a JSON list of agents run outside workflows: `{"id", "label", "phase", "role", "model", "status", "wf", "first", "result"}` (`first` is an ISO timestamp). |

## environment

```json
"environment": {
  "label": "Local stack",
  "health": {"url": "http://127.0.0.1:8000/health", "expect": "ok", "ok_text": "health → ok", "timeout": 2},
  "compose_project": "myproject",
  "links": [{"label": "App", "url": "http://localhost:8000"}],
  "notes": [{"label": "Reset", "text": "make reset"}]
}
```

- `health`: fetched on every rebuild. The page shows Online when the body contains `expect`.
- `compose_project`: lists the running containers of that docker compose project, if docker is on the PATH. When there is no `health`, the status is Online if any container runs.
- `links`: http(s) or relative URLs only; anything else is dropped.
- `notes`: short plain text. Never credentials.

## Where the data comes from

| Data | Source |
|---|---|
| Runs | `<claude config>/projects/<slug>/<session>/subagents/workflows/wf_*/journal.jsonl` (`started`, `result`, `failed` lines) |
| Run names | `<session>/workflows/scripts/<name>-<run id>.js` |
| Model, start time | the first lines of `agent-<id>.jsonl` in the run folder |
| Last activity | that file's modification time |
| Result | the agent's return value; for objects: `verdict`, `status`, `summary`, `estimate`, `report_file`, and lists such as `fixed` and `findings` |

`<slug>` is the absolute path of the folder the session started in, with every character other than a letter or digit replaced by `-`. The script looks for the config's folder, the current folder and their parents (stopping at the home folder). `CLAUDE_CONFIG_DIR` is honoured.
