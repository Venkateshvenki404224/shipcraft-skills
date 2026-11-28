# Lessons from real runs (and how the templates handle them)

Read once per project. Add to it when a run teaches something new.

## Running the team

- **Agents die mid-task** (network resets, usage limits); one drop took out three agents at once. → `ragent()` retries twice and tells the retry to continue from partial files. If a whole run stops, resume it (`resumeFromRunId`) instead of starting over, and mark a replaced run `superseded` in the control room.
- **Parallel agents edited the same files** in a plain dependency DAG. → Plan §9 gives every file one owner role, and the scheduler runs **one agent per role at a time**. Cross-role edits are small, additive, and logged in `build-messages.md`.
- **"Done" that wasn't.** → Statuses are `done` / `built` / `partial` / `blocked`; `built` means waiting on another ticket. A close-out pass re-verifies every ticket that is not `done` once everything has run.
- **Agents re-planned during the build.** → Builders are told the plan is final; rulings in plan §10.2 override the other documents; contract changes go to `41-api-changes.md`, not into silent workarounds.
- **The owner could not see what was going on.** → The control room from the start, one page per run family (`include_runs`), and honest `superseded` / `covered` entries.
- **Token cost.** Running every role on the strongest model costs roughly three times the lean preset for little gain on build tickets. → Strong models judge (plan, scope, verify, sign-off); mid models build; small models research.

## Frappe specifics

- Every builder gets these security rules (plan §8): role check first in every whitelisted method, POST for writes, explicit field lists, no `allow_guest`, no `ignore_permissions`, no `ignore_csrf`, escaped prints, no `v-html`.
- **Upstream apps can have holes too.** Whitelisted methods in the apps you build on may build SQL from user input or skip company/branch checks. → The verifier probes the upstream methods your roles can reach, and your app guards or blocks them. Report what you find to the upstream maintainers privately.
- **Multi-company as branches** (Companies + User Permissions): probe isolation for every method, and do not add a second Company to the demo site by accident.
- **Test as each non-admin user.** A screen is done only when its own user can do the job; Administrator hides permission bugs. If the product has its own UI, keep non-admins out of Desk.
- v16: Desk is at `/desk` (`/app` redirects). DocType JSON, custom fields and print formats need `migrate`; background-job code needs a restart.
- Prints in non-Latin scripts need the right fonts and a check in the PDF renderer you ship; some renderers shape them badly.

## Demo

- Seed data is invented and obviously fake; the reset script moves dates to today.
- The done gate is numbered and checkable (for example: the e2e spec passes after a reset, three clean runs in a row, the permission matrix has 0 FAIL, the prints are checked). The CEO's sign-off reads the gate results, not the agents' claims.
- Never call a rule-based feature "AI".
