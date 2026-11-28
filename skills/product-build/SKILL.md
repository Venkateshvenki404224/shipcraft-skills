---
name: product-build
description: Build a whole product, or a big module on an existing product, with an agent team, from a client brief to a demo that passes a done gate. It runs as two Workflow runs. The plan run goes research (verified), PM requirements, CEO scope and demo slice, Frappe and architecture feasibility, then the PM's plan plus a machine-readable tickets.json and a verifier review. The owner approves. The build run goes ticket scheduler (one agent per role), close-out, verifier, design review and done gate, fixes, final gate, PM report, CEO sign-off. The control-room skill shows it all live. Use whenever someone says "/product-build", "build this product/module end to end", "use the agent team", "PM/CEO/dev/QA team", "client requirement → demo", "new Frappe product", or wants to watch an agent team build something. Also use it to continue such a run ("/product-build approve", "status", "resume", "board"). For one feature from one issue, ending in a pull request, use the `work` skill instead.
---

# Product build: an agent team from brief to demo

You are the orchestrator. You do not write product code. You:
1. turn the request into one **run file** (`<root>/tools/<slug>.run.json`);
2. start the **control room** (the `control-room` skill in this plugin) so the owner can watch;
3. run the **plan** workflow, then stop for the owner's approval;
4. run the **build** workflow, then report.

`work` vs `product-build`: `work` takes one issue through tests, code, QA and a pull request on a branch. `product-build` is for something bigger and fuzzier: a new product or a module, where the team must first research the domain, decide what to build, plan many tickets across roles, and produce a demo with a numbered done gate. It came from building a hospital ERP demo on Frappe + ERPNext + Healthcare with an agent team, and then adding several modules to it.

`S` = this skill's base directory (printed when the skill loads). Use absolute paths in commands. The control room script is at `$S/../control-room/scripts/control_room.py`.

**Before you edit any workflow script, load the `workflow-authoring` skill.** You normally won't need to: the templates in `workflows/` take everything project-specific from `args`, so you change the run file, not the scripts. If workflow-authoring is not available, change only the args.

## 0. Read the invocation

| Request | Do |
|---|---|
| `/product-build <idea / client brief / file>` | New run: §1 to §3, then stop at the gate |
| `/product-build feature <text>` (or the request names an existing product) | Same, with `"mode": "feature"`: docs go in a subfolder (`docs/<feature>/`), and the context lists what exists |
| `/product-build approve [changes]` | Gate passed. With changes: ask the PM role to apply them to 40-plan.md and tickets.json (one agent), re-check, then §4 |
| `/product-build status` | Tickets and statuses from the latest journal, the control-room path, what waits on whom |
| `/product-build resume` | A run stopped: relaunch it with `resumeFromRunId` (§6) |
| `/product-build board` | Restart the control room and give the path |

## 1. Intake (inline, no agents)

1. **Find the project.** For a new product, agree a folder and create it. For a feature, use the product's folder and read its README, demo notes and the other feature folders under `docs/`. The context must say what exists and what the new feature can reuse; overlap you miss here gets built twice.
2. **Check the environment is up, not just present.** The build needs a running system the agents can test against (for Frappe: a bench, best in Docker, with a locked wrapper). Run its health check. If it is down, start it; if there is none, set it up first or make it ticket 1. `references/environment.md` has the pattern.
3. **Write the run file** from `assets/run.example.json` into `<root>/tools/<slug>.run.json`. Every key is in `references/run-config.md`. The ones that matter most:
   - `brief`: the owner's or client's words verbatim, plus `brief_files` for their documents;
   - `context`: what the product is, the stack and versions, what exists, who the client is;
   - `environment`: the exact commands agents use (URLs, wrapper, build command, test command, where secrets come from);
   - `roles`: who is on the team and which model each uses. The default is lean: the strongest models only judge (PM, CEO, verifier), a mid model builds, a small one researches. Remove roles the run does not need (backend-only: drop `fe1`, `fe2`, `ux` and set `"ui": false`);
   - `research`: one item per real unknown. 0 when the domain and stack are known, 1 or 2 for a feature (typically "what does the existing code already give us" plus one domain question), up to 6 for a new product in an unfamiliar industry (competitors, reference products, regulation, day-to-day operations, the framework's capability map, reusable apps);
   - `gate_role`: the builder who owns demo data and tests (`seed` or `qa`); only that role may reset the system, and it runs the done gate;
   - cost knobs: `signoff`, `fix_rounds`, `verify_research` (see the presets in run-config.md);
   - `today`: today's date as `YYYY-MM-DD` (workflow scripts cannot read the clock).

   Never put a password or token in it: name the env var instead. Paths are absolute.
4. **Initialise:**
   ```
   python3 $S/scripts/init_run.py <root>/tools/<slug>.run.json
   ```
   It checks the run file and writes `control-room-<slug>.json`, `extra-agents-<slug>.json`, and `<slug>-plan.workflow.js` and `<slug>-build.workflow.js` (the templates with the run's name, so the control room can tell runs apart). It prints the next commands.
5. **Start the control room** in the background (Bash `run_in_background: true`) and leave it running for the whole project:
   ```
   python3 $S/../control-room/scripts/control_room.py --config <root>/tools/control-room-<slug>.json --watch 10
   ```
   Give the owner the HTML path. If other sessions run workflows in the same folder, add `--session <this session id>`. In a cloud session, write a static snapshot (`--refresh 0`) and publish it as an Artifact instead. See the control-room skill.

## 2. Plan workflow

Run the Workflow tool with `scriptPath: <root>/tools/<slug>-plan.workflow.js` and `args`: the run file's JSON as a value, not a string. It writes, in the docs folder:

| File | Who | What |
|---|---|---|
| `research/*.md` | Researchers + verifier | One brief per question, checked (`verify_research`: `each`, `once` (default), `none`) |
| `10-requirements.md` | PM | Personas, journeys, requirement catalogue with IDs and priorities |
| `20-ceo-decision.md` | CEO | Phase 1/2/later, **the demo slice** as a 10-minute story, cut order, **the done gate**, claims |
| `30-frappe-feasibility.md` | Senior Frappe dev | Requirement → out of the box / configure / custom / new, data model, API contract draft, seed plan, gotchas |
| `31-architecture.md` | Senior dev | Architecture, frontend plan, integrations, security matrix |
| `40-plan.md` + `tickets.json` | PM | §1 decisions … §8 rules for builders, §9 file ownership, §10 gate and tickets |
| `41-plan-review.md` | Verifier | Findings, fixed in place |

On a stack other than Frappe, the feasibility role's brief (`roles.fdev.desc`) names your framework; the file name stays.

## 3. Owner gate (stop here)

When the plan run returns:
1. Run `python3 $S/scripts/check_tickets.py <root>/tools/<slug>.run.json`. If it fails, ask the PM role (one agent) to fix tickets.json, then check again. Do not rewrite the plan's substance yourself.
2. Give the owner a short brief: the demo slice (from 20), what is cut, the done gate, the schedule check_tickets printed (roles × hours, critical path), the verifier's open risks, and the client questions. Link 20-ceo-decision.md and 40-plan.md.
3. Ask: approve, approve with changes, or stop. Do not start the build without an explicit yes. A plan the owner never saw is the build that gets thrown away.

## 4. Build workflow

On approval:
```
python3 $S/scripts/check_tickets.py <root>/tools/<slug>.run.json --emit-args <root>/tools/<slug>-build.args.json
```
Then run the Workflow tool with `scriptPath: <root>/tools/<slug>-build.workflow.js` and `args`: that file's JSON. The run:
- **Design / Build:** a dependency scheduler runs each ticket when its dependencies are finished, **one agent per role at a time**, so two agents never edit one role's files. Stretch tickets open only when every core ticket is built or done.
- **QA:** close-out of every ticket that is not "done", then in parallel the verifier's code and security review (`52-verifier-review.md`), the gate run (`51-gate-results.md`) and, with `ui`, the designer's browser review (`53-design-review.md`).
- **Fix:** defects go to their owners (`54-fixes.md`). `fix_rounds` caps the QA+fix rounds; a new round runs only while blocker/major defects remain.
- **Demo:** the final gate, the PM's `60-build-report.md`, and the CEO's walkthrough `61-ceo-signoff.md` (go / go-with-caveats / no-go).

## 5. Report

Read 60, 61 and the final gate yourself, then tell the owner: the verdict, what works (with the demo URL and users), what failed or was cut, and the next actions. Keep the control room running if more runs follow; otherwise stop it (TaskStop) and say the page is now a static record. When the run taught something new about the stack, add it to `references/lessons.md`.

## 6. When things go wrong

- **A run stopped** (network drop, usage limit, closed laptop): relaunch the same `scriptPath` and args with `resumeFromRunId`. Finished agents come back from cache; the retry wrapper already tells a re-run agent to continue from partial files.
- **You stopped a run and started a new one:** add the old run id to `superseded` in the control-room config with one line on why.
- **An agent died, but another finished its work and you checked it:** add its label to `covered` with the evidence. Never for work you have not checked.
- **An agent ran outside a workflow:** append it to `extra-agents-<slug>.json` so the page stays complete.
- **The owner says the page is wrong:** fix the run file and re-run `init_run.py --force`, or fix the control-room config. Explaining the error is not enough.

## References

- `references/run-config.md`: every key of the run file, with defaults and the lean and full presets.
- `references/environment.md`: the environment the builders need, with a Frappe bench pattern.
- `references/lessons.md`: what went wrong in real runs and how the templates guard against it. Read it once per project.
