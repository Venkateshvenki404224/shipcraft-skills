# The run file: `<root>/tools/<slug>.run.json`

One file drives the plan workflow, the build workflow (with `tickets` added by `check_tickets.py --emit-args`) and the control room (through `init_run.py`). Start from `assets/run.example.json`. Keys starting with `_` are ignored.

| Key | Required | Default | What it does |
|---|---|---|---|
| `slug` | yes | | Lowercase, dashes. Names the workflow runs (`<slug>-plan`, `<slug>-build`), the control-room files and the screenshot folder. Use `<product>-<feature>` for features (`clinic-pharmacy`). |
| `product` | yes | | Product name as users see it. |
| `mode` | | `new-product` | `feature` tells every agent to reuse what exists, change it additively and keep the current demo and tests passing. |
| `root` | yes | | Absolute path of the product folder. |
| `docs` | | `docs` | Docs folder for this run, relative to root. Features use a subfolder (`docs/pharmacy`) so runs never overwrite each other. |
| `today` | | | Date string. Workflow scripts cannot read the clock, so pass it. |
| `brief` | | | The owner's or client's request, **verbatim**. The PM treats it as the source of truth. |
| `brief_files` | | `[]` | Client documents and mocks to read first (absolute or root-relative paths). |
| `context` | yes | | What every agent must know: what the product is, the stack and versions, what exists (for features), the client, the brand rules. 5 to 15 lines. |
| `environment` | | | The exact commands builders use: URLs, sign-in, the locked bench wrapper, build and test commands, where secrets come from. See `environment.md`. |
| `rules` | | `[]` | Extra hard rules added to every builder's prompt (brand words, "keep the existing demo spec passing", "no LLM calls"). |
| `ui` | | `true` | `false` = backend or Desk only: no design review, and the architect plans no screens. Remove `fe1`, `fe2` and `ux` from `roles` as well. |
| `viewport` | | `1366x768` | Size the design review checks at. |
| `browser` | | | How agents drive a browser, e.g. "Playwright from <root>/qa/e2e/". |
| `demo_budget` | | "a few hours of agent work" | What the CEO sizes the demo slice to. |
| `research` | | `[]` | `[{key, title, task, out, agentType?}]`. `out` is relative to the docs folder (`research/01-x.md`). `agentType` picks a custom agent such as `codebase-analyst` if one exists where the session runs. Empty = skip research. |
| `verify_research` | | `once` | `each` (one verifier per brief), `once` (one verifier over all briefs), `none`. |
| `roles` | yes | | See below. |
| `gate` | | | How to run the done gate when the plan has no gate ticket (a command or a spec file). |
| `gate_role` | | the gate ticket's owner, else `qa`, else `seed`, else the first ticket's owner | The builder role that runs the gate and alone may reset the system. Set it explicitly to a builder key. |
| `fix_rounds` | | `1` | Maximum QA+fix rounds. A new round runs only while blocker/major defects remain. |
| `signoff` | | `true` | `false` skips the CEO walkthrough (saves one Opus agent). |
| `control_room` | | | Passed to the control room: `title`, `subtitle`, `team_note`, `output`, `environment` (health URL, compose project, links), `accent`, `stale_after_seconds`. See the control-room skill's `references/config.md`. |

## roles

`{"<key>": {"label", "name", "model", "desc", "builder", "agentType", "effort"}}`

- **Fixed keys the workflows use:** `pm` (requirements, plan, report), `ceo` (decision, sign-off), `ver` (research check, plan review, code and security review), `res` (researchers), `fdev` and `sdev` (feasibility), `ux` (design review). A fixed key you leave out still works with a built-in label and brief and the session's model, so list it only to set its model or brief. With `ui: true` and no `ux` role, the design review runs as a generic "UI/UX" agent on the session model; add `ux` with `sonnet` to keep it cheap. Builder keys are free (`fe1`, `fe2`, `seed`, `qa`, `be3`...).
- `label` is the prefix of every agent label (`"Senior Frappe dev · T-12 Queue API"`); the control room groups agents by it.
- `builder: true` means the role can own tickets. Ticket owners and defect owners must be builder keys.
- `desc` is the role's brief and goes into every prompt for it: say what the role owns (files, areas) and how it thinks.
- `model`: `haiku`, `sonnet`, `opus`, `fable`, or leave it out to inherit the session's model.

## Presets

**Lean (default).** Opus or Fable only judge: `pm` fable, `ceo` opus, `ver` opus. Builders sonnet, `res` haiku, `verify_research: once`, `fix_rounds: 1`, one agent per role at a time. For backend or Desk-only work: `ui: false`, no `fe*`/`ux` roles, no screenshots or videos.

**Full (for a high-stakes client demo).** Every role on opus (PM fable), `verify_research: each`, two frontend devs, `fix_rounds: 2`, and a CEO design review as a ticket (`CEO-R`, owned by `ceo`, so give `ceo` `"builder": true`) followed by `UX-R` (owned by `ux`). It roughly triples the token cost; ask first.
