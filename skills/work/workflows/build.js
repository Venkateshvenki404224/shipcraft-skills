export const meta = {
  name: 'work-build',
  description: '/work: tests first, implement, gate + E2E, verify, per-role agent QA on video, UI before/after review, evidence',
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
    { title: 'Evidence', detail: 'writes .agent/evidence.md for the owner (H2)' },
  ],
}

// Copied per run to .agent/workflow/build.js by the /work skill. The run's shape comes from args:
// {run, today, skill, profile (the repo's .claude/work.json), tickets:[{id,title,kind,files,deps,acceptance,model}],
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
const W = (P.models && P.models.work) || 'sonnet'
const REVIEW_RULES = [P.review_rules, `${SKILL}/references/review-rules.md`].filter(Boolean).join(' and ')
const RULES = `Rules: follow the project rules (${(P.rules || ['CLAUDE.md']).join(', ')}). Never print secrets (${(P.secrets || ['.env*']).join(', ')}).
Do not commit, push or touch git history.`

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

const ticketPrompt = (t) => `Implement ticket ${t.id} of ${NAME} run ${A.run}: ${t.title}
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
    const out = await parallel(batch.map((t) => () => agent(ticketPrompt(t), { label: `${t.id}`, phase: phaseName, schema: DONE, model: t.model || W })))
    batch.forEach((t, i) => { done.add(t.id); left.splice(left.indexOf(t), 1); results.push(out[i] || { ticket: t.id, files_changed: [], notes: 'agent returned nothing' }) })
  }
  return results
}

const gate = (label, phaseName) => agent(
  `Run the gate for ${NAME} run ${A.run} and report; do not fix anything.
Gate commands, in order (stop at nothing; run them all):
${GATE || '(the profile lists no gate commands: run the project\'s linters and unit tests as its README or CI config describes, and say which)'}
${E2E ? `Then the end-to-end tests: ${E2E}
Browsers expected: ${BROWSERS.join(', ')}. Per browser report PASS n/n, FAIL, or NOT RUN with the reason (a browser that is not installed is NOT RUN, never left out).` : 'There is no end-to-end command; report browsers as {}.'}
If a test fails and then passes on a rerun, rerun it 20 times; all pass = list it under flakes, any fail = failure.`,
  { label, phase: phaseName, schema: GATE_RES, model: W, effort: 'low' })

const fix = (label, phaseName, what) => agent(
  `Fix round for ${NAME} run ${A.run}. Read .agent/plan.md. Fix these problems in the product code:
${JSON.stringify(what)}
Never weaken an assertion, widen a timeout or delete a test to make it pass; if a test is wrong against the test contract, fix the test and say why.
Return the files you changed. ${RULES}`,
  { label, phase: phaseName, schema: DONE, model: W })

const snapCmd = (ph) => (A.uiSnap || '').split('{phase}').join(ph)
const uiAfter = async (tag) => {
  const cap = await agent(`Run the UI after capture: ${snapCmd('after')}
Report the counts printed by the teardown and any test that errored (an error is not a visual change). Do not change files.`,
    { label: `ui-after${tag}`, phase: 'UI after', model: W, effort: 'low' })
  const rev = await agent(
    `You are the UI review agent for ${NAME} run ${A.run}. Read the "expected visible changes" in .agent/plan.md and .agent/ui/shots.json.
For every shot whose status is not "unchanged", open its before, marked (the after image with a red box around each changed area) and diff
PNGs (paths are relative to .agent/ui/; "boxes" lists the changed areas) and judge each boxed area:
expected = the change is in the plan; unexpected = a change the plan did not ask for; broken = overlap, clipping, sideways scroll,
unreadable text, an empty state where data belongs, wrong data for the role. A final_path that differs from the page is a redirect: check it
against the project's access rules (${REVIEW_RULES}). Write .agent/ui/review.json:
{"verdict":"PASS|CHANGES","summary":"one line","shots":{"<id>":{"verdict":"expected|unexpected|broken","note":"..."}}}
verdict is PASS only if nothing is unexpected or broken. Return the same verdict, summary, counts per verdict and the flagged shots.`,
    { label: `ui-review${tag}`, phase: 'UI after', schema: UIREV, model: RISK === 'high' ? 'opus' : W })
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
Read .agent/plan.md (what changed and for whom) and .agent/test-plan.json (what the scripted tests already cover).
${browser}
Rules: change only this role's own state;${APP.fixtures ? ` seed fixtures with \`${APP.fixtures}\` before and remove them after;` : ''} never print passwords or tokens;
for each bug, check whether it also happens without the feature (existing_bug).
Write .agent/qa/${role}.json with exactly the object you return.`
}

const result = { run: A.run, mode: A.mode || 'build', tickets: [], gates: [], fixes: [], rounds: { build: 0, qa: 0 } }

if (A.mode === 'fixup') {
  // ------------------------------------------------ owner: "one more fix round, then ship"
  phase('Fix')
  result.fixes.push(await fix('owner-fixup', 'Fix', { owner_themes: A.fixup && A.fixup.themes, findings: 'see .agent/evidence.md, .agent/qa/*.json, .agent/ui/review.json' }))
  phase('Gate + E2E')
  result.gates.push(await gate('gate:fixup', 'Gate + E2E'))
  if (A.ui) { phase('UI after'); result.ui = await uiAfter(':fixup') }
} else {
  // ------------------------------------------------ Tests first
  phase('Tests first')
  result.tickets.push(...await runTickets(T.filter((t) => t.kind === 'test'), 'Tests first'))
  const redPrompt = `Red run for ${NAME} run ${A.run}: the feature is not implemented yet, so the new tests must FAIL, each for the right reason
(the missing feature, not a typo, a bad locator or a broken fixture). Run the new unit/script checks${E2E ? ` and: ${E2E}` : ''}
(no retries; keep timeouts short). Compare each failure message with .agent/test-plan.json. Do not change files.`
  let red = await agent(redPrompt, { label: 'red-run', phase: 'Tests first', schema: RED, model: W, effort: 'low' })
  if (red && (red.passing_unexpectedly.length || red.wrong_reason.length)) {
    log(`red run: ${red.passing_unexpectedly.length} pass too early, ${red.wrong_reason.length} fail for the wrong reason; fixing the tests once`)
    await agent(`Fix these tests so they fail only because the feature is missing (no product code): ${JSON.stringify({ passing: red.passing_unexpectedly, wrong: red.wrong_reason })}. ${RULES}`,
      { label: 'fix-tests', phase: 'Tests first', schema: DONE, model: W })
    red = await agent(redPrompt, { label: 'red-run:2', phase: 'Tests first', schema: RED, model: W, effort: 'low' })
  }
  result.red = red

  // ------------------------------------------------ UI before (base code still in place)
  if (A.ui) {
    phase('UI before')
    result.uiBefore = await agent(`Run the UI before capture on the current code, before anything is implemented:
${snapCmd('before')}
It reads .agent/ui/pages.json. Report the shot count and any errors. Do not change files.`,
      { label: 'ui-before', phase: 'UI before', model: W, effort: 'low' })
  }

  // ------------------------------------------------ Implement
  phase('Implement')
  result.tickets.push(...await runTickets(T.filter((t) => t.kind !== 'test'), 'Implement'))

  // ------------------------------------------------ Gate + E2E, bounded fix loop
  phase('Gate + E2E')
  let g = await gate('gate:1', 'Gate + E2E')
  result.gates.push(g)
  while (g && !g.green && result.rounds.build < BUDGET.build) {
    result.rounds.build++
    result.fixes.push(await fix(`fix:build${result.rounds.build}`, 'Gate + E2E', g.failures))
    g = await gate(`gate:${result.rounds.build + 1}`, 'Gate + E2E')
    result.gates.push(g)
  }
  if (g && !g.green) log(`gate still red after ${BUDGET.build} fix rounds; the owner decides`)

  // ------------------------------------------------ Verify by risk tier
  phase('Verify')
  const LENSES = RISK === 'high' ? ['correctness and regressions', 'security, auth and role checks', 'UI rules, accessibility, phone widths'] : ['correctness and regressions']
  const verifyModel = RISK === 'low' ? W : 'opus'
  const reviews = (await parallel(LENSES.map((lens) => () => agent(
    `Review the uncommitted diff of ${NAME} run ${A.run} (git diff; new files included) through this lens: ${lens}.
Read .agent/plan.md for intent and ${REVIEW_RULES}. Each finding cites a rule heading from those files, or names a concrete failing
behaviour (input -> wrong output); anything else is an opinion: leave it out. Confirm every finding against the code before you report it:
a wrong finding costs more than a missed one. Severity blocker/major/minor/nit, with file:line. Change nothing.`,
    { label: `verify:${lens.split(' ')[0].replace(/,$/, '')}`, phase: 'Verify', schema: FINDINGS, model: verifyModel })))).filter(Boolean)
  result.verify = reviews
  const serious = reviews.flatMap((r) => r.findings).filter((f) => f.severity === 'blocker' || f.severity === 'major' || f.severity === 'minor')
  if (serious.length && result.rounds.build < BUDGET.build) {
    result.rounds.build++
    result.fixes.push(await fix(`fix:verify`, 'Verify', serious))
    result.gates.push(await gate('gate:after-verify', 'Verify'))
  } else if (serious.length) log(`${serious.length} verify findings left: build budget used up`)

  // ------------------------------------------------ Agent QA, one explorer per role (on video when there is an app)
  phase('Agent QA')
  const qaRoles = ROLES.length ? ROLES : ['user']
  const qa = (await parallel(qaRoles.map((role) => () => agent(qaPrompt(role),
    { label: `qa:${role}`, phase: 'Agent QA', schema: QA, model: W })))).filter(Boolean)
  result.qa = qa

  // ------------------------------------------------ UI after + review
  if (A.ui) { phase('UI after'); result.ui = await uiAfter('') }

  // ------------------------------------------------ one QA fix round
  const qaMajors = qa.flatMap((r) => r.findings.map((f) => ({ ...f, role: r.role }))).filter((f) => !f.existing_bug && (f.severity === 'blocker' || f.severity === 'major'))
  const uiFlags = (result.ui && result.ui.review && result.ui.review.flagged) || []
  if ((qaMajors.length || uiFlags.length) && result.rounds.qa < BUDGET.qa) {
    phase('Fix')
    result.rounds.qa++
    result.fixes.push(await fix('fix:qa', 'Fix', { qa: qaMajors, ui: uiFlags }))
    result.gates.push(await gate('gate:after-qa', 'Fix'))
    if (A.ui) result.uiRecheck = await uiAfter(':recheck')
  } else if (qaMajors.length || uiFlags.length) log('QA findings left: QA budget used up; they go to the owner')
}

// ------------------------------------------------ Evidence
phase('Evidence')
result.evidence = await agent(
  `Write .agent/evidence.md for the owner's ship decision (H2) on ${NAME} run ${A.run}, from the files in .agent/ and this result:
${JSON.stringify(result)}
Sections: what was built (plain words); test results as a role x browser table with NOT RUN where a browser did not run, plus flakes by name;
gate table; verification verdict and what was fixed; agent QA counts and open findings grouped by theme (existing bugs labelled);
UI before/after: every non-unchanged shot with its verdict (if .agent/ui/shots.json exists); videos: every file under .agent/video/ with role
and kind; fix rounds used vs budget; stages with time; cost marked "estimated" unless measured; files touched (git status).
Short sentences, no hype. Return the first 3 lines of the file.`,
  { label: 'evidence', phase: 'Evidence', model: W })
return result
