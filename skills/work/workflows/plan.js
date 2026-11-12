export const meta = {
  name: 'work-plan',
  description: '/work: research the request, write the plan, and have an approval agent check it before the owner sees it',
  whenToUse: 'Started by the /work skill after intake. args: {run, issue, title, today, skill, profile}',
  phases: [
    { title: 'Research', detail: 'scope the request, then one reader per area plus outside facts' },
    { title: 'Plan', detail: 'planner writes plan.md, tickets.json, test-plan.json, ui/pages.json' },
    { title: 'Approve', detail: 'approval agent checks the plan; up to 2 revisions' },
  ],
}

// Copied per run to .agent/workflow/plan.js by the /work skill. Everything project-specific comes in through
// args.profile (the repo's .claude/work.json); the date comes in through args, never the clock.
const A = args || {}
const P = A.profile || {}
const NAME = P.project || 'the project'
const SKILL = A.skill || '.claude/skills/work'
const ISSUE = A.issue || '.agent/issue.md'
const RULES = (P.rules || ['CLAUDE.md']).join(', ')
const ROLES = (P.roles || []).join(', ') || '(no user roles: the project has no app UI)'
const HAS_APP = !!(P.app && P.app.url)
const M = P.models || {}
const MODELS = { scope: M.research || 'sonnet', research: M.research || 'sonnet', outside: M.research || 'sonnet', plan: M.plan || 'opus', approve: M.approve || 'opus' }
const MAX_REVISIONS = 2

const SCOPE = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    areas: {
      type: 'array', maxItems: 6,
      items: { type: 'object', properties: { name: { type: 'string' }, paths: { type: 'array', items: { type: 'string' } }, question: { type: 'string' } },
               required: ['name', 'paths', 'question'] },
    },
    outside: { type: 'array', maxItems: 4, items: { type: 'string' } },
    ui: { type: 'boolean' },
    roles: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'areas', 'outside', 'ui', 'roles'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    facts: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, evidence: { type: 'string' } }, required: ['claim', 'evidence'] } },
    reuse: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'facts', 'reuse', 'risks'],
}
const PLAN = {
  type: 'object',
  properties: {
    files_written: { type: 'array', items: { type: 'string' } },
    tickets: { type: 'integer' }, tests: { type: 'integer' },
    risk: { type: 'string', enum: ['low', 'medium', 'high'] },
    ui: { type: 'boolean' },
    roles: { type: 'array', items: { type: 'string' } },
    specs: { type: 'string', description: 'the test files or folder for this feature, as they go into the e2e command' },
    questions: { type: 'array', items: { type: 'object', properties: { q: { type: 'string' }, default: { type: 'string' } }, required: ['q', 'default'] } },
    summary: { type: 'string' },
  },
  required: ['files_written', 'tickets', 'tests', 'risk', 'ui', 'roles', 'specs', 'questions', 'summary'],
}
const APPROVAL = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'REVISE'] },
    unmapped: { type: 'array', items: { type: 'string' }, description: 'sentences of the request that no ticket covers and the plan does not mark out of scope' },
    issues: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, what: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'what', 'fix'] } },
    risk_ok: { type: 'boolean' },
  },
  required: ['verdict', 'unmapped', 'issues', 'risk_ok'],
}

// ---------------------------------------------------------------- Research
phase('Research')
const scope = await agent(
  `Read ${ISSUE} (the owner's request for ${NAME}, run ${A.run}). Do not plan yet. Decide what must be researched:
- areas: up to 6 parts of THIS repo the feature touches or must reuse (name, the paths to read, one question each). Prefer existing scripts, components and endpoints over new ones.
- outside: up to 4 questions that need facts from outside the repo (library or framework behaviour, API docs). Empty if none.
- ui: true if users will see any change (templates, components, styles, copy).${HAS_APP ? '' : ' This project has no app URL in its profile, so ui is false unless the request says otherwise.'}
- roles: which of these are affected: ${ROLES}.`,
  { label: 'scope', phase: 'Research', schema: SCOPE, model: MODELS.scope, effort: 'low' })
if (!scope) throw new Error('scope agent returned nothing')
log(`${scope.areas.length} areas, ${scope.outside.length} outside questions, ui=${scope.ui}`)

const research = (await parallel([
  ...scope.areas.map((a) => () => agent(
    `Research one area of the ${NAME} repo for the request in ${ISSUE}. Area: ${a.name}. Start with: ${a.paths.join(', ')}.
Question: ${a.question}
Return facts with path:line evidence only (no guesses), what can be reused as-is, and risks (shared files, auth and role checks, rules in ${RULES}). Read-only: change nothing.`,
    { label: `research:${a.name}`, phase: 'Research', schema: FINDINGS, model: MODELS.research })),
  ...scope.outside.map((q, i) => () => agent(
    `Answer from primary sources (official docs, release notes), with the URL for each fact and the version it applies to. Say "not documented" rather than guess. Question: ${q}`,
    { label: `outside:${i + 1}`, phase: 'Research', schema: FINDINGS, model: MODELS.outside })),
])).filter(Boolean)
log(`research: ${research.length} reports`)

// ---------------------------------------------------------------- Plan
phase('Plan')
const planPrompt = (extra) => `You are the planner for ${NAME} run ${A.run} (${A.title || ''}), today ${A.today || ''}.
Read ${ISSUE}, ${SKILL}/references/pipeline.md (sections "Plan check", "Test rules", "UI before / after"), the project rules (${RULES}),
the project profile .claude/work.json, and these research reports:
${JSON.stringify(research)}

Write these files (create .agent/ui/ only if ui):
- .agent/research.md: the research above, merged and deduplicated, with evidence.
- .agent/plan.md: goal; a table mapping EVERY sentence of the request to a ticket or to "out of scope"; design; the test contract (for UI: the exact data-* or role/label hooks tests will use, and which component gets each; for APIs/CLIs: the exact calls and outputs); roles affected and how each is checked; risk tier with the reason; expected visible changes, one line per page (ui only); at most 4 open questions, each with a proposed default.
- .agent/tickets.json: [{"id":"T1","title":"...","kind":"test|impl|docs","files":["..."],"deps":["T0"],"acceptance":["Given/When/Then"],"model":"sonnet"}]. Test tickets come first and depend on nothing but fixtures. Tickets that share a file must depend on each other.
- .agent/test-plan.json: unit/script checks and end-to-end cases with ids, role, browser list (from the profile's e2e.browsers), and which ticket each covers; include cross-page state cases for anything that navigates and skip cases for role-gated steps.
- .agent/ui/pages.json (only if ui): pages, roles, viewports, themes, hide/mask, in the format at the top of ${SKILL}/scripts/ui-snap/spec.ts.${P.ui_snap && P.ui_snap.theme_key ? ` Set "theme_key": "${P.ui_snap.theme_key}".` : ''}${P.ui_snap && P.ui_snap.hide && P.ui_snap.hide.length ? ` Default "hide": ${JSON.stringify(P.ui_snap.hide)}.` : ''}
Return "specs": the test files or folder of this feature, as they go into the profile's e2e command.
Do not write product code.${extra || ''}`
let plan = await agent(planPrompt(), { label: 'plan', phase: 'Plan', schema: PLAN, model: MODELS.plan })
if (!plan) throw new Error('planner returned nothing')

// ---------------------------------------------------------------- Approve
phase('Approve')
let approval = null
for (let round = 0; round <= MAX_REVISIONS; round++) {
  approval = await agent(
    `You are the approval agent: check the plan before the owner sees it. Read ${ISSUE}, .agent/plan.md, .agent/tickets.json, .agent/test-plan.json${plan.ui ? ', .agent/ui/pages.json' : ''}, and ${SKILL}/references/pipeline.md "Plan check".
REVISE if any of these fail, else APPROVE:
1. Every sentence of the request maps to a ticket or an explicit "out of scope" (list unmapped sentences verbatim).
2. At most 4 open questions, each with a default.
3. The test contract names exact hooks or calls, and test cases use only those.
4. Each affected role has tests; navigation has cross-page state cases; role-gated steps have skip cases.
5. Tickets touching the same file depend on each other; test tickets come before implementation.
6. The risk tier fits (shared layout, auth, session, payment or data-migration code is at least medium).
7. Nothing breaks the project rules in ${RULES}${P.review_rules ? ` or the BLOCKING rules in ${P.review_rules}` : ''}.
${plan.ui ? '8. pages.json covers every page in "expected visible changes", for the affected roles.' : '8. ui=false really means no user-visible change.'}
Verify claims against the code; do not trust the plan's own summary.`,
    { label: `approve:${round + 1}`, phase: 'Approve', schema: APPROVAL, model: MODELS.approve })
  if (!approval || approval.verdict === 'APPROVE') break
  if (round === MAX_REVISIONS) { log('approval still REVISE after 2 revisions; the owner decides at H1'); break }
  log(`revision ${round + 1}: ${approval.issues.length} issues, ${approval.unmapped.length} unmapped`)
  plan = (await agent(planPrompt(`

REVISION ${round + 1}: the approval agent asked for changes. Fix every item, then rewrite the files:
${JSON.stringify({ unmapped: approval.unmapped, issues: approval.issues })}`),
    { label: `plan:rev${round + 1}`, phase: 'Plan', schema: PLAN, model: MODELS.plan })) || plan
}

return { scope: { summary: scope.summary, ui: scope.ui, roles: scope.roles }, plan, approval }
