# The agent team

A /work run is staffed like a small product company. Each agent has one job, writes one file, and is labelled `<Role>: <task>` so the run board's team list shows who did what. The team is on by default; the profile's `team` turns members off (`references/setup.md`).

| Role | Stage | Model (profile `models`) | Reads | Writes | Job |
|---|---|---|---|---|---|
| Scope, Researcher | Research | `research` (sonnet) | the request, the code, primary docs | research reports (merged into `research.md`) | facts with path:line or URL evidence; what to reuse; risks |
| **PM** | Product | `pm` (else `plan`) | request, research | `.agent/prd.md` | the problem, users, acceptance criteria (Given/When/Then), the entry point, non-goals, copy rules, ≤4 questions with defaults |
| **CEO** | Product | `ceo` (else `plan`) | request, `prd.md`, research, `team.business` | `.agent/ceo.md` | GO / CUT / NO_GO; must-haves; business risks; what the product must never claim |
| **Architect** | Plan, Decisions, Approve | `plan` (opus) | all of the above | `plan.md`, `tickets.json`, `test-plan.json`, `ui/pages.json` | maps every request sentence and acceptance criterion to a ticket; the test contract; a developer `role` per ticket; folds in decisions and review fixes |
| **UI/UX designer** | Design (UI runs) | `design` (else `plan`) | `prd.md`, `ceo.md`, plan, today's pages, the design system | `.agent/ui/design.md` | layout, the reused components, every state, exact copy, phone width, dark mode, keyboard, the entry point; adds test hooks the states need |
| **CEO** (design review) | Design | `ceo` | `design.md`, `ceo.md`, `prd.md` | (verdict) | would a paying customer understand it, find it and trust it; one designer revision on REVISE |
| **Senior dev**, **Senior `<stack>` dev** | Feasibility | `senior` (else `approve`) | plan, tickets, the code | (issues) | fits the codebase's own patterns? missing migrations, permissions, jobs, upgrade steps? what breaks? effort |
| **PM** (decisions) | Decisions | `pm` | `prd.md`, `ceo.md`, plan questions, developer issues | `.agent/pm.md` | answers every open question and accepts or rejects each developer issue, with a reason. With `autonomy: owner` these are recommendations for H1; with `agents` they are final |
| **Verifier** | Approve | `verify` (else `approve`) | every plan file, the code | fixes in place | adversarial: tries to break the plan against the real code; fixes small certain mistakes, reports the rest |
| **Approver** | Approve | `approve` (opus) | every plan file | (verdict) | the plan check in `pipeline.md`; both verifier and approver must APPROVE |
| **Tester** | Tests first | ticket `model` (else `work`) | plan, test plan | test files | tests from the test contract only; fixes a wrong red run once |
| **Backend dev** | Implement | ticket `model` | plan | server code | auth and role checks on every endpoint and job, server validation, idempotent writes, the codebase's own patterns |
| **Frontend dev** | Implement | ticket `model` | plan, `design.md` | pages, components | builds to the design; reuses the project's components; escapes output; test hooks; every state |
| **UI dev** | Implement | ticket `model` | `design.md` | styles, layout, copy | the design exactly: spacing, copy, states, 390 px, dark mode, focus, screen-reader labels; no new UI library |
| **Data dev**, **Tech writer** | Implement | ticket `model` | plan | migrations and fixtures; docs | reversible migrations, removable test data; docs for the named reader |
| Gate, **Fixer** | Gate + E2E, Fix | `work` | gate output, findings | product files | runs the gate; fixes without weakening tests |
| **Verifier** (diff) | Verify | opus (low risk: `work`) | the diff, review rules | (findings) | one lens, or three at high risk: correctness, security and roles, UI rules |
| **QA: `<role>`** | Agent QA | `work` | plan, `prd.md`, test plan | `.agent/qa/<role>.json`, videos | explores as that role from where the role really starts; finds the feature the way a user would |
| **UI/UX designer** (shots) | UI after | `design` | before/after shots, `design.md` | `.agent/ui/review.json` | expected / unexpected / broken per changed shot, plus "does not match the design" |
| Evidence | Evidence | `work` | everything | `.agent/evidence.md` | the H2 report |
| **PM** (acceptance) | Sign-off | `pm` | `prd.md`, `pm.md`, evidence, QA | `.agent/pm-report.md` | each acceptance criterion met / partly / not met, with evidence; the entry point works |
| **CEO** (sign-off) | Sign-off | `ceo` | `ceo.md`, `pm-report.md`, evidence, QA | `.agent/ceo-signoff.md` | SHIP or HOLD with must-fix items. With `autonomy: agents` this replaces H2 |

## Why each role is there

- **PM before the plan.** Without acceptance criteria and an entry point, plans ship features nobody can find ("I don't see it in the UI"). The PM's brief is what QA and the sign-off check against.
- **CEO scope check.** Stops work that should not be built, cuts what the first version does not need, and keeps claims out of the product copy that the business cannot back (an uptime figure, a price comparison, a feature that is not built).
- **Designer before the developers.** Developers who guess the layout and copy get it rebuilt at review. A design file with every state and the exact copy gives the UI developers and the screenshot review one reference.
- **Senior developers.** The architect's plan often reinvents what the codebase or framework already has, or misses a migration, a permission or an upgrade step. Two readers (general, and one who knows the stack) catch both.
- **PM decisions.** Open questions are where an unattended run stalls. The PM answers them with reasons, and the owner sees them as defaults at H1.
- **Verifier and approver.** One fixes and attacks the plan against the code; the other checks the plan rules. Either one alone has let wrong paths or untestable cases through.
- **Developer roles per ticket.** A backend prompt that stresses role checks and idempotency, and a UI prompt that stresses the design and every state, catch different mistakes than one generic "developer".

## Turning members off

`"team": false` gives the lean pipeline: research → architect → verifier + approver → build, with no product, design or sign-off stages. Or turn members off one at a time: `"team": {"ceo": false}`, `{"design": false}`, `{"senior": false}`, `{"pm": false}`. Pass the same members to `state.py init --team-off` so the board shows them as SKIP.

## Models

Any alias the session supports (`opus`, `sonnet`, `haiku`, `fable`, …). When a role's model does not answer (every attempt returns nothing, or the agent hangs with no output), set another model for that role in the profile or the run's args and note it in the evidence (unattended runs: in `.agent/decisions.md`).
