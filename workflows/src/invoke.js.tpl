// invoke — every /invoke chain as one saved script (replaces the model-driven /invoke loop for multi-act or size-L tasks).
// Args: {acts[], task, run, slug, brief?, surface?: general|frontend|backend|mixed, size?: S|M|L|XL, security_paths?[], tier_hint?}.
// The caller (router WORKFLOW line) supplies run = absolute .claude/runs/<utc-ts>-<slug>; scripts have no clock.
// Artifacts and run.json are written by the agents (scripts have no filesystem); replies stay small.
// Mixed surface runs backend -> frontend -> integrator in sequence (a workflow agent cannot lead a team).
// An act whose agent returns null (turn cap, dead agent) retries ONCE with a RETRY note; the XL review:2 pass does not;
// impl retries per sub-step (a finished backend half is never re-run). An incomplete review keeps its verdict and makes
// the result incomplete.
export const meta = {
  name: 'invoke',
  description: 'Run /invoke acts in canonical order (audit spec plan debug test impl refactor design clean security review docs verify): one specialist per act, closers after mutating acts, artifacts in the run folder',
  whenToUse: 'The router names it (WORKFLOW line) for >= 2 acts or a size-L act. Pass {acts, task, run, slug, brief?, surface?, size?}.',
  phases: [
    { title: 'Brief', model: '{{model:explore}}' },
    { title: 'Acts', model: '{{model:judge}}' },
    { title: 'Closers', model: '{{model:judge}}' },
    { title: 'Verify', model: '{{model:verify}}' },
  ],
}

const A = args || {}
const task = A.task || 'the task described in the conversation'
const run = String(A.run || '.claude/runs/invoke').replace(/\/+$/, '')
const slug = A.slug || 'run'
const dm = /(\d{4})(\d{2})(\d{2})T/.exec(run)
const date = dm ? `${dm[1]}-${dm[2]}-${dm[3]}` : 'undated'
const at = (f) => `${run}/${f}`
const ESC = A.tier_hint === 'escalate'   // set by workflow-model-guard / the router (I-5)
const up = (o, mm) => (ESC ? { ...o, model: mm } : o)   // executors only; judges never move
const ok = (x) => x !== null && x !== undefined          // agent() returns null when skipped or dead
const RETRY = 'RETRY: the previous run of exactly this task hit its turn cap and returned nothing. Create the artifact within ' +
  'your first 5 turns, append to it as you go, and return (StructuredOutput) by the deliver-by turn in your start context, ' +
  'listing what you could not cover as uncovered. '
const SIZE = ['S', 'M', 'L', 'XL'].includes(A.size) ? A.size : 'M'
const SURFACE = ['general', 'frontend', 'backend', 'mixed'].includes(A.surface) ? A.surface : 'general'
const BIG = SIZE === 'L' || SIZE === 'XL'

// Mirror of hooks/autonomous-skill-router.config.json categories.* (tests/test_workflows_lib.py pins equality).
const ACTS = [
  { act: 'audit', agent: 'audit-specialist', artifact: `AUDIT-${date}.md`, mutates: false, checkpoint: false },
  { act: 'spec', agent: 'spec-architect', artifact: `SPEC-${slug}.md`, mutates: false, checkpoint: true },
  { act: 'plan', agent: 'planning-director', artifact: `plan-${date}-${slug}.md`, mutates: false, checkpoint: true },
  { act: 'debug', agent: 'debug-detective', artifact: 'ROOTCAUSE.md', mutates: false, checkpoint: false },
  { act: 'test', agent: 'test-author', artifact: 'TEST-REPORT.md', mutates: false, checkpoint: false },
  { act: 'impl', agent: 'implementation-engineer', artifact: 'IMPL-REPORT.md', mutates: true, checkpoint: false },
  { act: 'refactor', agent: 'refactor-specialist', artifact: 'REFACTOR-REPORT.md', mutates: true, checkpoint: false },
  { act: 'design', agent: 'frontend-uiux-designer', artifact: 'DESIGN-REPORT.md', mutates: true, checkpoint: false },
  { act: 'clean', agent: 'deadcode-reaper', artifact: 'REAP-REPORT.md', mutates: true, checkpoint: false },
  { act: 'security', agent: 'security-sentinel', artifact: 'SECURITY-REPORT.md', mutates: false, checkpoint: false },
  { act: 'review', agent: 'santa-reviewer', artifact: 'SANTA-REVIEW.md', mutates: false, checkpoint: false },
  { act: 'docs', agent: 'docs-sync-agent', artifact: 'DOCS-SYNC-REPORT.md', mutates: false, checkpoint: false },
  { act: 'verify', agent: 'qa-verifier', artifact: 'VERIFY-REPORT.md', mutates: false, checkpoint: false },
]
const REPORT = { type: 'object', required: ['path', 'summary'], properties: { path: { type: 'string' }, summary: { type: 'string' },
  verdict: { type: 'string' }, touched_security: { type: 'boolean' }, files_changed: { type: 'array', items: { type: 'string' } } } }
const DO = {
  audit: 'Audit the code this task touches: architecture, dead code, risk, conventions; findings with file:line, severity and evidence.',
  spec: 'Produce the build-ready spec: requirements, typed contracts, acceptance criteria, Not-Doing list.',
  plan: 'Produce the dependency-ordered plan with exact paths and a TDD cycle per task.',
  debug: 'Find the root cause with evidence (reproduce, hypothesise, prove it); propose the minimal fix, do not apply it.',
  test: 'Write the failing tests that pin the required behaviour (TDD red) and report how to run them.',
  impl: 'Implement the plan test-first; touch only what the task needs; run the tests you touched.',
  refactor: 'Refactor without changing behaviour; the tests stay green before and after.',
  design: 'Design and implement the UI change against the project design system; run the design trio pipeline T1-T7 from your agent file (UI UX Pro Max, Hallmark, Impeccable) and list every call in DESIGN-REPORT.md ## Pipeline; verify it renders.',
  clean: 'Audit the diff of this run for dead code it orphaned (imports, exports, routes, state); remove only what this run introduced.',
  security: 'Security review of everything changed in this run; verdict PASS or BLOCK.',
  review: 'Santa Method review of everything changed in this run (BREAKER, SIMPLIFIER, VERIFIER); verdict APPROVE or CHANGES_REQUESTED.',
  docs: 'Sync documentation (repo docs and the local CLAUDE.md of every changed directory) to the changes of this run.',
  verify: 'Verify every acceptance criterion against the live code with real commands (tests, builds, linters; never start servers); verdict PASS or FAIL per criterion.',
}
const briefTxt = A.brief ? ` Read the brief ${A.brief} first.` : ` Read ${at('BRIEF.md')} first when it exists.`
const ctx = (focus) => `Task: ${task}.${briefTxt} Run folder: ${run}/ — read every artifact already there` +
  (focus ? `, especially ${focus}` : '') + '; when you finish, append your act to run.json "done".'
const out = (file) => ` Write your artifact to ${file}, then return {path, summary (5 lines max), verdict?, touched_security, files_changed}.` +
  ' touched_security is true when you changed files under auth/middleware/security/api/routes/handlers/controllers or with names matching' +
  ' login/session/token/password/oauth/jwt/secret/credential/validat/sanitiz.'
const prompt = (a, focus, note) => `${note || ''}${ctx(focus)} ${DO[a.act]}${out(at(a.artifact))}`

const results = {}
const done = []
const failed = []
const checkpoints = []
const lastPlan = () => (ok(results.plan) ? results.plan.path : ok(results.spec) ? results.spec.path : null)
const changedFiles = () => [...new Set(Object.values(results).filter(ok).flatMap(r => Array.isArray(r.files_changed) ? r.files_changed : []))]

async function once1(label, call) {             // call(notePrefix) -> result | null; ONE retry with the RETRY note
  const r = await call('')
  if (ok(r)) return r
  log(`${label} returned nothing (turn cap or dead agent): retrying once`)
  return call(RETRY)
}

async function runImpl(a, ph, note) {            // every agent call retries once on its own (once1)
  const focus = lastPlan()
  const n = note || ''
  if (SURFACE === 'frontend') {
    return once1('impl', (n2) => agent(prompt(a, focus, n2 + n), up({ agentType: 'frontend-implementor-specialist', model: '{{model:impl}}', label: 'impl', phase: ph, schema: REPORT }, '{{model:impl:up}}')))
  }
  if (SURFACE === 'backend') {
    return once1('impl', (n2) => agent(prompt(a, focus, n2 + n), up({ agentType: 'backend-implementor-specialist', model: '{{model:impl}}', label: 'impl', phase: ph, schema: REPORT }, '{{model:impl:up}}')))
  }
  if (SURFACE === 'mixed') {
    const be = await once1('backend', (n2) => agent(`${n2}${n}${ctx(focus)} Implement the backend half contract-first and publish a ## CONTRACT section.${out(at('IMPL-REPORT-BE.md'))}`,
      up({ agentType: 'backend-implementor-specialist', model: '{{model:impl}}', label: 'backend', phase: ph, schema: REPORT }, '{{model:impl:up}}')))
    if (!ok(be)) return null
    const fe = await once1('frontend', (n2) => agent(`${n2}${n}${ctx(at('IMPL-REPORT-BE.md') + ' (## CONTRACT)')} Implement the frontend half against the published contract; never invent API shapes.${out(at('IMPL-REPORT-FE.md'))}`,
      up({ agentType: 'frontend-implementor-specialist', model: '{{model:impl}}', label: 'frontend', phase: ph, schema: REPORT }, '{{model:impl:up}}')))
    if (!ok(fe)) return null
    const integ = await once1('integrate', (n2) => agent(`${n2}${n}${ctx(at('IMPL-REPORT-BE.md') + ' and ' + at('IMPL-REPORT-FE.md'))} Diff the contract against the frontend consumption, fix small wiring gaps, prove the end-to-end flow with evidence.${out(at('INTEGRATION-REPORT.md'))}`,
      up({ agentType: 'integrator-specialist', model: '{{model:integrate}}', label: 'integrate', phase: ph, schema: REPORT }, '{{model:integrate:up}}')))
    if (!ok(integ)) return null
    const parts = [be, fe, integ]
    return { path: integ.path, summary: integ.summary, touched_security: parts.some(p => p.touched_security === true),
      files_changed: [...new Set(parts.flatMap(p => Array.isArray(p.files_changed) ? p.files_changed : []))] }
  }
  return once1('impl', (n2) => agent(prompt(a, focus, n2 + n), up({ agentType: 'implementation-engineer', model: '{{model:impl}}', label: 'impl', phase: ph, schema: REPORT }, '{{model:impl:up}}')))
}

async function runReview(ph, note) {
  try {
    const r = await workflow('review', { run, paths: changedFiles(), tier_hint: A.tier_hint })
    if (ok(r)) {
      if (r.incomplete) log('review incomplete: uncovered paths remain; verdict kept as ' + r.verdict)
      return { path: at('SANTA-REVIEW.md'), summary: `review workflow: ${r.verdict}, ${(r.blocking || []).length} blocking`,
        verdict: r.verdict, incomplete: !!r.incomplete, blocking: r.blocking || [] }
    }
  } catch (e) {
    log(`review workflow unavailable (${String((e && e.message) || e)}); inline santa review`)
  }
  return agent(prompt(ACTS.find(x => x.act === 'review'), null, note), { agentType: 'santa-reviewer', model: '{{model:judge}}', label: 'review', phase: ph, schema: REPORT })
}

async function runAct(a, ph, note) {
  const p = prompt(a, a.act === 'spec' ? null : lastPlan(), note)
  switch (a.act) {
    case 'audit': return agent(p, { agentType: 'audit-specialist', model: '{{model:judge}}', label: 'audit', phase: ph, schema: REPORT })
    case 'spec': return agent(p, { agentType: 'spec-architect', model: '{{model:judge}}', label: 'spec', phase: ph, schema: REPORT })
    case 'plan': return agent(p, { agentType: 'planning-director', model: '{{model:judge}}', label: 'plan', phase: ph, schema: REPORT })
    case 'debug': return agent(p, { agentType: 'debug-detective', model: '{{model:judge}}', label: 'debug', phase: ph, schema: REPORT })
    case 'test': return agent(p, up({ agentType: 'test-author', model: '{{model:test}}', label: 'test', phase: ph, schema: REPORT }, '{{model:test:up}}'))
    case 'impl': return runImpl(a, ph, note)
    case 'refactor': return agent(p, up({ agentType: 'refactor-specialist', model: '{{model:impl}}', label: 'refactor', phase: ph, schema: REPORT }, '{{model:impl:up}}'))
    case 'design': return agent(p, { agentType: 'frontend-uiux-designer', model: '{{model:judge}}', label: 'design', phase: ph, schema: REPORT })
    case 'clean': return agent(p, { agentType: 'deadcode-reaper', model: '{{model:docs}}', label: 'clean', phase: ph, schema: REPORT })
    case 'security': return agent(p, up({ agentType: 'security-sentinel', model: '{{model:security}}', label: 'security', phase: ph, schema: REPORT }, '{{model:security:up}}'))
    case 'review': return runReview(ph, note)
    case 'docs': return agent(p, { agentType: 'docs-sync-agent', model: '{{model:docs}}', label: 'docs', phase: ph, schema: REPORT })
    case 'verify': return agent(p, { agentType: 'qa-verifier', model: '{{model:verify}}', label: 'qa', phase: ph, schema: REPORT, effort: BIG ? 'high' : undefined })
  }
  return null
}

async function runActOnce(a, ph) {              // one retry with the RETRY note; the label stays (the phase groups it)
  const r = await runAct(a, ph, '')
  if (ok(r)) return r
  log(`${a.act} returned nothing (turn cap or dead agent): retrying once`)
  return runAct(a, ph, RETRY)
}

// ---------- normalise acts (canonical order by construction) ----------
const requested = (Array.isArray(A.acts) ? A.acts : []).map(String)
const unknown = requested.filter(a => !ACTS.some(x => x.act === a))
if (unknown.length) log(`unknown acts dropped: ${unknown.join(', ')}`)
const acts = ACTS.filter(x => requested.includes(x.act))
if (!acts.length) return { run, error: 'no valid acts', unknown }

// ---------- brief ----------
phase('Brief')
const brief = await agent(`Task: ${task}. Run folder: ${run}/ (create it if missing). ` +
  (A.brief ? `Reuse the existing brief ${A.brief}: summarise it into ${at('BRIEF.md')}. ` : `Write ${at('BRIEF.md')}: the task, touched surfaces, impacted files, contracts at risk, acceptance criteria. `) +
  `Then write ${at('run.json')} in the ONE schema of skills/invoke/SKILL.md §2.4: task, slug "${slug}", run, started_utc (from the run folder name), ` +
  `start_sha (git rev-parse HEAD), acts ${JSON.stringify(acts.map(a => a.act))}, done [], models {}, team false, expected_artifacts. ` +
  'Read code with jcodemunch first; do not edit source. Return {path, summary (5 lines max)}.',
  { agentType: 'general-purpose', model: '{{model:explore}}', label: 'explore:brief', phase: 'Brief', schema: REPORT })
if (!ok(brief)) log('brief agent returned nothing; acts read the task text only')

// ---------- acts, sequential (each reads the previous artifacts) ----------
phase('Acts')
for (const a of acts) {
  if (a.act === 'verify') continue   // verify always runs last, on the final tree (Verify phase)
  const r = a.act === 'impl' ? await runAct(a, 'Acts', '') : await runActOnce(a, 'Acts')   // impl retries per sub-step
  results[a.act] = r
  if (ok(r)) {
    done.push(a.act)
    if (a.checkpoint) checkpoints.push({ act: a.act, path: r.path, summary: r.summary })
  } else {
    failed.push(a.act)
    if (a.act === 'spec' || a.act === 'plan') { log(`${a.act} failed: later acts depend on it, stopping`); break }
  }
}

// ---------- closers after mutating acts ----------
const mutated = acts.filter(a => a.mutates && ok(results[a.act]))
const ran = (act) => act in results
const sec = mutated.some(a => results[a.act].touched_security === true) || (Array.isArray(A.security_paths) && A.security_paths.length > 0)
const closerNames = []
if (mutated.length) {
  phase('Closers')
  if (!ran('clean')) {
    const c = await runActOnce(ACTS.find(x => x.act === 'clean'), 'Closers')
    results.clean = c
    if (!ok(c)) failed.push('clean')
  }
  const names = ['review', ...(sec && !ran('security') ? ['security'] : []), 'docs'].filter(n => !ran(n))
  if (sec && !requested.includes('security')) log('security-sensitive changes: security closer added')
  const closers = await parallel(names.map(n => () => runActOnce(ACTS.find(x => x.act === n), 'Closers')))
  names.forEach((n, i) => {
    results[n] = closers[i]
    closerNames.push(n)
    if (!ok(closers[i])) failed.push(n)
  })
  const rv = results.review
  if (SIZE === 'XL' && ok(rv) && rv.verdict !== 'APPROVE') {
    if (rv.incomplete === true) log(`review incomplete: uncovered paths remain; verdict kept as ${rv.verdict}`)
    const r2 = await agent(`${ctx(at('SANTA-REVIEW.md'))} Second review pass (size XL): re-check every blocking finding of the first review against the current tree; confirm fixed or still open. Append to ${at('SANTA-REVIEW.md')}. Return {path, summary, verdict}.`,
      { agentType: 'santa-reviewer', model: '{{model:judge}}', label: 'review:2', phase: 'Closers', schema: REPORT })
    if (ok(r2)) results.review = { ...rv, verdict: rv.incomplete === true ? rv.verdict : (r2.verdict || rv.verdict), second_pass: r2.summary }
    else failed.push('review:2')
  }
}

// ---------- verify last ----------
let qa = null
if (mutated.length || requested.includes('verify')) {
  phase('Verify')
  qa = await runActOnce(ACTS.find(x => x.act === 'verify'), 'Verify')
  results.verify = qa
  if (ok(qa)) { if (requested.includes('verify')) done.push('verify') } else failed.push('verify')
}

const verdictOf = (k) => (ok(results[k]) ? results[k].verdict || null : null)
return {
  run,
  acts: acts.map(a => a.act),
  done,
  failed,
  closers: closerNames,
  checkpoints,
  artifacts: Object.fromEntries(acts.map(a => [a.act, at(a.artifact)])),
  verdicts: { review: verdictOf('review'), security: verdictOf('security'), verify: verdictOf('verify') },
  incomplete: failed.length > 0 || (ok(results.review) && results.review.incomplete === true),
}
