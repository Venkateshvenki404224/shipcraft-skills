# Project profile (default `.claude/work.json`)

The skill is generic. Everything it must know about one project lives in that project's profile (`P` below), committed so every session and every teammate gets the same answers. The format, with every field, is `assets/work.json.example`. Agents never guess these values; a missing profile is why a /work run gets lost.

## Where the profile lives

`P` is not fixed. Find it in this order and stop at the first hit:

1. A path the owner gave: `/work setup <path>`, or `--profile <path>` on any `/work` call.
2. The `WORK_PROFILE` environment variable.
3. `.claude/work.json`.
4. The path in `.work-profile` at the repo root (one line, relative to the repo).

If none exists, decide where to save it:
- `.claude/` exists: propose `.claude/work.json`.
- `.claude/` does not exist: ask with AskUserQuestion where to read and save the profile ("Create `.claude/work.json`" / "Use another path" / "Stop"). Never create `.claude/` or any folder without the owner's answer.
- When the answer is not `.claude/work.json`, write the chosen path (repo-relative) to `.work-profile` so later sessions find it, and say so. Do not commit it unless the owner says so.

Call the resolved path `PROFILE_PATH`. Pass it to every workflow as `args.profilePath` and show it in the board's run header. Every other file in this skill that says `.claude/work.json` means `PROFILE_PATH`.

## Models: always asked, never assumed

The skill has no default models. Before any workflow runs, `P.models` must hold `plan`, `approve`, `research` and `work`. If any is missing (new profile, or an older profile that never set them):

1. Ask with AskUserQuestion, one question per missing key, with the aliases the session supports as options (for example `opus`, `sonnet`, `haiku`, `fable`) plus Other. Say what each key does (table under "Fields").
2. Ask once, as a second step, whether to set the optional role keys (`pm`, `ceo`, `design`, `senior`, `verify`). Unset ones fall back to `plan` (pm, ceo, design) or `approve` (senior, verify).
3. Write the answers into `P.models` and show them in the profile table at step 6 below.

A workflow started without the four base models stops with an error.

## First run in a repo: write the profile

When the profile is missing (or the owner says `/work setup`):

0. **Resolve `PROFILE_PATH`** (section above).
1. **Read, do not ask.** Look at the repo before you ask anything:
   - `CLAUDE.md`, `AGENTS.md`, `README*`, `CONTRIBUTING*`: rules, names, how to run.
   - `package.json` scripts, `Makefile`, `pyproject.toml`, `composer.json`, `go.mod`, `Cargo.toml`: lint, type check and test commands.
   - CI config (`.github/workflows/*`, `.gitlab-ci.yml`): the gate CI actually runs. Copy it, do not invent it.
   - `docker-compose*.yml`, `Procfile`, dev scripts: how the app starts and on which URL.
   - `playwright.config.*`, `cypress.config.*`, `tests/`, `e2e/`: the end-to-end tool, its folder, its login setup (storageState files) and its browsers.
   - Seed or fixture scripts and test accounts: `app.login`, `app.fixtures`, the role names.
   - `.gitignore` and env files: the `secrets` list.
2. **Draft** the profile at `PROFILE_PATH` from what you found. Leave out what does not apply: no `app` for a library or CLI (no screenshots, no video; QA uses the CLI or API); no `e2e` when there is none (the gate is the test suite). Mark each value you inferred rather than found in the summary you show the owner.
3. **Project review rules.** If `CLAUDE.md` or the docs hold rules a reviewer should enforce (access rules, naming, security patterns), copy them into `.claude/work-review-rules.md` in the shape of `assets/work-review-rules.md.example`, each with its reason, and set `review_rules`. Otherwise leave `review_rules` out.
4. **Check the commands.** Run `app.check` and each `gate` command once. Record which pass on the base branch: a gate that is red before the feature starts must be known now, not found at H2.
5. **The agent team.** Fill `team` from what you found: `stack` (the main framework, for example "Frappe", "Django", "Next.js"; it adds a `Senior <stack> dev`), `business` (one line: what the product sells and to whom, from the README or site), `design_system` (the folders of the project's own UI components and styles, when it has any). Leave the team on unless the owner says otherwise; `"team": false` is the lean pipeline.
6. **Show the owner** the profile as a table (field, value, found/inferred) and ask with AskUserQuestion: "Use it" / "Change it" / "Stop". Ask also, only when you could not tell: and the ship mode (`pr`: push the branch and open a pull request; `squash`: squash onto the base branch locally, then ask before the push). The models are always asked (section above). Always write `"autonomy": "owner"` and do not offer `"agents"`: the owner approves H1 and H2 themselves.
7. Commit the profile on its own (`chore: add /work profile`) only when the owner says so; otherwise leave it uncommitted and use it.

## Fields

| Field | Used by | Notes |
|---|---|---|
| `project` | every prompt | the product name agents use |
| `base`, `branch_prefix` | intake, ship | defaults `main`, `agent/` |
| `rules` | every agent | files with project rules; agents follow them |
| `review_rules` | approve, verify, UI review | project rules a finding can cite |
| `secrets` | every agent, ship check | globs never printed, never committed |
| `app.url`, `app.check`, `app.expect` | intake `stack`, QA, UI snap | omit `app` when there is no running app |
| `app.start`, `app.start_minutes` | intake `stack` | run when the check fails; tell the owner how long |
| `app.login`, `app.auth` | intake, QA, UI snap | `auth` is a storageState path pattern with `{role}` |
| `app.fixtures` | QA | seeds test data; QA removes what it made |
| `roles` | plan, QA, UI snap | include `signed-out` when there is a login |
| `gate` | gate stage, ship | run in order, all of them |
| `e2e.cmd` (`{specs}`), `e2e.full`, `e2e.browsers` | gate, red run, ship | browsers not run are reported NOT RUN |
| `ui_snap.dir`, `theme_key`, `hide`, `channel` | UI layer | `dir` must be inside the e2e package so Playwright resolves; `channel: "chrome"` uses the installed Chrome |
| `video` | QA | false to never record |
| `models` | workflows | **required, asked from the owner, no defaults.** `plan` (architect), `approve` (approver), `research` (scope, researchers), `work` (tester, developers, gate, fixer, QA, evidence). Optional: `pm`, `ceo`, `design` (fall back to `plan`), `senior`, `verify` (fall back to `approve`). Any alias the session supports |
| `team` | plan, build | `false` = lean pipeline; or `{pm, ceo, design, senior}` as `false` to turn one off; `senior` may be a list of reviewer names; `stack`, `business`, `design_system` (`references/team.md`) |
| `autonomy` | gates, ship | `owner`: the owner approves H1 and H2. Setup always writes `owner`. `agents` exists only if the owner edits the file by hand (SKILL.md, "Unattended runs") |
| `ship.mode` | ship | `pr` (default) or `squash` |
| `ship.auto_push` | ship | with `autonomy: agents` only: push the run branch after each commit (never the base branch, never a PR) |
