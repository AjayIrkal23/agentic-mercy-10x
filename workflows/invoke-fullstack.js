// invoke-fullstack — deterministic mirror of `/invoke spec plan impl` for a mixed-surface build.
// EXPLICIT USER OPT-IN ONLY: the /invoke skill never launches this on its own.
// Usage: create the run folder first (see skills/invoke step 2), then run with
//   args: { task: "<task>", run: ".claude/runs/<utc-ts>-<slug>", slug: "<slug>", brief?: "<path>" }
// Scripts have no clock or filesystem, so the caller supplies the run folder; artifact dates come from its name.
export const meta = {
  name: 'invoke-fullstack',
  description: 'spec → plan → backend → frontend → integrator → parallel(santa, security, docs) → qa, artifacts in the run folder',
  whenToUse: 'Only when the user explicitly asks for /invoke-fullstack. Pass {task, run, slug} via args.',
  phases: [
    { title: 'Spec' },
    { title: 'Plan' },
    { title: 'Backend', model: 'opus' },
    { title: 'Frontend', model: 'opus' },
    { title: 'Integrate', model: 'opus' },
    { title: 'Close' },
    { title: 'Verify' },
  ],
}

const task = (args && args.task) || 'the task described in the conversation'
const run = ((args && args.run) || '.claude/runs/invoke-fullstack').replace(/\/+$/, '')
const slug = (args && args.slug) || 'fullstack'
const m = /(\d{4})(\d{2})(\d{2})T/.exec(run)
const date = m ? `${m[1]}-${m[2]}-${m[3]}` : 'undated'
const at = (file) => `${run}/${file}`
const SPEC = at(`SPEC-${slug}.md`)
const PLAN = at(`plan-${date}-${slug}.md`)
const brief = (args && args.brief) ? ` Read ${args.brief} first.` : ''

const ctx = (focus) =>
  `Task: ${task}.${brief} Run folder: ${run}/ — read every artifact already there` +
  (focus ? `, especially ${focus}` : '') + '.'
const out = (file) => ` Write your artifact to ${file} and return its path plus a 5-line summary.`

phase('Spec')
const spec = await agent(`${ctx()} Produce the build-ready spec: requirements, typed contracts, acceptance criteria, Not-Doing list.${out(SPEC)}`,
  { agentType: 'spec-architect', model: 'sonnet', label: 'spec' })

phase('Plan')
const plan = await agent(`${ctx(SPEC)} Produce the dependency-ordered plan with exact paths and a TDD cycle per task.${out(PLAN)}`,
  { agentType: 'planning-director', model: 'sonnet', label: 'plan' })

phase('Backend')
const be = await agent(`${ctx(PLAN)} Implement the backend half contract-first and publish the CONTRACT section.${out(at('IMPL-REPORT-BE.md'))}`,
  { agentType: 'backend-implementor-specialist', model: 'opus', label: 'backend' })

phase('Frontend')
const fe = await agent(`${ctx(at('IMPL-REPORT-BE.md') + ' (## CONTRACT)')} Implement the frontend half against the published contract; never invent API shapes; assets via Higgsfield.${out(at('IMPL-REPORT-FE.md'))}`,
  { agentType: 'frontend-implementor-specialist', model: 'opus', label: 'frontend' })

phase('Integrate')
const integ = await agent(`${ctx(at('IMPL-REPORT-BE.md') + ' and ' + at('IMPL-REPORT-FE.md'))} Diff the contract against the FE consumption, fix small wiring gaps, prove the E2E flow with evidence.${out(at('INTEGRATION-REPORT.md'))}`,
  { agentType: 'integrator-specialist', model: 'opus', label: 'integrate' })

// Barrier is deliberate: qa must see the finished tree after all three closers.
phase('Close')
const [santa, security, docs] = await parallel([
  () => agent(`${ctx()} Santa Method review of everything changed in this run.${out(at('SANTA-REVIEW.md'))}`,
    { agentType: 'santa-reviewer', model: 'opus', label: 'santa', phase: 'Close' }),
  () => agent(`${ctx()} Security review of everything changed in this run; verdict PASS or BLOCK.${out(at('SECURITY-REPORT.md'))}`,
    { agentType: 'security-sentinel', model: 'sonnet', label: 'security', phase: 'Close' }),
  () => agent(`${ctx()} Sync documentation to the changes of this run.${out(at('DOCS-SYNC-REPORT.md'))}`,
    { agentType: 'docs-sync-agent', model: 'sonnet', label: 'docs', phase: 'Close' }),
])

phase('Verify')
const qa = await agent(`${ctx(SPEC)} Verify every acceptance criterion against the live code with real commands; PASS or FAIL per criterion.${out(at('VERIFY-REPORT.md'))}`,
  { agentType: 'qa-verifier', model: 'sonnet', label: 'qa' })

return { run, spec, plan, be, fe, integ, santa, security, docs, qa }
