export const meta = {
  name: 'work-plan',
  description: '/work: research, PM brief, CEO scope check, architect plan, UI/UX design, senior dev feasibility, PM decisions, then a verifier and an approval agent check the plan',
  whenToUse: 'Started by the /work skill after intake. args: {run, issue, title, today, skill, profile}',
  phases: [
    { title: 'Research', detail: 'scope the request, then one reader per area plus outside facts' },
    { title: 'Product', detail: 'PM writes the brief; the CEO checks scope and business fit' },
    { title: 'Plan', detail: 'the architect writes plan.md, tickets.json, test-plan.json, ui/pages.json' },
    { title: 'Design', detail: 'UI/UX designer writes ui/design.md; the CEO reviews it (UI runs only)' },
    { title: 'Feasibility', detail: 'senior developers check the plan against the code and the framework' },
    { title: 'Decisions', detail: 'PM decides every open question; the architect folds the decisions in' },
    { title: 'Approve', detail: 'a verifier and an approval agent check the plan; up to 2 revisions' },
  ],
}

// Copied per run to .agent/workflow/plan.js by the /work skill. Everything project-specific comes in through
// args.profile (the repo's work profile; its location is args.profilePath); the date comes in through args, never the clock.
// The agent team (PM, CEO, UI/UX designer, senior developers) is on by default; the profile's "team" turns parts off.
const A = args || {}
const P = A.profile || {}
const NAME = P.project || 'the project'
const SKILL = A.skill || '.claude/skills/work'
const ISSUE = A.issue || '.agent/issue.md'
const RULES = (P.rules || ['CLAUDE.md']).join(', ')
const ROLES = (P.roles || []).join(', ') || '(no user roles: the project has no app UI)'
const HAS_APP = !!(P.app && P.app.url)
const AUTO = P.autonomy === 'agents'
// Models come only from the profile (no defaults in this script). Setup detects the host (Claude, Codex, Copilot...),
// lists the models it offers and writes models + model_fallback into the profile. A role with no model uses model_fallback.
const M = P.models || {}
const FB = P.model_fallback
const MISSING = ['plan', 'approve', 'research', 'work'].filter((k) => !(M[k] || FB))
if (MISSING.length) throw new Error(`profile has no model for: ${MISSING.join(', ')}, and no model_fallback. Run the model setup (references/setup.md, "Models") and pass the profile again.`)
const PLAN_M = M.plan || FB, APPROVE_M = M.approve || FB
const MODELS = {
  scope: M.research || FB, research: M.research || FB, plan: PLAN_M, approve: APPROVE_M,
  verify: M.verify || APPROVE_M, pm: M.pm || PLAN_M, ceo: M.ceo || PLAN_M,
  design: M.design || PLAN_M, senior: M.senior || APPROVE_M,
}
const TEAM = P.team === false ? { pm: false, ceo: false, design: false, senior: false } : (P.team || {})
const PM_ON = TEAM.pm !== false
const CEO_ON = TEAM.ceo !== false
const DESIGN_ON = TEAM.design !== false
const STACK = TEAM.stack || P.stack || ''
const SENIORS = TEAM.senior === false ? [] : (Array.isArray(TEAM.senior) && TEAM.senior.length ? TEAM.senior : ['Senior dev', ...(STACK ? [`Senior ${STACK} dev`] : [])])
const BUSINESS = TEAM.business ? `\nWhat the business sells and to whom (from the profile): ${TEAM.business}` : ''
const DESIGN_SYSTEM = (P.ui && P.ui.design_system) || TEAM.design_system || []
const MAX_REVISIONS = 2

// ---------------------------------------------------------------- helpers
// An agent that dies on an API error returns null: try it up to 3 times before giving up on that step.
async function run(prompt, opts) {
  for (let i = 0; i < 3; i++) {
    const r = await agent(prompt, { ...opts, label: i ? `${opts.label} (retry ${i})` : opts.label })
    if (r) return r
    log(`${opts.label}: no result, attempt ${i + 1}/3`)
  }
  return null
}
const S = (props, req) => ({ type: 'object', properties: props, required: req || Object.keys(props) })
const STR = { type: 'string' }, BOOL = { type: 'boolean' }, INT = { type: 'integer' }
const STRS = { type: 'array', items: STR }
const ISSUES = { type: 'array', items: S({ severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, what: STR, fix: STR }) }

const SCOPE = S({
  summary: STR,
  areas: { type: 'array', maxItems: 6, items: S({ name: STR, paths: STRS, question: STR }) },
  outside: { type: 'array', maxItems: 4, items: STR },
  ui: BOOL, roles: STRS,
})
const FINDINGS = S({ area: STR, facts: { type: 'array', items: S({ claim: STR, evidence: STR }) }, reuse: STRS, risks: STRS })
const PRD = S({ summary: STR, users: STRS, acceptance: STRS, non_goals: STRS, questions: { type: 'array', items: S({ q: STR, default: STR }) } })
const CEO = S({ verdict: { type: 'string', enum: ['GO', 'CUT', 'NO_GO'] }, must_haves: STRS, cuts: STRS, risks: STRS, never_claim: STRS, summary: STR })
const PLAN = S({
  files_written: STRS, tickets: INT, tests: INT,
  risk: { type: 'string', enum: ['low', 'medium', 'high'] }, ui: BOOL, roles: STRS,
  specs: { type: 'string', description: 'the test files or folder for this feature, as they go into the e2e command' },
  questions: { type: 'array', items: S({ q: STR, default: STR }) }, summary: STR,
})
const DESIGN = S({ pages: INT, states: STRS, hooks_added: STRS, reused: STRS, summary: STR })
const REVIEW = S({ verdict: { type: 'string', enum: ['APPROVE', 'REVISE'] }, notes: ISSUES, summary: STR })
const FEAS = S({ who: STR, verdict: { type: 'string', enum: ['FEASIBLE', 'CHANGES'] }, issues: ISSUES, reuse: STRS, effort: STR, summary: STR })
const DECISIONS = S({ decisions: { type: 'array', items: S({ q: STR, decision: STR, reason: STR }) }, rejected: STRS, summary: STR })
const APPROVAL = S({
  verdict: { type: 'string', enum: ['APPROVE', 'REVISE'] },
  unmapped: { type: 'array', items: STR, description: 'sentences of the request that no ticket covers and the plan does not mark out of scope' },
  issues: ISSUES, fixed_in_place: STRS, risk_ok: BOOL, summary: STR,
}, ['verdict', 'unmapped', 'issues', 'risk_ok', 'summary'])

const out = { stopped: null }

// ---------------------------------------------------------------- Research
phase('Research')
const scope = await run(
  `Read ${ISSUE} (the owner's request for ${NAME}, run ${A.run}). Do not plan yet. Decide what must be researched:
- areas: up to 6 parts of THIS repo the feature touches or must reuse (name, the paths to read, one question each). Prefer existing scripts, components and endpoints over new ones.
- outside: up to 4 questions that need facts from outside the repo (library or framework behaviour, API docs). Empty if none.
- ui: true if users will see any change (templates, components, styles, copy).${HAS_APP ? '' : ' This project has no app URL in its profile, so ui is false unless the request says otherwise.'}
- roles: which of these are affected: ${ROLES}.`,
  { label: 'Scope: the request', phase: 'Research', schema: SCOPE, model: MODELS.scope, effort: 'low' })
if (!scope) throw new Error('scope agent returned nothing')
log(`${scope.areas.length} areas, ${scope.outside.length} outside questions, ui=${scope.ui}`)
out.scope = { summary: scope.summary, ui: scope.ui, roles: scope.roles }

const research = (await parallel([
  ...scope.areas.map((a) => () => run(
    `Research one area of the ${NAME} repo for the request in ${ISSUE}. Area: ${a.name}. Start with: ${a.paths.join(', ')}.
Question: ${a.question}
Return facts with path:line evidence only (no guesses), what can be reused as-is, and risks (shared files, auth and role checks, rules in ${RULES}). Read-only: change nothing.`,
    { label: `Researcher: ${a.name}`, phase: 'Research', schema: FINDINGS, model: MODELS.research })),
  ...scope.outside.map((q, i) => () => run(
    `Answer from primary sources (official docs, release notes), with the URL for each fact and the version it applies to. Say "not documented" rather than guess. Question: ${q}`,
    { label: `Researcher: outside ${i + 1}`, phase: 'Research', schema: FINDINGS, model: MODELS.research })),
])).filter(Boolean)
log(`research: ${research.length} reports`)

// ---------------------------------------------------------------- Product: PM brief, CEO scope check
if (PM_ON || CEO_ON) phase('Product')
if (PM_ON) {
  out.prd = await run(
    `You are the product manager for ${NAME}, run ${A.run} (${A.title || ''}), today ${A.today || ''}.${BUSINESS}
Read ${ISSUE}, the project rules (${RULES}) and these research reports:
${JSON.stringify(research)}
Write .agent/prd.md, a short product brief (no design, no code):
- the problem and who has it (the users and roles: ${ROLES});
- what the user can do when this ships, as acceptance criteria in Given/When/Then, each one testable;
- non-goals: what this run does not do;
- where the user finds it (the entry point: a menu item, a link, a button). A feature nobody can find does not count as shipped;
- the copy rules: names, tone, words the product never uses;
- at most 4 open questions, each with a proposed default.
Base every claim about what exists on the research, not on guesses. Return the same content.`,
    { label: 'PM: product brief', phase: 'Product', schema: PRD, model: MODELS.pm })
}
if (CEO_ON) {
  out.ceo = await run(
    `You are the CEO of ${NAME}. You decide whether this work is worth doing now and what it must include.${BUSINESS}
Read ${ISSUE}${PM_ON ? ', .agent/prd.md' : ''} and these research reports:
${JSON.stringify(research)}
Judge as the owner of the business, not as an engineer:
- GO: build it as asked. CUT: build it without the parts in "cuts" (name each one and why). NO_GO: do not build it (say why; the owner decides).
- must_haves: what the first version cannot ship without (for example: the entry point, the error states, the role checks).
- risks: to customers, money, data, trust or the law.
- never_claim: what the product copy must never promise (for example an uptime figure, a price comparison, a feature that does not exist).
Write .agent/ceo.md with the verdict and these lists, short. Return the same.`,
    { label: 'CEO: scope and business fit', phase: 'Product', schema: CEO, model: MODELS.ceo })
  if (out.ceo && out.ceo.verdict === 'NO_GO') {
    out.stopped = 'ceo'
    log(`CEO: NO_GO. ${out.ceo.summary}`)
    return out
  }
}

// ---------------------------------------------------------------- Plan
phase('Plan')
const productFiles = [PM_ON && '.agent/prd.md', CEO_ON && '.agent/ceo.md'].filter(Boolean)
const planPrompt = (extra) => `You are the architect for ${NAME} run ${A.run} (${A.title || ''}), today ${A.today || ''}.
Read ${ISSUE}, ${productFiles.length ? `${productFiles.join(', ')} (the product brief and the CEO's scope: honour the cuts and must-haves), ` : ''}${SKILL}/references/pipeline.md (sections "Plan check", "Test rules", "UI before / after"), the project rules (${RULES}),
the project profile (${A.profilePath || '.work-profile/work.json'}), and these research reports:
${JSON.stringify(research)}

Write these files (create .agent/ui/ only if ui):
- .agent/research.md: the research above, merged and deduplicated, with evidence.
- .agent/plan.md: goal; a table mapping EVERY sentence of the request${PM_ON ? ' and every acceptance criterion of prd.md' : ''} to a ticket or to "out of scope"; design; the test contract (for UI: the exact data-* or role/label hooks tests will use, and which component gets each; for APIs/CLIs: the exact calls and outputs); roles affected and how each is checked; risk tier with the reason; expected visible changes, one line per page (ui only); at most 4 open questions, each with a proposed default.
- .agent/tickets.json: [{"id":"T1","title":"...","kind":"test|impl|docs","role":"test|backend|frontend|ui|data|docs","files":["..."],"deps":["T0"],"acceptance":["Given/When/Then"],"model":"${M.work || FB}"}]. "role" says which developer builds it: backend (server code, APIs, jobs, permissions), frontend (pages, components, client code), ui (styles, layout, copy, design-system work), data (migrations, fixtures, seed data), docs, test. Test tickets come first and depend on nothing but fixtures. Tickets that share a file must depend on each other.
- .agent/test-plan.json: unit/script checks and end-to-end cases with ids, role, browser list (from the profile's e2e.browsers), and which ticket each covers; include cross-page state cases for anything that navigates and skip cases for role-gated steps.
- .agent/ui/pages.json (only if ui): pages, roles, viewports, themes, hide/mask, in the format at the top of ${SKILL}/scripts/ui-snap/spec.ts.${P.ui_snap && P.ui_snap.theme_key ? ` Set "theme_key": "${P.ui_snap.theme_key}".` : ''}${P.ui_snap && P.ui_snap.hide && P.ui_snap.hide.length ? ` Default "hide": ${JSON.stringify(P.ui_snap.hide)}.` : ''}
Return "specs": the test files or folder of this feature, as they go into the profile's e2e command.
Do not write product code.${extra || ''}`
let plan = await run(planPrompt(), { label: 'Architect: plan', phase: 'Plan', schema: PLAN, model: MODELS.plan })
if (!plan) throw new Error('architect returned nothing')

// ---------------------------------------------------------------- Design (UI runs)
if (DESIGN_ON && plan.ui) {
  phase('Design')
  const designPrompt = (extra) => `You are the UI/UX designer for ${NAME} run ${A.run}. Read ${ISSUE}, ${[...productFiles, '.agent/plan.md', '.agent/ui/pages.json'].join(', ')}, the project rules (${RULES})${DESIGN_SYSTEM.length ? ` and the design system: ${DESIGN_SYSTEM.join(', ')}` : ''}.
Look at the pages the feature changes as they are today (read their templates or components; open them in a browser if the app runs${HAS_APP ? ` at ${P.app.url}` : ''}).
Write .agent/ui/design.md, one section per page or component:
- layout and hierarchy: what the user sees first, and the one main action;
- the components it reuses from the project's own design system (name the file). No new UI library; a new component only when nothing fits, and say why;
- every state: empty, loading, error, no permission, long text, many rows, success;
- copy: the exact labels, buttons, messages and empty-state text, in the product's voice;
- phone width (390 px): what stacks, what hides, no sideways scroll; dark mode; keyboard order and focus; labels for screen readers;
- the entry point: how the user reaches it from where they already are.
If the plan's test contract lacks a hook a state needs, add the hook to the test contract section of .agent/plan.md and list it. Do not write product code.${extra || ''}`
  out.design = await run(designPrompt(), { label: 'UI/UX designer: design', phase: 'Design', schema: DESIGN, model: MODELS.design })
  if (CEO_ON && out.design) {
    out.designReview = await run(
      `You are the CEO of ${NAME}. Review the UI design in .agent/ui/design.md against .agent/ceo.md${PM_ON ? ' and .agent/prd.md' : ''}.${BUSINESS}
Would a paying customer understand it in 5 seconds, find it from where they are, and trust it? Is anything promised that the product does not do?
APPROVE, or REVISE with concrete notes (what to change, not "make it better").`,
      { label: 'CEO: design review', phase: 'Design', schema: REVIEW, model: MODELS.ceo })
    if (out.designReview && out.designReview.verdict === 'REVISE') {
      out.design = (await run(designPrompt(`

REVISION: the CEO asked for these changes. Apply each one, then rewrite .agent/ui/design.md:
${JSON.stringify(out.designReview.notes)}`), { label: 'UI/UX designer: revise design', phase: 'Design', schema: DESIGN, model: MODELS.design })) || out.design
    }
  }
}

// ---------------------------------------------------------------- Feasibility
if (SENIORS.length) {
  phase('Feasibility')
  out.feasibility = (await parallel(SENIORS.map((who) => () => run(
    `You are the ${who} on ${NAME} run ${A.run}.${who !== 'Senior dev' && STACK ? ` You know ${STACK} deeply: its idioms, its permission model, its upgrade path and what it already gives for free.` : ''}
Read .agent/plan.md, .agent/tickets.json, .agent/test-plan.json${plan.ui && DESIGN_ON ? ', .agent/ui/design.md' : ''} and the code they name. Check feasibility against the real code, not the plan's summary:
- does each ticket fit how this codebase already does the same thing (name the existing file to copy from)?
- what is missing: migrations, permissions, caching, background jobs, upgrade steps, config, docs?
- what will break: shared files, other callers, existing tests, performance at real data sizes?
- is the ticket split right (file ownership, dependencies), and is the effort realistic?
FEASIBLE, or CHANGES with each issue (severity, what, the fix). Read-only: change nothing.`,
    { label: `${who}: feasibility`, phase: 'Feasibility', schema: FEAS, model: MODELS.senior })))).filter(Boolean)
  log(`feasibility: ${out.feasibility.map((f) => `${f.who} ${f.verdict}`).join(', ')}`)
}

// ---------------------------------------------------------------- Decisions
const feasIssues = (out.feasibility || []).flatMap((f) => f.issues.map((i) => ({ ...i, from: f.who })))
if (PM_ON || feasIssues.length) {
  phase('Decisions')
  if (PM_ON) {
    out.decisions = await run(
      `You are the product manager for ${NAME} run ${A.run}. Make the product calls so the plan has no open questions left.${BUSINESS}
Read .agent/prd.md${CEO_ON ? ', .agent/ceo.md' : ''}, .agent/plan.md (its open questions)${plan.ui && DESIGN_ON ? ', .agent/ui/design.md' : ''}, and these issues from the senior developers:
${JSON.stringify(feasIssues)}
For every open question in plan.md and prd.md: decide (take the default or choose another answer), with the reason in one line.
For every developer issue that changes what the user gets: accept or reject it, with the reason.
${AUTO ? 'Nobody approves after you: your decisions are final for this run.' : 'Your decisions are the recommended answers the owner sees at H1; the owner can change them.'}
Write .agent/pm.md with the decisions. Return them.`,
      { label: 'PM: decide the open questions', phase: 'Decisions', schema: DECISIONS, model: MODELS.pm })
  }
  plan = (await run(planPrompt(`

DECISIONS: fold these into the files, then rewrite them. ${PM_ON ? 'Apply every decision in .agent/pm.md; open questions it answered are no longer open.' : ''}
Apply the developers' issues${PM_ON ? ' the PM did not reject' : ''}:
${JSON.stringify(feasIssues)}`), { label: 'Architect: apply decisions', phase: 'Decisions', schema: PLAN, model: MODELS.plan })) || plan
}

// ---------------------------------------------------------------- Approve: verifier + approval agent
phase('Approve')
const checklist = `1. Every sentence of the request${PM_ON ? ' and every acceptance criterion in .agent/prd.md' : ''} maps to a ticket or an explicit "out of scope" (list unmapped ones verbatim).
2. At most 4 open questions, each with a default${PM_ON ? ' (questions .agent/pm.md decided are closed)' : ''}.
3. The test contract names exact hooks or calls, and test cases use only those.
4. Each affected role has tests; navigation has cross-page state cases; role-gated steps have skip cases.
5. Tickets touching the same file depend on each other; test tickets come before implementation; each ticket has a role.
6. The risk tier fits (shared layout, auth, session, payment or data-migration code is at least medium).
7. Nothing breaks the project rules in ${RULES}${P.review_rules ? ` or the BLOCKING rules in ${P.review_rules}` : ''}${CEO_ON ? ', the CEO\'s cuts and must-haves in .agent/ceo.md, or its never_claim list' : ''}.
${plan.ui ? `8. pages.json covers every page in "expected visible changes", for the affected roles${DESIGN_ON ? '; every state in .agent/ui/design.md has a test or a screenshot' : ''}.` : '8. ui=false really means no user-visible change.'}`
const files = [ISSUE, ...productFiles, '.agent/plan.md', '.agent/tickets.json', '.agent/test-plan.json', ...(plan.ui ? ['.agent/ui/pages.json'] : []), ...(plan.ui && DESIGN_ON ? ['.agent/ui/design.md'] : []), ...(PM_ON ? ['.agent/pm.md'] : [])]
let approval = null, verifier = null
for (let round = 0; round <= MAX_REVISIONS; round++) {
  ;[verifier, approval] = await parallel([
    () => run(
      `You are the plan verifier: an adversarial reviewer. Read ${files.join(', ')} and ${SKILL}/references/pipeline.md "Plan check".
Try to break the plan against the real code: wrong file paths, functions that do not exist, a permission check that is missing, a test that cannot fail, a ticket that cannot be built from what it owns.
Fix small, certain mistakes in the plan files in place (a wrong path, a missing dependency) and list them under fixed_in_place. Report the rest.
Then check:
${checklist}
APPROVE only if nothing blocker or major is left. Verify claims against the code; do not trust the plan's own summary.`,
      { label: `Verifier: plan r${round + 1}`, phase: 'Approve', schema: APPROVAL, model: MODELS.verify }),
    () => run(
      `You are the approval agent: check the plan before ${AUTO ? 'the build starts (nobody else approves it)' : 'the owner sees it'}. Read ${files.join(', ')} and ${SKILL}/references/pipeline.md "Plan check".
REVISE if any of these fail, else APPROVE:
${checklist}
Verify claims against the code; do not trust the plan's own summary. Change nothing.`,
      { label: `Approver: plan r${round + 1}`, phase: 'Approve', schema: APPROVAL, model: MODELS.approve }),
  ])
  const both = [verifier, approval].filter(Boolean)
  if (both.every((v) => v.verdict === 'APPROVE')) break
  if (round === MAX_REVISIONS) { log(`plan still REVISE after ${MAX_REVISIONS} revisions; ${AUTO ? 'reported in the result' : 'the owner decides at H1'}`); break }
  const issues = both.flatMap((v) => v.issues), unmapped = both.flatMap((v) => v.unmapped)
  log(`revision ${round + 1}: ${issues.length} issues, ${unmapped.length} unmapped`)
  plan = (await run(planPrompt(`

REVISION ${round + 1}: the verifier and the approval agent asked for changes. Fix every item, then rewrite the files:
${JSON.stringify({ unmapped, issues })}`),
    { label: `Architect: revise r${round + 1}`, phase: 'Approve', schema: PLAN, model: MODELS.plan })) || plan
}

return { ...out, plan, approval, verifier, team: { pm: PM_ON, ceo: CEO_ON, design: DESIGN_ON && !!plan.ui, seniors: SENIORS }, autonomy: AUTO ? 'agents' : 'owner' }
