# Project profile (default `.work-profile/work.json`)

The skill is generic. Everything it must know about one project lives in that project's profile (`P` below), committed so every session and every teammate gets the same answers. The format, with every field, is `assets/work.json.example`. Agents never guess these values; a missing profile is why a /work run gets lost.

## Where the profile lives

Default: **`.work-profile/work.json`** in the repo root. It has its own folder, so it works under any host (Claude Code, Codex, Copilot) and needs no `.claude/`. Do not ask the owner where to save it; create the folder and tell them the path.

Find it in this order and stop at the first hit:

1. A path the owner gave: `/work setup <path>`, or `--profile <path>` on any `/work` call.
2. The `WORK_PROFILE` environment variable.
3. `.agent/profile.json`: a parallel lane's profile, written by `scripts/lanes.py` with that lane's ports. Never edit it by hand.
4. `.work-profile/work.json`.

Call the result `PROFILE_PATH`. Pass it to every workflow as `args.profilePath`. The rest of this skill says "the profile" for this file. Review rules and other files the setup writes go in the same `.work-profile/` folder (`.work-profile/review-rules.md`).

## Models: detected, then confirmed; never hardcoded

The skill ships no model names. Setup finds the real ones:

1. Run `python3 $S/scripts/detect_models.py`. It finds each host's binary on PATH or inside the app or editor extension that bundles it (Claude Code in the terminal, the VS Code/Cursor extension or the desktop app; Codex CLI or its VS Code extension; Copilot CLI or `gh copilot`), then reads the models: Claude's `--model` aliases, Codex's `debug models` catalog, and Copilot's account catalog read over `copilot --acp` (the Agent Client Protocol; `session/new` lists the enabled models, no prompt is sent, so no model is called). It returns the running `host`, its `models` and `configured` model, and `by_host` for every host found. If `host` is `unknown`, offer the hosts in `by_host` and ask which one the owner uses. If `models` is empty, ask the owner which models the host offers.
2. Write into the profile: `host`, `available_models` (the list), `model_fallback` (the host's configured model if it is in the list, else the first model listed), and `models` (below).
3. Fill `models` only from `available_models`. Suggest: `plan` and `approve` the most capable listed model, `research` and `work` a cheaper one; with one model, use it everywhere. Show the table and ask with AskUserQuestion ("Use these" / "Change them" / "Stop"). Other models are accepted; the owner may type any model the host supports.
4. Any role with no model later uses `model_fallback`. A workflow with neither stops with an error.

Re-run detection on `/work setup` or when a run fails with "model not available": the host's models change.

## First run in a repo: write the profile

When the profile is missing (or the owner says `/work setup`):

0. **Resolve `PROFILE_PATH`** (section above) and do the model step.
1. **Read, do not ask.** Look at the repo before you ask anything:
   - `CLAUDE.md`, `AGENTS.md`, `README*`, `CONTRIBUTING*`: rules, names, how to run.
   - `package.json` scripts, `Makefile`, `pyproject.toml`, `composer.json`, `go.mod`, `Cargo.toml`: lint, type check and test commands.
   - CI config (`.github/workflows/*`, `.gitlab-ci.yml`): the gate CI actually runs. Copy it, do not invent it.
   - `docker-compose*.yml`, `Procfile`, dev scripts: how the app starts and on which URL.
   - `playwright.config.*`, `cypress.config.*`, `tests/`, `e2e/`: the end-to-end tool, its folder, its login setup (storageState files) and its browsers.
   - Seed or fixture scripts and test accounts: `app.login`, `app.fixtures`, the role names.
   - `.gitignore` and env files: the `secrets` list.
2. **Draft** the profile at `PROFILE_PATH` from what you found. Leave out what does not apply: no `app` for a library or CLI (no screenshots, no video; QA uses the CLI or API); no `e2e` when there is none (the gate is the test suite). Mark each value you inferred rather than found in the summary you show the owner.
3. **Project review rules.** If `CLAUDE.md` or the docs hold rules a reviewer should enforce (access rules, naming, security patterns), copy them into `.work-profile/review-rules.md` in the shape of `assets/work-review-rules.md.example`, each with its reason, and set `review_rules`. Otherwise leave `review_rules` out.
4. **Check the commands.** Run `app.check` and each `gate` command once. Record which pass on the base branch: a gate that is red before the feature starts must be known now, not found at H2.
4b. **Feature map.** If the repo has a map of its screens and actions (for example `docs/features.md`), set `feature_map` to it. If it has a UI and no map, offer to write one from the routes and templates, one line per screen or action, and set `feature_map`.
5. **The agent team.** Fill `team` from what you found: `stack` (the main framework, for example "Frappe", "Django", "Next.js"; it adds a `Senior <stack> dev`), `business` (one line: what the product sells and to whom, from the README or site), `design_system` (the folders of the project's own UI components and styles, when it has any). Leave the team on unless the owner says otherwise; `"team": false` is the lean pipeline.
6. **Show the owner** the profile as a table (field, value, found/inferred) and ask with AskUserQuestion: "Use it" / "Change it" / "Stop". Ask also, only when you could not tell: and the ship mode (`pr`: push the branch and open a pull request; `squash`: squash onto the base branch locally, then ask before the push). **Always ask the autonomy on first setup**, with AskUserQuestion: "Owner approves (Recommended)" = `"autonomy": "owner"` (the default; you decide at H1 and H2) / "Agents decide" = `"agents"` (the agent team stands in for you at both gates). Write what the owner picks; if they skip the question, write `"owner"`. Never write `"agents"` unasked.
7. Commit the profile on its own (`chore: add /work profile`) only when the owner says so; otherwise leave it uncommitted and use it. Before the commit, run `python3 $S/scripts/branch_guard.py --base <base>`. If it says `stale` (you are on the base branch, or the branch's pull request is merged or closed, or all its commits are already in the base), run it again with `--new <branch_prefix>work-profile` and commit there, then push that branch and open a pull request.

## Fields

| Field | Used by | Notes |
|---|---|---|
| `project` | every prompt | the product name agents use |
| `base`, `branch_prefix` | intake, ship | defaults `main`, `agent/` |
| `rules` | every agent | files with project rules; agents follow them |
| `review_rules` | approve, verify, UI review | project rules a finding can cite |
| `secrets` | every agent, ship check | globs never printed, never committed |
| `intake` | plan | `false` = no ACCEPT / NEEDS_INFO / REJECT decision (a cheap scope pass only); `{"comment": true}` = post NEEDS_INFO questions on the issue without asking. `models.intake` picks its model (default the approve model) |
| `routing` | build (verify) | `{"risk": {"low": {"lenses": ["correctness"], "model": "work"}, …}, "surfaces": {"security": {"lens": "security", "model": "verify"}, …}}`. Lenses: correctness, security, ui, money, data, migration; a model is a role name (work, verify, approve, plan, cheap) or an alias. Omit it for the defaults (SKILL.md §3) |
| `app.url`, `app.check`, `app.expect` | intake `stack`, QA, UI snap | omit `app` when there is no running app |
| `app.start`, `app.start_minutes` | intake `stack` | run when the check fails; tell the owner how long |
| `app.login`, `app.auth` | intake, QA, UI snap | `auth` is a storageState path pattern with `{role}` |
| `app.fixtures` | QA | seeds test data; QA removes what it made |
| `roles` | plan, QA, UI snap | include `signed-out` when there is a login |
| `gate` | gate stage, ship | run in order, all of them |
| `evals` | gate, plan | `{"cmd": "make eval", "paths": ["evals/", "internal/ai/"]}`: the gate runs `cmd` whenever a changed file is under one of `paths` (always, when `paths` is empty), and a failing or regressed eval turns the gate red; the architect adds eval cases for every AI change. Omit when the project has no AI features |
| `e2e.cmd` (`{specs}`), `e2e.full`, `e2e.browsers` | gate, red run, ship | browsers not run are reported NOT RUN |
| `ui_snap.dir`, `theme_key`, `hide`, `channel` | UI layer | `dir` must be inside the e2e package so Playwright resolves; `channel: "chrome"` uses the installed Chrome |
| `video` | QA | false to never record |
| `garden` | gardener | `{"log": "docs/garden.md", "repeat": 2}` by default: where findings are logged and how many sightings make a check; `false` turns the gardener off |
| `feature_map` | architect, designer, QA, UI review | path to a Markdown map of every screen, panel and action from the user's point of view (name, where it lives, how to reach it, roles). Shared names for owner and agents; plans keep it current |
| `host`, `available_models` | setup | written by `detect_models.py`: the host and the models it offers |
| `model_fallback` | workflows | the model any role without one uses; one of `available_models` |
| `models` | workflows | `plan` (architect), `approve` (approver), `research` (scope, researchers), `work` (tester, developers, gate, fixer, QA, evidence). Optional: `pm`, `ceo`, `design` (fall back to `plan`), `senior`, `verify` (fall back to `approve`), and `cheap` for the mechanical stages that only run commands and report (the scope pass, gate runs, red runs, UI snap captures; falls back to `work`; a small model such as `haiku` fits). Values come from `available_models` |
| `team` | plan, build | `false` = lean pipeline; or `{pm, ceo, design, senior}` as `false` to turn one off; `senior` may be a list of reviewer names; `stack`, `business`, `design_system` (`references/team.md`) |
| `autonomy` | gates, ship | asked on first setup; default `owner`: the owner approves H1 and H2. `agents`: the team stands in at both gates (SKILL.md, "Unattended runs"). May be per mode: `{"single": "owner", "chain": "agents", "lanes": "owner"}` |
| `tier`, `knobs` | plan | cost template `lean`, `balanced` (default) or `max`, and per-part overrides (SKILL.md, Cost templates). Ask the owner which template on first setup |
| `video`, `qa`, `ui_shots`, `garden` | build | `false` skips that stage (QA videos, agent QA, UI before/after screenshots, the Gardener); the evidence names each skipped stage. The board's Settings panel sets these, and the models, for every run (here) or for one run (`.agent/overrides.json`) |
| `ship.mode` | ship | `pr` (default) or `squash` |
| `ship.auto_push` | ship | with `autonomy: agents` only: push the run branch after each commit (never the base branch, never a PR) |

## Lanes (parallel runs)

`/work lanes` runs independent issues side by side, each in its own git worktree. Each lane needs its own ports, so the profile says which ports exist and how commands receive them:

```
"lanes": {
  "url": "http://localhost:{port}",
  "health": "/healthz",
  "ports": { "port": 8090, "e2e_port": 8099 },
  "step": 10,
  "env": { "DEV_ADDR": ":{port}", "APP_E2E_PORT": "{e2e_port}" },
  "copy": [".claude/settings.local.json"]
}
```

Lane k gets every port plus k × `step`. Every gate, e2e and app command in the lane's profile runs with `env` set, so the project's scripts must read those variables (a dev server address, a test server port, a Docker project name). Leave `lanes` out when the project cannot run twice on one machine.

