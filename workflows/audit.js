// GENERATED from workflows/src/audit.js.tpl by scripts/build_workflows.py (tier max20). Do not edit; edit the template.
// audit — one cheap reader per surface (pipeline, no barrier), then one judge writes the map.
// Args: {run, root?, surfaces?[], task?, corpus?[], tier_hint?}; the router passes {run, task, corpus?}, so
// surfaces fall back to corpus, then to the whole tree. Every reply stays <= 2 KB; findings go to files.
export const meta = {
  name: 'audit',
  description: 'Audit a codebase by surface: one reader per surface writes audit/NN-<surface>.md, then an audit-specialist writes audit/00-MAP.md',
  whenToUse: 'The router names it for an audit/tech-debt/health-check request on a named corpus (size >= M). Pass {run, root?, surfaces?, task?}.',
  phases: [
    { title: 'Slices', model: 'haiku' },
    { title: 'Map', model: 'opus' },
  ],
}

const A = (args && typeof args === 'object') ? args : {}
const run = String(A.run || '.claude/runs/audit').replace(/\/+$/, '')
const at = (f) => `${run}/${f}`
const ok = (x) => x !== null && x !== undefined
const nn = (i) => String(i + 1).padStart(2, '0')
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'surface'
const list = (v) => (Array.isArray(v) ? v.map(String).filter(Boolean) : [])
const SLICE = { type: 'object', required: ['path', 'summary'], properties: { path: { type: 'string' }, summary: { type: 'string' }, count: { type: 'integer' } } }
const root = A.root || 'the repository'
const focus = A.task || 'architecture, dead code, risk, conventions'
const surfaces = list(A.surfaces).length ? list(A.surfaces) : list(A.corpus).length ? list(A.corpus) : ['whole-tree']

phase('Slices')
const slices = await pipeline(surfaces, (s, _item, i) => agent(
  `Audit surface "${s}" of ${root} for: ${focus}. Read the real code (jcodemunch first); do not edit anything. ` +
  `Write ${at('audit/' + nn(i) + '-' + slug(s) + '.md')} (findings with file:line, severity and evidence; a "looks bad but is fine" section). ` +
  'Return {path, summary (5 lines max), count (number of findings)}; the reply stays under 2 KB.',
  { agentType: 'general-purpose', model: 'haiku', label: 'explore:slice:' + slug(s), phase: 'Slices', schema: SLICE }))
const done = slices.map((r, i) => (ok(r) ? { surface: surfaces[i], ...r } : null)).filter(Boolean)
const dead = surfaces.filter((_, i) => !ok(slices[i]))
if (dead.length) log(`surfaces with no result (not covered): ${dead.join(', ')}`)

let map = null
if (done.length) {
  phase('Map')
  map = await agent(`Write ${at('audit/00-MAP.md')}: one ranked map of the audit of ${root} (${focus}) built from these slice files: ` +
    `${done.map(d => d.path).join(', ')}. Merge duplicates, rank by severity and blast radius, keep file:line citations, ` +
    `and list surfaces that were not covered: ${dead.join(', ') || 'none'}. Return {path, summary (5 lines max), count (findings in the map)}.`,
  { agentType: 'audit-specialist', model: 'opus', label: 'map', phase: 'Map', schema: SLICE })
}

return { run, slices: done, dead, map: ok(map) ? map.path : null, incomplete: dead.length > 0 || !ok(map) }
