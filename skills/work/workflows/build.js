export const meta = {
  name: 'work-build',
  description: '/work: tests first, backend/frontend/UI developers by ticket, gate + E2E, verify, per-role agent QA on video, UI/UX designer review of before/after shots, evidence, PM acceptance report and CEO sign-off',
  whenToUse: 'Started by the /work skill after the owner approves the plan (H1). args: see the top of the script',
  phases: [
    { title: 'Tests first', detail: 'test tickets, then a red run that must fail for the right reason' },
    { title: 'UI before', detail: 'screenshots of the affected pages on the base code (ui runs only)' },
    { title: 'Implement', detail: 'tickets in dependency waves; tickets sharing a file run one after another' },
    { title: 'Gate + E2E', detail: 'gate commands and end-to-end tests; up to the build fix-round budget' },
    { title: 'Verify', detail: 'risk-tiered review of the diff' },
    { title: 'Agent QA', detail: 'one explorer per role in a real browser, recorded on video' },
    { title: 'UI after', detail: 'after screenshots, diff and the UI review (ui runs only)' },
    { title: 'Fix', detail: 'one QA fix round for QA majors and unexpected/broken UI shots' },
    { title: 'Garden', detail: 'turns repeated findings into lint rules or structure tests; logs the rest' },
    { title: 'Evidence', detail: 'writes .agent/evidence.md for the owner (H2)' },
    { title: 'Sign-off', detail: 'PM checks every acceptance criterion; the CEO says SHIP or HOLD' },
  ],
}

// Copied per run to .agent/workflow/build.js by the /work skill. The run's shape comes from args:
// {run, today, skill, profile (the repo's work profile), tickets:[{id,title,kind,files,deps,acceptance,model}],
//  roles:["user","admin",...], risk:"low|medium|high", ui:bool, e2e:"command for this feature's tests",
//  uiSnap:"command with {phase} for before/after" (ui runs), video:bool, budgets:{build:2, qa:1},
//  mode:"build"|"fixup", fixup:{themes:"..."}}   ("fixup" = the owner's "one more fix round, then ship")
const A = args || {}
const P = A.profile || {}
const NAME = P.project || 'the project'
const SKILL = A.skill || '.claude/skills/work'
const T = A.tickets || []
const APP = P.app || {}
const ROLES = A.roles && A.roles.length ? A.roles : (P.roles && P.roles.length ? P.roles : [])
const RISK = A.risk || 'medium'
const BUDGET = { build: (A.budgets && A.budgets.build) ?? 2, qa: (A.budgets && A.budgets.qa) ?? 1 }
const GATE = (P.gate || []).map((c, i) => `${i + 1}. ${c}`).join('\n')
const E2E = A.e2e || (P.e2e && P.e2e.cmd) || ''
const BROWSERS = (P.e2e && P.e2e.browsers) || ['chromium']
const REVIEW_RULES = [P.review_rules, `${SKILL}/references/review-rules.md`].filter(Boolean).join(' and ')
const AUTO = P.autonomy === 'agents'
const M = P.models || {}
const FB = P.model_fallback
const MISSING = ['plan', 'approve', 'research', 'work'].filter((k) => !(M[k] || FB))
if (MISSING.length) throw new Error(`profile has no model for: ${MISSING.join(', ')}, and no model_fallback. Run the model setup (references/setup.md, "Models") and pass the profile again.`)
const W = M.work || FB
const APPROVE_M = M.approve || FB, PLAN_M = M.plan || FB
const VERIFY_M = M.verify || APPROVE_M
const PM_M = M.pm || PLAN_M, CEO_M = M.ceo || PLAN_M, DESIGN_M = M.design || PLAN_M
const TEAM = P.team === false ? { pm: false, ceo: false, design: false } : (P.team || {})
const PM_ON = TEAM.pm !== false, CEO_ON = TEAM.ceo !== false, DESIGN_ON = TEAM.design !== false
const STACK = TEAM.stack || P.stack || ''
const BUSINESS = TEAM.business ? ` What the business sells and to whom: ${TEAM.business}` : ''
const DESIGN_SYSTEM = (P.ui && P.ui.design_system) || TEAM.design_system || []
const FEATURE_MAP = P.feature_map || ''
const CASES = (A.testPlan && Array.isArray(A.testPlan.cases)) ? A.testPlan.cases : null
const UI_TICKETS = T.filter((t) => t.kind !== 'test' && (t.role === 'frontend' || t.role === 'ui'))
const E2E_COVERED = new Set((CASES || []).filter((c) => c.kind === 'e2e').flatMap((c) => c.covers || []))
const UNCOVERED_UI = CASES ? UI_TICKETS.filter((t) => !E2E_COVERED.has(t.id)).map((t) => t.id) : []
const EVALS = P.evals && P.evals.cmd ? { cmd: P.evals.cmd, paths: P.evals.paths || [] } : null
const GARDEN = P.garden === false ? null : { log: (P.garden && P.garden.log) || 'docs/garden.md', repeat: (P.garden && P.garden.repeat) || 2 }
const RULES = `Rules: follow the project rules (${(P.rules || ['CLAUDE.md']).join(', ')}). Never print secrets (${(P.secrets || ['.env*']).join(', ')}).
Do not commit, push or touch git history.`

// An agent that dies on an API error returns null: try it up to 3 times before giving up on that step.
async function run(prompt, opts) {
  for (let i = 0; i < 3; i++) {
    const r = await agent(prompt, { ...opts, label: i ? `${opts.label} (retry ${i})` : opts.label })
    if (r) return r
    log(`${opts.label}: no result, attempt ${i + 1}/3`)
  }
  return null
}

const DONE = { type: 'object', properties: { ticket: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['ticket', 'files_changed', 'notes'] }
const RED = { type: 'object', properties: { total: { type: 'integer' }, failing: { type: 'integer' }, passing_unexpectedly: { type: 'array', items: { type: 'string' } }, wrong_reason: { type: 'array', items: { type: 'string' } }, minutes: { type: 'number' } }, required: ['total', 'failing', 'passing_unexpectedly', 'wrong_reason', 'minutes'] }
const GATE_RES = {
  type: 'object',
  properties: {
    green: { type: 'boolean' },
    checks: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, result: { type: 'string' }, detail: { type: 'string' } }, required: ['name', 'result'] } },
    failures: { type: 'array', items: { type: 'object', properties: { where: { type: 'string' }, what: { type: 'string' } }, required: ['where', 'what'] } },
    flakes: { type: 'array', items: { type: 'string' } },
    browsers: { type: 'object', additionalProperties: { type: 'string' }, description: 'browser -> "PASS n/n" | "FAIL ..." | "NOT RUN (reason)"' },
  },
  required: ['green', 'checks', 'failures', 'flakes', 'browsers'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['SHIP', 'SHIP_AFTER_FIXES', 'BLOCK'] },
    findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] }, where: { type: 'string' }, what: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'where', 'what'] } },
  },
  required: ['verdict', 'findings'],
}
const QA = {
  type: 'object',
  properties: {
    role: { type: 'string' },
    passed: { type: 'array', items: { type: 'string' } },
    findings: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] }, title: { type: 'string' }, steps: { type: 'string' }, expected: { type: 'string' }, actual: { type: 'string' }, url: { type: 'string' }, screenshot: { type: 'string' }, existing_bug: { type: 'boolean' } }, required: ['id', 'severity', 'title', 'steps', 'expected', 'actual', 'existing_bug'] } },
    videos: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, kind: { type: 'string', enum: ['demo', 'qa'] }, seconds: { type: 'number' } }, required: ['file', 'kind'] } },
  },
  required: ['role', 'passed', 'findings', 'videos'],
}
const UIREV = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'CHANGES'] }, summary: { type: 'string' },
    counts: { type: 'object', additionalProperties: { type: 'integer' } },
    flagged: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, verdict: { type: 'string' }, note: { type: 'string' } }, required: ['id', 'verdict', 'note'] } },
  },
  required: ['verdict', 'summary', 'counts', 'flagged'],
}

const PMREP = { type: 'object', properties: { met: { type: 'integer' }, total: { type: 'integer' }, not_met: { type: 'array', items: { type: 'string' } }, entry_point_ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['met', 'total', 'not_met', 'entry_point_ok', 'summary'] }
const GARDEN_RES = { type: 'object', properties: { checks_added: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, file: { type: 'string' }, catches: { type: 'string' } }, required: ['rule', 'file', 'catches'] } }, logged: { type: 'array', items: { type: 'string' } }, skipped: { type: 'array', items: { type: 'object', properties: { finding: { type: 'string' }, why: { type: 'string' } }, required: ['finding', 'why'] } } }, required: ['checks_added', 'logged', 'skipped'] }
const SIGNOFF = { type: 'object', properties: { verdict: { type: 'string', enum: ['SHIP', 'HOLD'] }, reasons: { type: 'array', items: { type: 'string' } }, must_fix: { type: 'array', items: { type: 'string' } } }, required: ['verdict', 'reasons', 'must_fix'] }

// Who builds a ticket: tickets.json "role" (the architect sets it); "kind": "test" is always the test engineer.
const DEV = {
  test: { who: 'Tester', brief: 'You are the test engineer. Write the tests only, from the test contract; no product code. Cases with "kind": "property" are property-based tests (the project\'s property-testing library, or generated inputs in a loop when it has none) that check the invariant over many inputs or operation sequences. Never write a tautological test: each test must fail when the behaviour it names breaks.' },
  backend: { who: 'Backend dev', brief: `You are the backend developer${STACK ? ` (${STACK})` : ''}. Every endpoint and job checks who is calling and what they may do; validate input on the server; make writes idempotent where a retry or a double click can repeat them; follow how this codebase already does the same thing.` },
  frontend: { who: 'Frontend dev', brief: `You are the frontend developer. Build the pages and components to .agent/ui/design.md when it exists; reuse the project's components${DESIGN_SYSTEM.length ? ` (${DESIGN_SYSTEM.join(', ')})` : ''}; escape every output; put the test contract's hooks on the right elements; every state (empty, loading, error, no permission) works.` },
  ui: { who: 'UI dev', brief: `You are the UI developer. Follow .agent/ui/design.md exactly: layout, spacing, copy, every state, phone width 390 with no sideways scroll, dark mode, keyboard focus and screen-reader labels. Use the project's design system${DESIGN_SYSTEM.length ? ` (${DESIGN_SYSTEM.join(', ')})` : ''}; no new UI library.` },
  data: { who: 'Data dev', brief: 'You are the data developer. Migrations are reversible or say why not; fixtures and seed data are marked as test data and removable; never touch real data.' },
  docs: { who: 'Tech writer', brief: 'You are the technical writer. Write for the reader named in the ticket; short sentences; exact commands; no claims the code does not back.' },
}
const devOf = (t) => DEV[t.kind === 'test' ? 'test' : (t.role || (t.kind === 'docs' ? 'docs' : ''))] || { who: 'Developer', brief: 'You are the developer.' }

const ticketPrompt = (t) => `${devOf(t).brief}
Implement ticket ${t.id} of ${NAME} run ${A.run}: ${t.title}
Files you own: ${(t.files || []).join(', ') || '(see plan)'}. Acceptance: ${(t.acceptance || []).join(' | ')}
Read .agent/plan.md (design, test contract) and .agent/test-plan.json first. ${t.kind === 'test'
    ? 'Write the tests only. Use only the hooks and calls in the test contract; no product code.'
    : 'Make the tests for this ticket pass. Change only the files you own unless the plan says otherwise; no test edits unless a test contradicts the test contract (say so).'}
${RULES}`

// Dependency waves; inside a wave, tickets that share a file run one after another.
async function runTickets(list, phaseName) {
  const done = new Set(T.filter((t) => !list.includes(t)).map((t) => t.id))
  const left = [...list], results = []
  while (left.length) {
    const ready = left.filter((t) => (t.deps || []).every((d) => done.has(d)))
    if (!ready.length) { log(`dependency cycle or missing dep among ${left.map((t) => t.id).join(', ')}; running them in order`); ready.push(left[0]) }
    const batch = [], used = new Set()
    for (const t of ready) {
      const files = t.files || []
      if (files.some((f) => used.has(f))) continue
      files.forEach((f) => used.add(f)); batch.push(t)
    }
    const out = await parallel(batch.map((t) => () => run(ticketPrompt(t), { label: `${devOf(t).who}: ${t.id} ${t.title || ''}`.trim(), phase: phaseName, schema: DONE, model: t.model || W })))
    batch.forEach((t, i) => { done.add(t.id); left.splice(left.indexOf(t), 1); results.push(out[i] || { ticket: t.id, files_changed: [], notes: 'agent returned nothing' }) })
  }
  return results
}

const gate = (label, phaseName) => run(
  `Run the gate for ${NAME} run ${A.run} and report; do not fix anything.
Gate commands, in order (stop at nothing; run them all):
${GATE || '(the profile lists no gate commands: run the project\'s linters and unit tests as its README or CI config describes, and say which)'}
${E2E ? `Then the end-to-end tests: ${E2E}
Browsers expected: ${BROWSERS.join(', ')}. Per browser report PASS n/n, FAIL, or NOT RUN with the reason (a browser that is not installed is NOT RUN, never left out).` : 'There is no end-to-end command; report browsers as {}.'}
If a test fails and then passes on a rerun, rerun it 20 times; all pass = list it under flakes, any fail = failure.${EVALS ? `
AI evals: list the changed files (git diff --name-only HEAD plus untracked files). ${EVALS.paths.length ? `If any of them is under ${EVALS.paths.join(', ')}` : 'Always'}, run: ${EVALS.cmd}
Report it as a check named "eval" with its scores; a failing or regressed eval is a failure and makes green false. When no matching file changed, report the check as "eval" with result "SKIP (no AI files changed)".` : ''}`,
  { label: `Gate: ${label}`, phase: phaseName, schema: GATE_RES, model: W, effort: 'low' })

const fix = (label, phaseName, what) => run(
  `Fix round for ${NAME} run ${A.run}. Read .agent/plan.md. Fix these problems in the product code:
${JSON.stringify(what)}
Never weaken an assertion, widen a timeout or delete a test to make it pass; if a test is wrong against the test contract, fix the test and say why.
Return the files you changed. ${RULES}`,
  { label: `Fixer: ${label}`, phase: phaseName, schema: DONE, model: W })

const snapCmd = (ph) => (A.uiSnap || '').split('{phase}').join(ph)
const uiAfter = async (tag) => {
  const cap = await run(`Run the UI after capture: ${snapCmd('after')}
Report the counts printed by the teardown and any test that errored (an error is not a visual change). Do not change files.`,
    { label: `UI snap: after${tag}`, phase: 'UI after', model: W, effort: 'low' })
  const designer = DESIGN_ON && A.ui
  const rev = await run(
    `You are the ${designer ? 'UI/UX designer' : 'UI review agent'} for ${NAME} run ${A.run}. Read the "expected visible changes" in .agent/plan.md${FEATURE_MAP ? `, the screen names in ${FEATURE_MAP}` : ''}${designer ? ', the design in .agent/ui/design.md (when it exists)' : ''} and .agent/ui/shots.json.
For every shot whose status is not "unchanged", open its before, marked (the after image with a red box around each changed area) and diff
PNGs (paths are relative to .agent/ui/; "boxes" lists the changed areas) and judge each boxed area:
expected = the change is in the plan; unexpected = a change the plan did not ask for; broken = overlap, clipping, sideways scroll,
unreadable text, an empty state where data belongs, wrong data for the role${designer ? ', or a page that does not match .agent/ui/design.md (layout, copy, states, spacing, dark mode)' : ''}. A final_path that differs from the page is a redirect: check it
against the project's access rules (${REVIEW_RULES}). Write .agent/ui/review.json:
{"verdict":"PASS|CHANGES","summary":"one line","shots":{"<id>":{"verdict":"expected|unexpected|broken","note":"..."}}}
verdict is PASS only if nothing is unexpected or broken. Return the same verdict, summary, counts per verdict and the flagged shots.`,
    { label: `${designer ? 'UI/UX designer' : 'UI reviewer'}: shots${tag}`, phase: 'UI after', schema: UIREV, model: designer ? DESIGN_M : (RISK === 'high' ? APPROVE_M : W) })
  return { capture: cap, review: rev }
}

const qaPrompt = (role) => {
  const browser = APP.url
    ? `The app runs at ${APP.url}. Browser: agent-browser --session qa-${role} --ignore-https-errors ${role === 'signed-out' || !APP.auth ? '(no saved login)' : `--state ${APP.auth.split('{role}').join(role)}`}
${A.video ? `Video (needs ffmpeg; if missing say so and skip the recording, not the testing):
1. Demo take: agent-browser --session qa-${role} record start .agent/video/demo-${role}.webm <start url> --cursor --contact-sheet
   Walk the feature's happy path as this role in under 90 seconds, at a pace a person can follow; then: agent-browser --session qa-${role} record stop
2. Exploration take: record start .agent/video/qa-${role}.webm --fps 10 --contact-sheet before you explore; record stop when done.` : 'Video is off for this run.'}
Explore beyond the scripted tests: Back/Forward, reload, double clicks, a second tab, phone width 390, dark mode, keyboard only, slow network,
and what this role must NOT see or reach. Save a screenshot per finding under .agent/qa/${role}/. Close the browser session at the end.`
    : `The project has no app URL: explore through its real interface (CLI, API or library calls) as the plan describes. Try bad input,
empty input, large input, repeated calls, interrupted runs and what this role must not be able to do. Record exact commands and outputs.`
  return `You are the agent-QA explorer for role "${role}" in ${NAME} run ${A.run}.
Read .agent/plan.md (what changed and for whom)${PM_ON ? ', .agent/prd.md (the acceptance criteria and the entry point)' : ''}${FEATURE_MAP ? `, ${FEATURE_MAP} (every screen and action by name: name things the same way in your findings, and report a screen the map lists that you cannot reach)` : ''} and .agent/test-plan.json (what the scripted tests already cover).
Start where this role really starts (the home page or the signed-in landing page) and find the feature the way a user would; say if you cannot.
${browser}
Rules: change only this role's own state;${APP.fixtures ? ` seed fixtures with \`${APP.fixtures}\` before and remove them after;` : ''} never print passwords or tokens;
for each bug, check whether it also happens without the feature (existing_bug).
Write .agent/qa/${role}.json with exactly the object you return.`
}

const result = { run: A.run, mode: A.mode || 'build', tickets: [], gates: [], fixes: [], rounds: { build: 0, qa: 0 } }

if (A.mode === 'fixup') {
  // ------------------------------------------------ owner: "one more fix round, then ship"
  phase('Fix')
  result.fixes.push(await fix('owner fixup', 'Fix', { owner_themes: A.fixup && A.fixup.themes, findings: 'see .agent/evidence.md, .agent/qa/*.json, .agent/ui/review.json' }))
  phase('Gate + E2E')
  result.gates.push(await gate('fixup', 'Gate + E2E'))
  if (A.ui) { phase('UI after'); result.ui = await uiAfter(':fixup') }
} else {
  // ------------------------------------------------ Tests first
  phase('Tests first')
  if (!CASES && UI_TICKETS.length) log('no testPlan in args: the UI-test coverage check did not run')
  if (UNCOVERED_UI.length) {
    log(`UI tickets with no end-to-end case: ${UNCOVERED_UI.join(', ')}; the tester adds them first`)
    result.uiCoverage = await run(`These UI tickets of ${NAME} run ${A.run} have no end-to-end case in .agent/test-plan.json: ${UNCOVERED_UI.join(', ')}.
For each one, add at least one case with "kind": "e2e" and "covers": ["<ticket id>"] that drives the real UI as a user would (find the screen, act, see the result), using only hooks from the test contract in .agent/plan.md (add a hook to the contract when one is missing, and say so). Then write those tests. No product code. ${RULES}`,
      { label: 'Tester: end-to-end cases for UI tickets', phase: 'Tests first', schema: DONE, model: W })
  }
  result.tickets.push(...await runTickets(T.filter((t) => t.kind === 'test'), 'Tests first'))
  const redPrompt = `Red run for ${NAME} run ${A.run}: the feature is not implemented yet, so the new tests must FAIL, each for the right reason
(the missing feature, not a typo, a bad locator or a broken fixture). Run the new unit/script checks${E2E ? ` and: ${E2E}` : ''}
(no retries; keep timeouts short). Compare each failure message with .agent/test-plan.json. Do not change files.`
  let red = await run(redPrompt, { label: 'Gate: red run', phase: 'Tests first', schema: RED, model: W, effort: 'low' })
  if (red && (red.passing_unexpectedly.length || red.wrong_reason.length)) {
    log(`red run: ${red.passing_unexpectedly.length} pass too early, ${red.wrong_reason.length} fail for the wrong reason; fixing the tests once`)
    await run(`Fix these tests so they fail only because the feature is missing (no product code): ${JSON.stringify({ passing: red.passing_unexpectedly, wrong: red.wrong_reason })}. ${RULES}`,
      { label: 'Tester: fix the red run', phase: 'Tests first', schema: DONE, model: W })
    red = await run(redPrompt, { label: 'Gate: red run 2', phase: 'Tests first', schema: RED, model: W, effort: 'low' })
  }
  result.red = red

  // ------------------------------------------------ UI before (base code still in place)
  if (A.ui) {
    phase('UI before')
    result.uiBefore = await run(`Run the UI before capture on the current code, before anything is implemented:
${snapCmd('before')}
It reads .agent/ui/pages.json. Report the shot count and any errors. Do not change files.`,
      { label: 'UI snap: before', phase: 'UI before', model: W, effort: 'low' })
  }

  // ------------------------------------------------ Implement
  phase('Implement')
  result.tickets.push(...await runTickets(T.filter((t) => t.kind !== 'test'), 'Implement'))

  // ------------------------------------------------ Gate + E2E, bounded fix loop
  phase('Gate + E2E')
  let g = await gate('run 1', 'Gate + E2E')
  result.gates.push(g)
  while (g && !g.green && result.rounds.build < BUDGET.build) {
    result.rounds.build++
    result.fixes.push(await fix(`gate round ${result.rounds.build}`, 'Gate + E2E', g.failures))
    g = await gate(`run ${result.rounds.build + 1}`, 'Gate + E2E')
    result.gates.push(g)
  }
  if (g && !g.green) log(`gate still red after ${BUDGET.build} fix rounds; the owner decides`)

  // ------------------------------------------------ Verify by risk tier
  phase('Verify')
  const LENSES = RISK === 'high' ? ['correctness and regressions', 'security, auth and role checks', 'UI rules, accessibility, phone widths'] : ['correctness and regressions']
  const verifyModel = RISK === 'low' ? W : VERIFY_M
  const reviews = (await parallel(LENSES.map((lens) => () => run(
    `Review the uncommitted diff of ${NAME} run ${A.run} (git diff; new files included) through this lens: ${lens}.
Read .agent/plan.md for intent and ${REVIEW_RULES}. Each finding cites a rule heading from those files, or names a concrete failing
behaviour (input -> wrong output); anything else is an opinion: leave it out. Confirm every finding against the code before you report it:
a wrong finding costs more than a missed one. Severity blocker/major/minor/nit, with file:line. Change nothing.`,
    { label: `Verifier: ${lens.split(' ')[0].replace(/,$/, '')}`, phase: 'Verify', schema: FINDINGS, model: verifyModel })))).filter(Boolean)
  result.verify = reviews
  const serious = reviews.flatMap((r) => r.findings).filter((f) => f.severity === 'blocker' || f.severity === 'major' || f.severity === 'minor')
  if (serious.length && result.rounds.build < BUDGET.build) {
    result.rounds.build++
    result.fixes.push(await fix('verify findings', 'Verify', serious))
    result.gates.push(await gate('after verify', 'Verify'))
  } else if (serious.length) log(`${serious.length} verify findings left: build budget used up`)

  // ------------------------------------------------ Agent QA, one explorer per role (on video when there is an app)
  phase('Agent QA')
  const qaRoles = ROLES.length ? ROLES : ['user']
  const qa = (await parallel(qaRoles.map((role) => () => run(qaPrompt(role),
    { label: `QA: ${role}`, phase: 'Agent QA', schema: QA, model: W })))).filter(Boolean)
  result.qa = qa

  // ------------------------------------------------ UI after + review
  if (A.ui) { phase('UI after'); result.ui = await uiAfter('') }

  // ------------------------------------------------ one QA fix round
  const qaMajors = qa.flatMap((r) => r.findings.map((f) => ({ ...f, role: r.role }))).filter((f) => !f.existing_bug && (f.severity === 'blocker' || f.severity === 'major'))
  const uiFlags = (result.ui && result.ui.review && result.ui.review.flagged) || []
  if ((qaMajors.length || uiFlags.length) && result.rounds.qa < BUDGET.qa) {
    phase('Fix')
    result.rounds.qa++
    result.fixes.push(await fix('QA findings', 'Fix', { qa: qaMajors, ui: uiFlags }))
    result.gates.push(await gate('after QA', 'Fix'))
    if (A.ui) result.uiRecheck = await uiAfter(':recheck')
  } else if (qaMajors.length || uiFlags.length) log('QA findings left: QA budget used up; they go to the owner')
}

const gardenFindings = [
  ...(result.verify || []).flatMap((r) => r.findings || []).map((f) => ({ from: 'verify', ...f })),
  ...(result.qa || []).flatMap((r) => (r.findings || []).filter((f) => !f.existing_bug).map((f) => ({ from: `qa:${r.role}`, severity: f.severity, where: f.url || '', what: f.title }))),
  ...(((result.ui && result.ui.review && result.ui.review.flagged) || []).map((f) => ({ from: 'ui', severity: 'major', where: f.id, what: f.note }))),
]
if (GARDEN && gardenFindings.length) {
  phase('Garden')
  result.garden = await run(
    `You are the gardener for ${NAME} run ${A.run}. Your job is the codebase's guard rails, not this feature: every mistake an agent makes should become impossible next time.
Read ${GARDEN.log} (the garden log: earlier findings, one entry each; create it if missing) and these findings from this run:
${JSON.stringify(gardenFindings)}
For each finding, decide:
- the same pattern is already in the log, or appears ${GARDEN.repeat}+ times in this run: make it a deterministic check. Prefer, in order: an API or type change that makes the mistake impossible; a lint rule; a structure test (for example a test that fails on a forbidden import). Its error message tells the next agent the root-cause fix, not a workaround. Fix every existing occurrence so the check passes. Record it under "Checks" in the log.
- a first sighting: append it to the log (date ${A.today || ''}, pattern in one line, where, run ${A.run}) and change no code.
- not a pattern (a one-off typo, a product decision): skip it and say why.
Never add a code comment, a doc line or an AGENTS.md rule in place of a check. Then run the gate:
${GATE || "(the project's linters and unit tests)"}
It must stay green; if a new check cannot pass yet, revert that check and log it instead. ${RULES}`,
    { label: 'Gardener: findings into checks', phase: 'Garden', schema: GARDEN_RES, model: W })
}

// ------------------------------------------------ Evidence
phase('Evidence')
result.evidence = await run(
  `Write .agent/evidence.md for the owner's ship decision (H2) on ${NAME} run ${A.run}, from the files in .agent/ and this result:
${JSON.stringify(result)}
Sections: what was built (plain words); test results as a role x browser table with NOT RUN where a browser did not run, plus flakes by name;
gate table; verification verdict and what was fixed; agent QA counts and open findings grouped by theme (existing bugs labelled);
UI before/after: every non-unchanged shot with its verdict (if .agent/ui/shots.json exists); videos: every file under .agent/video/ with role
and kind; fix rounds used vs budget; garden: checks added (rule, file, what it catches) and patterns logged; stages with time; cost marked "estimated" unless measured; files touched (git status).
Short sentences, no hype. Return the first 3 lines of the file.`,
  { label: 'Evidence: report', phase: 'Evidence', model: W })

// ------------------------------------------------ Sign-off: PM acceptance report, CEO ship call
if (PM_ON || CEO_ON) phase('Sign-off')
if (PM_ON) {
  result.pmReport = await run(
    `You are the product manager for ${NAME} run ${A.run}. Check what was built against the brief, as a user would.
Read .agent/prd.md (acceptance criteria and entry point), .agent/pm.md (your decisions), .agent/evidence.md, .agent/qa/*.json${A.ui ? ', .agent/ui/review.json' : ''}.
For each acceptance criterion: met, partly or not met, with the evidence (a test id, a QA step, a screenshot or a video). Check the entry point: can a user find
the feature from where they already are? Write .agent/pm-report.md in plain words for the owner, with a table of the criteria. Return the counts.`,
    { label: 'PM: acceptance report', phase: 'Sign-off', schema: PMREP, model: PM_M })
}
if (CEO_ON) {
  result.signoff = await run(
    `You are the CEO of ${NAME}.${BUSINESS} Decide whether run ${A.run} is ready to ship.
Read .agent/ceo.md (your scope, must-haves and never-claim list)${PM_ON ? ', .agent/pm-report.md' : ''}, .agent/evidence.md and .agent/qa/*.json.
SHIP when the must-haves are in, the gate is green, nothing blocker or major is open and nothing in the product promises what it does not do. Otherwise HOLD,
with must_fix: the exact items to fix before it ships. Write .agent/ceo-signoff.md (verdict, reasons, must_fix). ${AUTO ? 'In this run your SHIP replaces the owner\'s H2.' : 'The owner makes the final call at H2.'}`,
    { label: 'CEO: sign-off', phase: 'Sign-off', schema: SIGNOFF, model: CEO_M })
}
return result
