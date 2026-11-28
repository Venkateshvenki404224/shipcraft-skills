export const meta = {
  name: 'pb-plan',
  description: 'Product team, plan half: research (verified) -> requirements -> CEO decision -> feasibility -> PM plan + tickets.json -> plan review',
  phases: [
    { title: 'Research', detail: 'Research sub-agents; a verifier checks the briefs' },
    { title: 'Requirements', detail: 'PM writes the requirements' },
    { title: 'Decide', detail: 'CEO decides scope, phases and the demo slice' },
    { title: 'Feasibility', detail: 'Senior Frappe dev and senior dev check fit and cost' },
    { title: 'Plan', detail: 'PM writes the plan and tickets; verifier reviews' },
  ],
}

// Template from the product-build skill. Everything project-specific comes in `args`
// (the project's tools/<slug>.run.json). Do not edit the logic per project; edit the run file.
// Copy it to <root>/tools/<slug>-plan.workflow.js and change only meta.name to '<slug>-plan'.

const A = args || {}
if (!A.root || !A.product || !A.context) throw new Error('args needs root, product and context (see references/run-config.md)')
const ROOT = A.root
const DOCS = `${ROOT}/${A.docs || 'docs'}`
const FEATURE = A.mode === 'feature'
const ROLES = A.roles || {}
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

// Agents can die on a dropped connection (ECONNRESET) or a usage limit. Retry twice and tell
// the retry to continue from the partial work instead of starting over.
async function ragent(prompt, o) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const p = attempt === 1 ? prompt : prompt + `\n\nNOTE: this is retry ${attempt}; an earlier attempt was cut off. Files from it may exist. Inspect them and continue; do not start over or duplicate work.`
    const r = await agent(p, { ...o, label: attempt === 1 ? o.label : `${o.label} (retry ${attempt})` })
    if (r) return r
    log(`${o.label}: no result on attempt ${attempt}`)
  }
  return null
}

const CTX = `PROJECT CONTEXT (shared by every agent):
Product: "${A.product}".${FEATURE ? ' This run adds a FEATURE to an existing product: reuse what exists, change it additively, and keep its current demo and tests passing.' : ' This run plans a NEW product.'}
${A.context}

All files for this run live under ${ROOT}/ ; the documents for this run go in ${DOCS}/ .
Write markdown in plain, direct English. Give a source (URL) for every external fact and file:line for every code fact. Mark anything you could not confirm as UNVERIFIED. Today is ${A.today || '(not given)'}.`

const DOC = { type: 'object', properties: { file: { type: 'string' }, summary: { type: 'string', description: 'concise summary (10-25 lines) other roles can act on' } }, required: ['file', 'summary'] }
const BRIEF = { type: 'object', properties: { file: { type: 'string' }, summary: { type: 'string', description: '8-15 line summary of the key findings' }, key_points: { type: 'array', items: { type: 'string' } } }, required: ['file', 'summary', 'key_points'] }
const VERIFY = { type: 'object', properties: { verdict: { type: 'string', enum: ['sound', 'sound-with-fixes', 'unreliable'] }, corrections: { type: 'array', items: { type: 'string' } }, summary: { type: 'string', description: 'corrected summary, 8-20 lines' } }, required: ['verdict', 'corrections', 'summary'] }
const FEAS = { type: 'object', properties: { file: { type: 'string' }, summary: { type: 'string' }, estimate: { type: 'string', description: 'effort per phase and for the demo slice, and which/how many agents' } }, required: ['file', 'summary', 'estimate'] }

// ---------------- Research ----------------
const RESEARCH = A.research || []
const verifyMode = A.verify_research || 'once'   // 'each' (one check per brief) | 'once' (one check over all) | 'none'
let briefs = '(no research step in this run)'
const researchOut = []
if (RESEARCH.length) {
  phase('Research')
  const researchPrompt = r => `${CTX}

ROLE: ${role('res').desc || 'research sub-agent working for the project manager'} ("${r.title}").
TASK: ${r.task}

Write your full findings to ${DOCS}/${r.out} (create it). Start with a 10-line executive summary, then details, then a Sources list. Be specific; never invent prices, features, doctype or field names. Write UNVERIFIED where you could not confirm.`
  const verifyPrompt = (files, summaries) => `${CTX}

ROLE: ${role('ver').desc || 'adversarial verifier'}. Check the research in: ${files}.
Try to REFUTE the claims that decisions will rest on: prices, feature claims, laws and dates, versions, Frappe doctype/field/hook names (check those in code). Fix wrong statements IN THE FILES, mark unconfirmable ones UNVERIFIED, and append a "## Verification" section to each file: what you checked, what you corrected, what stays uncertain, and what the brief missed for our use case.
The researchers' own summaries:
${summaries}`
  if (verifyMode === 'each') {
    const out = await pipeline(RESEARCH,
      r => ragent(researchPrompt(r), { ...opts('res', r.key, 'Research', BRIEF), ...(r.agentType ? { agentType: r.agentType } : {}) }),
      (b, r) => ragent(verifyPrompt(`${DOCS}/${r.out}`, b ? b.summary : '(researcher returned nothing: check whether the file exists; if not, do the research yourself and write it)'), opts('ver', `research ${r.key}`, 'Research', VERIFY)))
    out.forEach((v, i) => researchOut.push({ key: RESEARCH[i].key, verdict: v && v.verdict, summary: v ? v.summary : 'FAILED' }))
  } else {
    const out = await parallel(RESEARCH.map(r => () => ragent(researchPrompt(r), { ...opts('res', r.key, 'Research', BRIEF), ...(r.agentType ? { agentType: r.agentType } : {}) })))
    out.forEach((b, i) => researchOut.push({ key: RESEARCH[i].key, verdict: 'unverified', summary: b ? b.summary : 'FAILED' }))
    if (verifyMode === 'once') {
      const v = await ragent(verifyPrompt(RESEARCH.map(r => `${DOCS}/${r.out}`).join(', '), researchOut.map(x => `### ${x.key}\n${x.summary}`).join('\n\n')), opts('ver', 'research', 'Research', VERIFY))
      if (v) researchOut.forEach(x => { x.verdict = v.verdict })
    }
  }
  briefs = RESEARCH.map((r, i) => `### ${r.title} (${DOCS}/${r.out}) — ${researchOut[i].verdict}\n${researchOut[i].summary}`).join('\n\n')
  log(`Research: ${researchOut.filter(x => x.summary !== 'FAILED').length}/${RESEARCH.length} briefs`)
}

// ---------------- Requirements ----------------
phase('Requirements')
const req = await ragent(`${CTX}

ROLE: ${role('pm').desc || 'Project Manager: you lead the project.'}
${A.brief ? `THE OWNER'S / CLIENT'S REQUEST (verbatim; the source of truth for what is wanted):\n${A.brief}\n` : ''}${A.brief_files && A.brief_files.length ? `Client material to read first: ${A.brief_files.join(', ')}\n` : ''}
Research briefs (read the files for detail):
${briefs}

TASK: write ${DOCS}/10-requirements.md:
1. Problem, goals and success measures.
2. Users/personas and their top jobs.
3. End-to-end journeys, step by step.
4. Requirement catalogue: for EACH item an ID (e.g. R-01 or module-prefixed), description, priority (Must/Should/Could/Won't-now), source (client text, competitor, law), and acceptance in one line.${FEATURE ? '\n   Map every client requirement to an ID; say for each whether the existing product already covers it (cite files).' : ''}
5. Non-functional needs: security and privacy, roles and permissions, audit, performance, languages, printing, offline tolerance.
6. Assumptions, and open questions for the client (list them; do not ask now).
Be decisive and specific.`, opts('pm', 'requirements', 'Requirements', DOC))

// ---------------- Decide ----------------
phase('Decide')
const ceo = await ragent(`${CTX}

ROLE: ${role('ceo').desc || "CEO: you think from the customer's and the business's point of view."}
Read ${DOCS}/10-requirements.md (summary below) and the research in ${DOCS}/research/ if any.
${req ? req.summary : '(summary missing: read the file)'}

TASK: write ${DOCS}/20-ceo-decision.md:
1. Positioning: one paragraph and the differentiators we can honestly claim.
2. Scope: PHASE 1 (what makes the client sign), PHASE 2, LATER, as lists of requirement IDs with a one-line reason each.
3. THE DEMO SLICE: what the agent team builds and demos NOW ${A.demo_budget ? `(budget: ${A.demo_budget})` : '(a few hours of agent work)'}. Write it as a 10-minute story for the client, click by click, using the product's existing pieces wherever possible. Cut order: what to drop first if time runs out.
4. The done gate: the checks that must pass before you would show it (numbered; each objectively checkable).
5. Claims: what we may and may not say in the demo.
6. Team per phase, what we need from humans, pricing/packaging if relevant, top risks.`, opts('ceo', 'decision', 'Decide', DOC))

// ---------------- Feasibility ----------------
phase('Feasibility')
const ceoSum = ceo ? ceo.summary : '(read the file)'
const [fdev, sdev] = await parallel([
  () => ragent(`${CTX}

ROLE: ${role('fdev').desc || 'Senior Frappe developer: expert in Frappe, ERPNext and the apps this product builds on.'}
Inputs: ${DOCS}/10-requirements.md, ${DOCS}/20-ceo-decision.md. CEO summary:
${ceoSum}

TASK: write ${DOCS}/30-frappe-feasibility.md. Check facts in code (shallow-clone upstream apps into your own scratch directory, never under ${ROOT}):
1. A table over EVERY requirement in phase 1 and the demo slice: requirement -> out of the box | configure | custom fields/scripts | new doctype/code in our app | integration | not feasible now -> exact doctypes/fields/hooks (cite file paths) -> hours.
2. Data model for the demo slice: doctypes used, masters/settings needed, and what our app must add.
3. First draft of the API contract: whitelisted methods (name, args, returns, roles allowed).
4. Demo data plan (invented, clearly fake) and how it loads and resets.
5. Version gotchas and setup prerequisites; permission pitfalls.
6. Estimate per phase and for the demo slice; how many backend agents.`, opts('fdev', 'feasibility', 'Feasibility', FEAS)),
  () => ragent(`${CTX}

ROLE: ${role('sdev').desc || 'Senior developer: architecture, frontend, integrations, security.'}
Inputs: ${DOCS}/10-requirements.md, ${DOCS}/20-ceo-decision.md. CEO summary:
${ceoSum}

TASK: write ${DOCS}/31-architecture.md:
1. Target architecture (what lives in our app, what in the UI, what stays in Desk); justify it.
2. Frontend for the demo slice: routes, state, components, how it signs in, build and serve steps. ${A.ui === false ? 'This run has NO new UI (backend/Desk only): say how users reach the feature in Desk instead.' : ''}
3. Integrations and how each is done or stubbed.
4. Security and privacy design: roles x methods matrix, field limits, audit, CSRF/session, rate limits, secrets.
5. Hosting/environments if relevant.
6. Feasibility verdict and estimate for the demo slice.`, opts('sdev', 'architecture', 'Feasibility', FEAS)),
])

// ---------------- Plan ----------------
phase('Plan')
const owners = Object.keys(ROLES).filter(k => ROLES[k].builder).join(', ') || 'fdev, sdev, fe1, fe2, ux, seed, qa'
const plan = await ragent(`${CTX}

ROLE: ${role('pm').desc || 'Project Manager.'} Consolidate everything into the plan the builders will follow without re-planning.
Inputs: ${DOCS}/10-requirements.md, 20-ceo-decision.md, 30-frappe-feasibility.md, 31-architecture.md, research in ${DOCS}/research/.
Frappe dev estimate: ${fdev ? fdev.estimate : 'n/a'}
Senior dev estimate: ${sdev ? sdev.estimate : 'n/a'}

TASK 1: write ${DOCS}/40-plan.md with these numbered sections:
§1 Decisions log (with the owning role). §2 Data model. §3 API contract (method, args, returns, roles, POST/GET). §4 Screens${A.ui === false ? ' (none in this run: say so)' : ' (per screen: user, purpose, components, states)'}. §5 Prints (if any). §6 Demo data and reset. §7 The demo script, click by click. §8 RULES FOR BUILDERS: hard rules (security: role check first in every method, POST for writes, explicit fields, no allow_guest, no ignore_permissions; additive changes; keep the existing demo/tests passing; brand words; invented data only). §9 File ownership: which role owns which files, so parallel agents never edit the same file. §10 Gates and tickets: §10.1 the done gate (from the CEO), §10.2 conflicts between the documents and how you resolved them, §10.3 the tickets.
TASK 2: write the same tickets as machine-readable JSON to ${DOCS}/tickets.json: an array of
  {"id": "T-01", "title": "...", "owner": "<one of: ${owners}>", "depends_on": ["T-00"], "hours": 2, "phase": "Design" | "Build", "acceptance": ["one checkable line", "..."], "files": ["paths this ticket owns"], "stretch": false, "gate": false}
  Order: design -> API contract/stubs -> backend and frontend in parallel -> demo data -> gate. Exactly one ticket may have "gate": true: the run of the done gate (owned by the demo-data or QA role). Mark nice-to-haves "stretch": true (they run only if every core ticket is done). Each role runs one ticket at a time, so spread work across roles and keep dependency chains short. Every "depends_on" id must exist.
Also write ${DOCS}/README.md indexing the documents.`, opts('pm', 'plan', 'Plan', DOC))

const review = await ragent(`${CTX}

ROLE: ${role('ver').desc || 'adversarial verifier'}. Review ${DOCS}/40-plan.md and ${DOCS}/tickets.json against 10, 20, 30 and 31. Try to break them:
- Wrong Frappe facts (doctypes, fields, hooks that do not exist; check in code from your own scratch clone).
- Tickets that cannot be done in the time given, missing dependencies, acceptance lines that cannot be checked, two tickets owning the same file, a tickets.json that disagrees with §10.3, ids in depends_on that do not exist, an owner that is not a builder role.
- Security or privacy gaps; claims the CEO said we may not make; table-stakes features missing from phase 1.
Fix confirmed defects directly in 40-plan.md and tickets.json (bump the plan version and keep a changelog at its end). Write ${DOCS}/41-plan-review.md with every finding: confirmed and fixed, or rejected with the reason.`,
  opts('ver', 'plan review', 'Plan', { type: 'object', properties: { summary: { type: 'string' }, confirmed_fixed: { type: 'array', items: { type: 'string' } }, open_risks: { type: 'array', items: { type: 'string' } } }, required: ['summary', 'confirmed_fixed', 'open_risks'] }))

return {
  research: researchOut.map(x => ({ key: x.key, verdict: x.verdict })),
  requirements: req && req.summary,
  ceo: ceo && ceo.summary,
  frappe_dev: fdev && { summary: fdev.summary, estimate: fdev.estimate },
  senior_dev: sdev && { summary: sdev.summary, estimate: sdev.estimate },
  plan: plan && plan.summary,
  review,
}
