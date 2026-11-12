# Project profile: `.claude/work.json`

The skill is generic. Everything it must know about one project lives in that project's `.claude/work.json`, committed so every session and every teammate gets the same answers. The format, with every field, is `assets/work.json.example`. Agents never guess these values; a missing profile is why a /work run gets lost.

## First run in a repo: write the profile

When `.claude/work.json` is missing (or the owner says `/work setup`):

1. **Read, do not ask.** Look at the repo before you ask anything:
   - `CLAUDE.md`, `AGENTS.md`, `README*`, `CONTRIBUTING*`: rules, names, how to run.
   - `package.json` scripts, `Makefile`, `pyproject.toml`, `composer.json`, `go.mod`, `Cargo.toml`: lint, type check and test commands.
   - CI config (`.github/workflows/*`, `.gitlab-ci.yml`): the gate CI actually runs. Copy it, do not invent it.
   - `docker-compose*.yml`, `Procfile`, dev scripts: how the app starts and on which URL.
   - `playwright.config.*`, `cypress.config.*`, `tests/`, `e2e/`: the end-to-end tool, its folder, its login setup (storageState files) and its browsers.
   - Seed or fixture scripts and test accounts: `app.login`, `app.fixtures`, the role names.
   - `.gitignore` and env files: the `secrets` list.
2. **Draft** `.claude/work.json` from what you found. Leave out what does not apply: no `app` for a library or CLI (no screenshots, no video; QA uses the CLI or API); no `e2e` when there is none (the gate is the test suite). Mark each value you inferred rather than found in the summary you show the owner.
3. **Project review rules.** If `CLAUDE.md` or the docs hold rules a reviewer should enforce (access rules, naming, security patterns), copy them into `.claude/work-review-rules.md` in the shape of `assets/work-review-rules.md.example`, each with its reason, and set `review_rules`. Otherwise leave `review_rules` out.
4. **Check the commands.** Run `app.check` and each `gate` command once. Record which pass on the base branch: a gate that is red before the feature starts must be known now, not found at H2.
5. **Show the owner** the profile as a table (field, value, found/inferred) and ask with AskUserQuestion: "Use it" / "Change it" / "Stop". Ask also, only when you could not tell: the ship mode (`pr`: push the branch and open a pull request; `squash`: squash onto the base branch locally, then ask before the push) and the plan model.
6. Commit the profile on its own (`chore: add /work profile`) only when the owner says so; otherwise leave it uncommitted and use it.

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
| `models` | workflows | `plan`, `approve`, `research`, `work`; aliases such as `opus`, `sonnet`, `fable` |
| `ship.mode` | ship | `pr` (default) or `squash` |
