// migrate — lossless merge/port of one harness into another: inventory -> dispositions -> packages -> critic -> revision.
// Args: {run, source?, target?, surfaces?[], task?, corpus?[], tier_hint?}; the router passes {run, task, corpus?},
// so source/target fall back to corpus[0]/corpus[1]. Big text goes to files under <run>/migrate/; replies stay <= 2 KB.
export const meta = {
  name: 'migrate',
  description: 'Lossless migration plan: per-surface inventory, per-part dispositions (keep|optimize|merge|adopt|library|skip), disjoint packages, an adversarial critic and one revision pass',
  whenToUse: 'The router names it for a migrate/port/lossless-merge request on a named corpus (size L). Pass {run, source, target, surfaces?}.',
  phases: [
    { title: 'Inventory', model: '{{model:explore}}' },
    { title: 'Dispositions', model: '{{model:judge}}' },
    { title: 'Packages', model: '{{model:judge}}' },
    { title: 'Critic', model: '{{model:judge}}' },
    { title: 'Revision', model: '{{model:judge}}' },
  ],
}

const A = (args && typeof args === 'object') ? args : {}
const run = String(A.run || '.claude/runs/migrate').replace(/\/+$/, '')
const at = (f) => `${run}/${f}`
const ok = (x) => x !== null && x !== undefined
const nn = (i) => String(i + 1).padStart(2, '0')
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'surface'
const list = (v) => (Array.isArray(v) ? v.map(String).filter(Boolean) : [])
const SLICE = { type: 'object', required: ['path', 'summary'], properties: { path: { type: 'string' }, summary: { type: 'string' }, count: { type: 'integer' } } }
const DISP = { type: 'object', required: ['path', 'groups'], properties: { path: { type: 'string' }, groups: { type: 'integer' }, summary: { type: 'string' } } }
const ISSUES = { type: 'object', required: ['issues'], properties: { issues: { type: 'array', items: { type: 'object', required: ['id', 'severity', 'text'],
  properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['high', 'med', 'low'] }, text: { type: 'string' } } } } } }
const corpus = list(A.corpus)
const source = A.source || corpus[0] || 'the source named in the task'
const target = A.target || corpus[1] || 'the target named in the task'
const surfaces = list(A.surfaces).length ? list(A.surfaces) : ['agents', 'skills', 'hooks', 'commands', 'rules', 'scripts', 'docs']
const task = A.task ? ` Task: ${A.task}.` : ''
const RULES = 'Nothing of the target may be lost: every target component keeps a disposition. Read real files; do not edit anything outside the run folder.'

phase('Inventory')
const inv = await pipeline(surfaces, (s, _item, i) => agent(
  `Inventory surface "${s}" of the source ${source} and of the target ${target}.${task} ${RULES} ` +
  `Write ${at('migrate/inventory/' + nn(i) + '-' + slug(s) + '.json')}: one record per component {id, side (source|target), path, purpose, size}. ` +
  'Return {path, summary (5 lines max), count (records)}; the reply stays under 2 KB.',
  { agentType: 'general-purpose', model: '{{model:explore}}', label: 'explore:surface:' + slug(s), phase: 'Inventory', schema: SLICE }))
const inventory = inv.map((r, i) => (ok(r) ? { surface: surfaces[i], ...r } : null)).filter(Boolean)
const dead = surfaces.filter((_, i) => !ok(inv[i])).map(s => 'inventory:' + s)
if (dead.length) log(`inventory surfaces with no result (not covered): ${dead.join(', ')}`)
if (!inventory.length) return { run, inventory, dispositions: [], packages: null, critic: 0, revised: false, dead, incomplete: true }

phase('Dispositions')
const disp = await pipeline(inventory, (f, _item, i) => agent(
  `Read the inventory ${f.path} (surface ${f.surface}).${task} ${RULES} Write ${at('migrate/dispositions/' + nn(i) + '.json')}: groups of components, ` +
  'each with action keep|optimize|merge|adopt|library|skip, the target path and a one-line reason. Return {path, groups, summary}; the reply stays under 2 KB.',
  { agentType: 'planning-director', model: '{{model:judge}}', label: 'dispositions:' + (i + 1), phase: 'Dispositions', schema: DISP }))
const dispositions = disp.filter(ok)
disp.forEach((r, i) => { if (!ok(r)) dead.push('dispositions:' + inventory[i].surface) })

phase('Packages')
const packages = await agent(`Read the disposition files ${dispositions.map(d => d.path).join(', ') || '(none)'}.${task} ` +
  `Write ${at('migrate/PACKAGES.json')}: implementation packages with disjoint owned_paths, depends_on, goal, brief and acceptance commands that exit. ` +
  'Return {path, summary (5 lines max), count (packages)}.',
{ agentType: 'spec-architect', model: '{{model:judge}}', label: 'packages', phase: 'Packages', schema: SLICE })
if (!ok(packages)) {
  log('packages agent returned nothing: nothing to critique')
  dead.push('packages')
  return { run, inventory, dispositions, packages: null, critic: 0, revised: false, dead, incomplete: true }
}

phase('Critic')
const critic = await agent(`Adversarially critique ${packages.path} against the dispositions in ${run}/migrate/dispositions/. ` +
  'Hunt lost components, overlapping owned_paths, missing dependencies, acceptance commands that cannot fail, unsafe ordering. ' +
  'Report at most 30 issues, each {id, severity high|med|low, text}; only issues you can show from the files.',
{ agentType: 'santa-reviewer', model: '{{model:judge}}', label: 'critic', phase: 'Critic', schema: ISSUES })
const issues = ok(critic) && Array.isArray(critic.issues) ? critic.issues : []
if (!ok(critic)) dead.push('critic')

let revised = false
if (issues.some(i => i.severity !== 'low')) {
  phase('Revision')
  const rev = await agent(`Revise ${packages.path} to fix these critic issues (drop any you can show is wrong, with the reason):\n` +
    issues.map(i => `- [${i.severity}] ${i.id}: ${i.text}`).join('\n') +
    `\nRewrite ${packages.path} in place and append what changed and why to ${at('migrate/REVISION.md')}. Return {path, summary, count}.`,
  { agentType: 'planning-director', model: '{{model:judge}}', label: 'revision', phase: 'Revision', schema: SLICE })
  revised = ok(rev)
  if (!revised) dead.push('revision')
}

return { run, inventory, dispositions, packages: packages.path, critic: issues.length, revised, dead, incomplete: dead.length > 0 }
