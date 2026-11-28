export const meta = {
  name: 'pb-build',
  description: 'Product team, build half: ticket scheduler (one agent per role) -> close-out -> verifier + design review + gate -> fixes -> final gate -> PM report -> CEO sign-off',
  phases: [
    { title: 'Design', detail: 'Design tickets (and the CEO design review, if planned)' },
    { title: 'Build', detail: 'Backend, frontend, prints and demo data tickets' },
    { title: 'QA', detail: 'Close-out, verifier, design review, gate run' },
    { title: 'Fix', detail: 'Owners fix confirmed defects' },
    { title: 'Demo', detail: 'Final gate, PM report, CEO sign-off' },
  ],
}

// Template from the product-build skill. `args` = the run file (tools/<slug>.run.json) plus
// `tickets` (from <docs>/tickets.json, checked by scripts/check_tickets.py --emit-args).
// Copy it to <root>/tools/<slug>-build.workflow.js and change only meta.name to '<slug>-build'.

const A = args || {}
if (!A.root || !A.product || !A.context) throw new Error('args needs root, product and context (see references/run-config.md)')
if (!Array.isArray(A.tickets) || !A.tickets.length) throw new Error('args.tickets is missing: run check_tickets.py --emit-args and pass its output')
const ROOT = A.root
const D = A.docs || 'docs'
const DOCS = `${ROOT}/${D}`
const ROLES = A.roles || {}
const TICKETS = A.tickets
const DEFAULT_ROLES = {
  pm: { label: 'PM', desc: 'Project Manager: you lead the project, write the requirements, the plan and the report.' },
  ceo: { label: 'CEO', desc: "CEO: you think from the customer's and the business's point of view; you decide scope and sign off the demo." },
  ver: { label: 'Verifier', desc: 'Adversarial verifier: you try to refute claims and break the build; only confirmed defects count.' },
  res: { label: 'Research', desc: 'Research sub-agent working for the project manager.' },
  fdev: { label: 'Senior Frappe dev', desc: 'Senior Frappe developer: expert in Frappe, ERPNext and the apps this product builds on.' },
  sdev: { label: 'Senior dev', desc: 'Senior developer: architecture, frontend, integrations, security.' },
  ux: { label: 'UI/UX', desc: "UI/UX designer: you review screens from the users' side: neat, calm, professional, status colours with text labels, the product's brand." },
}
const role = k => ROLES[k] || DEFAULT_ROLES[k] || { label: k, desc: k }
const opts = (k, task, phase, schema) => {
  const r = role(k)
  const o = { label: `${r.label} · ${task}`, phase, schema }
  if (r.model) o.model = r.model
  if (r.agentType) o.agentType = r.agentType
  if (r.effort) o.effort = r.effort
  return o
}
async function ragent(prompt, o) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const p = attempt === 1 ? prompt : prompt + `\n\nNOTE: this is retry ${attempt}; an earlier attempt was cut off. Files from it may exist. Inspect the current state first and continue from it; do not start over or duplicate work.`
    const r = await agent(p, { ...o, label: attempt === 1 ? o.label : `${o.label} (retry ${attempt})` })
    if (r) return r
    log(`${o.label}: no result on attempt ${attempt}`)
  }
  return null
}

const GATE_ROLE = A.gate_role || (TICKETS.find(t => t.gate) || {}).owner || ['qa', 'seed'].find(k => ROLES[k]) || TICKETS[0].owner
const CTX = `PROJECT: "${A.product}". We are BUILDING now. Everything is planned already: follow the plan, do not re-plan.
${A.context}

READ FIRST (the source of truth, in this order of authority):
- ${DOCS}/40-plan.md: your ticket in §10.3 under its ID, and the sections it points to (data model §2, API contract §3, screens §4, prints §5, demo data §6, demo script §7, RULES FOR BUILDERS §8 = hard rules, file ownership §9, gates §10.1).
- ${DOCS}/41-plan-review.md (fixes already applied to 40), ${DOCS}/20-ceo-decision.md (scope, demo slice, claims), ${DOCS}/30-frappe-feasibility.md, ${DOCS}/31-architecture.md.
- ${DOCS}/build-log.md (what other agents finished; create it if missing) and ${DOCS}/41-api-changes.md (API contract changes; append yours).
- ${DOCS}/build-messages.md: requests between roles. Read it at the start: if a request is addressed to your role and touches your files, do it and mark it done there.

ENVIRONMENT (already running; do not rebuild it):
${A.environment || '(see the project README)'}

TEAM RULES:
- Work only on YOUR ticket and the files your role owns (plan §9). If you truly need a change in another role's file, re-read it right before editing, make the smallest additive edit, and log it in build-messages.md ("<ticket>: edited <file> (owner <role>): <what>"). Never rewrite or reformat someone else's code.
- Plan §8 rules are hard rules.${(A.rules || []).map(r => `\n- ${r}`).join('')}
- Never touch git (no commit, stash, checkout, reset, clean). Never run a database reset, restore or backup retake unless you are the ${role(GATE_ROLE).label} role. Never print a password or token, and never write one into a file or log: read secrets from environment variables.
- Verify every acceptance line for real on the running system (requests as the right non-admin user, Guest and wrong-role probes, tests, a browser look at screens). A screen is done only when it works as its own non-admin user.
- Status: "done" = every acceptance line verified; "built" = code complete but a line needs something another ticket has not delivered yet; "partial" / "blocked" with the reason. An honest partial beats a false done.
- When finished, append one line to ${DOCS}/build-log.md: "<ticket> <status> — <one line>", and put what dependents must know in handoff_notes (method names, routes, fields, users, test ids, gotchas).
- An earlier attempt may have left files for your ticket: inspect the current state first, keep what is correct, finish the job.
- Today is ${A.today || '(not given)'}.`

const RESULT = {
  type: 'object',
  properties: {
    ticket: { type: 'string' },
    status: { type: 'string', enum: ['done', 'built', 'partial', 'blocked'] },
    summary: { type: 'string', description: 'what you built and how you verified each acceptance line (5-15 lines)' },
    files: { type: 'array', items: { type: 'string' } },
    open_lines: { type: 'array', items: { type: 'string' }, description: 'acceptance lines not yet verified, and why' },
    handoff_notes: { type: 'string', description: 'facts dependents need: method names, routes, fields, users, gotchas' },
  },
  required: ['ticket', 'status', 'summary', 'files', 'open_lines', 'handoff_notes'],
}

// ---------------- Build: dependency scheduler, one agent per role at a time ----------------
const ids = new Set(TICKETS.map(t => t.id))
const GATE_TICKET = TICKETS.find(t => t.gate)
const CORE = TICKETS.filter(t => !t.stretch && !t.gate)
const STRETCH = TICKETS.filter(t => t.stretch)
const results = {}
const roleBusy = {}
const running = new Map()
let pending = [...CORE, ...STRETCH]
let stretchDecision = null

function depNotes(t) {
  return (t.depends_on || []).map(d => {
    const r = results[d]
    if (!r) return `${d}: not run`
    return `${d} [${r.status}]: ${r.summary}\n  handoff: ${r.handoff_notes}${r.open_lines && r.open_lines.length ? `\n  open: ${r.open_lines.join(' | ')}` : ''}`
  }).join('\n')
}
function stretchOpen() {
  if (stretchDecision !== null) return stretchDecision
  if (!CORE.every(t => results[t.id])) return false
  stretchDecision = CORE.every(t => ['done', 'built'].includes(results[t.id].status))
  log(stretchDecision ? 'All core tickets built or done: stretch tickets open' : 'Some core tickets partial/blocked: stretch tickets stay closed')
  return stretchDecision
}
function start(t) {
  roleBusy[t.owner] = true
  pending = pending.filter(x => x.id !== t.id)
  const prompt = `${CTX}

YOUR ROLE: ${role(t.owner).desc}

YOUR TICKET: ${t.id} "${t.title}"${t.hours ? ` (${t.hours} h estimate)` : ''}. Read its full text in plan §10.3. Summary:
${JSON.stringify(t, null, 1)}

DEPENDENCIES (results of the tickets you depend on):
${(t.depends_on || []).length ? depNotes(t) : 'none'}

If a dependency is partial or blocked, work around what is missing as far as you can without breaking a §8 rule, and say exactly what is missing in open_lines and handoff_notes.`
  const p = ragent(prompt, opts(t.owner, `${t.id} ${t.title}`, t.phase || 'Build', RESULT)).then(r => {
    results[t.id] = r || { ticket: t.id, status: 'blocked', summary: 'agent failed three times', files: [], open_lines: [], handoff_notes: '' }
    log(`${t.id} ${results[t.id].status}`)
    roleBusy[t.owner] = false
    running.delete(t.id)
    return t.id
  })
  running.set(t.id, p)
}

phase('Design')
while (pending.length || running.size) {
  for (const t of [...pending]) {
    if (roleBusy[t.owner]) continue
    if (!(t.depends_on || []).every(d => results[d] || !ids.has(d))) continue
    if (t.stretch && !stretchOpen()) continue
    start(t)
  }
  if (!running.size) {
    if (pending.length) log(`Not started: ${pending.map(t => t.id).join(', ')} (stretch closed or a dependency never ran)`)
    break
  }
  await Promise.race([...running.values()])
}

const statusLine = id => results[id] ? `${id} ${results[id].status}` : `${id} not run`
const buildSummary = () => TICKETS.filter(t => !t.gate).map(t => statusLine(t.id)).join(', ')
log(`Build done: ${buildSummary()}`)

// ---------------- QA: close-out, then verifier + design review + gate ----------------
phase('QA')
const openByRole = {}
for (const t of TICKETS) {
  const r = results[t.id]
  if (r && r.status !== 'done') (openByRole[t.owner] = openByRole[t.owner] || []).push({ id: t.id, title: t.title, status: r.status, open_lines: r.open_lines, summary: r.summary })
}
const CLOSE = { type: 'object', properties: { tickets: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['done', 'partial', 'blocked'] }, note: { type: 'string' } }, required: ['id', 'status', 'note'] } } }, required: ['tickets'] }
if (Object.keys(openByRole).length) {
  const closed = await parallel(Object.keys(openByRole).map(k => () =>
    ragent(`${CTX}\n\nYOUR ROLE: ${role(k).desc}\n\nClose-out. All build tickets have run (${buildSummary()}). Your tickets below are not yet "done". For each: verify every open acceptance line for real against the real APIs and data, fix what fails in your own files, and report the true status. Append the outcome to build-log.md.\n\n${JSON.stringify(openByRole[k], null, 1)}`,
      opts(k, 'close-out', 'QA', CLOSE))))
  for (const c of closed.filter(Boolean)) for (const x of c.tickets) if (results[x.id]) results[x.id].status = x.status
}

const builderKeys = [...new Set(TICKETS.map(t => t.owner))]
const DEFECTS = {
  type: 'object',
  properties: {
    report_file: { type: 'string' },
    summary: { type: 'string' },
    defects: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
      owner: { type: 'string', enum: builderKeys },
      ticket: { type: 'string' }, title: { type: 'string' },
      repro: { type: 'string', description: 'exact steps or request/response' }, expected: { type: 'string' }, actual: { type: 'string' },
    }, required: ['id', 'severity', 'owner', 'ticket', 'title', 'repro', 'expected', 'actual'] } },
  },
  required: ['report_file', 'summary', 'defects'],
}
const OWNERS = 'Owner codes for defects (plan §9 has the file list): ' + builderKeys.map(k => `${k} = ${role(k).label}`).join(', ') + '.'
const gateText = GATE_TICKET
  ? `Run the done gate, ticket ${GATE_TICKET.id}:\n${JSON.stringify(GATE_TICKET, null, 1)}`
  : `Run the done gate in plan §10.1 (the CEO's checks in 20-ceo-decision.md)${A.gate ? `. How: ${A.gate}` : ''}.`

async function qaRound(round) {
  const s = buildSummary()
  const jobs = [
    () => ragent(`${CTX}\n\nYOUR ROLE: ${role('ver').desc || 'Verifier (adversarial).'}\n\nRound ${round}. The build is finished (${s}). Review the whole change set (find it with git status / git diff, read only) against plan §2, §3 and §8 and the CEO's rulings. Hunt for: security holes (every new or changed whitelisted method: role check first, POST for writes, IDOR through any id argument, explicit fields, no ignore_permissions, no allow_guest, no v-html, escaped prints, /api/resource bypasses, secrets in the repo), wrong business rules versus the plan, broken existing behaviour, contract mismatches between the frontend and backend. Probe the running system to confirm each one. Write ${DOCS}/52-verifier-review${round > 1 ? `-r${round}` : ''}.md. Only confirmed defects go in the list. ${OWNERS}`,
      opts('ver', `code and security (round ${round})`, 'QA', DEFECTS)),
    () => ragent(`${CTX}\n\nYOUR ROLE: ${role(GATE_ROLE).desc}\n\nRound ${round}. ${gateText}\nBuild status: ${s}. Write ${DOCS}/51-gate-results.md with pass/fail and evidence for each point (add a "Round ${round}" section if it exists). Every failure is a defect for its owner with an exact repro. Leave the system in the demo state. ${OWNERS}`,
      opts(GATE_ROLE, `gate run (round ${round})`, 'QA', DEFECTS)),
  ]
  if (A.ui !== false) jobs.push(() => ragent(`${CTX}\n\nYOUR ROLE: ${role('ux').desc || 'UI/UX designer.'}\n\nRound ${round}. Design review. Walk the demo script in plan §7 in a real browser (Playwright${A.browser ? `: ${A.browser}` : ''}) at ${A.viewport || '1366x768'} as each user it names, and check every new or changed screen against the design and plan §4: layout, empty/loading/error states, words, console errors, the brand. Save screenshots under ${ROOT}/qa/screens/${A.slug || 'run'}/round-${round}/. Write ${DOCS}/53-design-review${round > 1 ? `-r${round}` : ''}.md with at most 10 fixes, ordered by what the client notices first. ${OWNERS}`,
    opts('ux', `design review (round ${round})`, 'QA', DEFECTS)))
  const out = await parallel(jobs)
  return out.filter(Boolean).flatMap(r => r.defects.map(d => ({ ...d, source: r.report_file })))
}

const FIXED = { type: 'object', properties: { fixes: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, outcome: { type: 'string', enum: ['fixed', 'not-reproduced', 'not-fixed'] }, note: { type: 'string' } }, required: ['id', 'outcome', 'note'] } } }, required: ['fixes'] }
async function fixRound(defects, round) {
  const byOwner = {}
  for (const d of defects) (byOwner[d.owner] = byOwner[d.owner] || []).push(d)
  log(`Fix round ${round}: ${defects.length} defects for ${Object.entries(byOwner).map(([o, ds]) => `${o} ${ds.length}`).join(', ')}`)
  const out = await parallel(Object.keys(byOwner).map(o => () =>
    ragent(`${CTX}\n\nYOUR ROLE: ${role(o).desc}\n\nFix round ${round}. QA found these defects in your area. Reproduce each one first; fix real ones at the root (never by weakening a security check, a rule or a test); mark ones you cannot reproduce with evidence. If a fix needs another owner's file, make the smallest additive change and log it in build-messages.md. Re-verify each fix as the affected user. Append each outcome to ${DOCS}/54-fixes.md.\n\nDEFECTS:\n${JSON.stringify(byOwner[o], null, 1)}`,
      opts(o, `fixes round ${round} (${byOwner[o].length})`, 'Fix', FIXED))))
  return out.filter(Boolean).flatMap(f => f.fixes)
}

const maxRounds = A.fix_rounds || 1
const allFixes = []
let defects = []
for (let round = 1; round <= maxRounds; round++) {
  phase('QA')
  defects = await qaRound(round)
  const serious = defects.filter(d => d.severity !== 'minor')
  log(`QA round ${round}: ${defects.length} defects (${serious.length} blocker/major)`)
  if (!defects.length) break
  phase('Fix')
  allFixes.push(...await fixRound(defects, round))
  if (!serious.length) break
}
const fixSummary = allFixes.map(f => `${f.id} ${f.outcome}`).join(', ')

// ---------------- Demo: final gate, PM report, CEO sign-off ----------------
phase('Demo')
const regate = await ragent(`${CTX}\n\nYOUR ROLE: ${role(GATE_ROLE).desc}\n\nFinal gate. Fixes are in (${fixSummary || 'no defects'}; see ${DOCS}/54-fixes.md). Re-run the done gate exactly as before and add a "Final run" section to ${DOCS}/51-gate-results.md (pass/fail + evidence per point). Then update ${ROOT}/DEMO.md (or the project README's demo section): how to reset to the demo state, which users to sign in as, and the script order. Leave the system in the demo state. Report remaining failures honestly as defects. ${OWNERS}`,
  opts(GATE_ROLE, 'final gate', 'Demo', DEFECTS))

const report = await ragent(`${CTX}\n\nYOUR ROLE: ${role('pm').desc || 'Project Manager.'}\n\nWrite ${DOCS}/60-build-report.md for the owner, in plain short English: what was built (per ticket with its final status, mapped to the requirement IDs in 10-requirements.md), what was verified and how (51, 52, 53, 54), what is not done or cut and why, the honest demo readiness, what the client must still answer, and the next 10 actions. Index all documents in ${DOCS}/README.md.\n\nBuild status: ${buildSummary()}\nFixes: ${fixSummary || 'none'}\nFinal gate: ${regate ? regate.summary : 'final gate agent failed'}`,
  opts('pm', 'build report', 'Demo', { type: 'object', properties: { file: { type: 'string' }, summary: { type: 'string' } }, required: ['file', 'summary'] }))

let signoff = null
if (A.signoff !== false) {
  signoff = await ragent(`${CTX}\n\nYOUR ROLE: ${role('ceo').desc || 'CEO.'} You decided the scope in 20-ceo-decision.md and own the demo story and the claims. Read ${DOCS}/60-build-report.md and 51-gate-results.md, look at the screenshots under ${ROOT}/qa/, and walk the demo script (plan §7) yourself in a real browser as the demo users (do not reset anything). Would you show this to the client next week? Write ${DOCS}/61-ceo-signoff.md: go / go-with-caveats / no-go, the 3 strongest moments, the 3 biggest risks during the demo and how the presenter handles each, and what must be true before the commercial proposal goes out.`,
    opts('ceo', 'walkthrough and sign-off', 'Demo', { type: 'object', properties: { verdict: { type: 'string', enum: ['go', 'go-with-caveats', 'no-go'] }, summary: { type: 'string' } }, required: ['verdict', 'summary'] }))
}

return {
  tickets: Object.fromEntries(TICKETS.map(t => [t.id, t.gate ? 'gate (ran in QA and Demo)' : results[t.id] ? results[t.id].status : 'not run'])),
  defects_found: defects.length,
  fixes: fixSummary,
  final_gate: regate ? { summary: regate.summary, open_defects: regate.defects.length } : null,
  report: report && report.summary,
  signoff,
}
