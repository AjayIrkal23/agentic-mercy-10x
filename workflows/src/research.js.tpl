// research — one reader per named source (pipeline, no barrier), then one judge writes the feature map.
// Args: {run, question?, sources?[], url?, task?, corpus?[], tier_hint?}; the router passes {run, task, corpus?, url?},
// so question falls back to task and sources to corpus, then [url]. Web-only questions belong to /deep-research.
export const meta = {
  name: 'research',
  description: 'Research a question over named sources (paths, docs, changelogs, URLs): one reader per source writes cited facts, a spec-architect writes research/00-FEATURES.md',
  whenToUse: 'The router names it for a research/compare-the-docs/changelog study on a named corpus (size >= M). Pass {run, question, sources}.',
  phases: [
    { title: 'Read', model: '{{model:explore}}' },
    { title: 'Synthesis', model: '{{model:judge}}' },
  ],
}

const A = (args && typeof args === 'object') ? args : {}
const run = String(A.run || '.claude/runs/research').replace(/\/+$/, '')
const at = (f) => `${run}/${f}`
const ok = (x) => x !== null && x !== undefined
const nn = (i) => String(i + 1).padStart(2, '0')
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'source'
const list = (v) => (Array.isArray(v) ? v.map(String).filter(Boolean) : [])
const SLICE = { type: 'object', required: ['path', 'summary'], properties: { path: { type: 'string' }, summary: { type: 'string' }, count: { type: 'integer' } } }
const question = A.question || A.task || 'the question described in the conversation'
const sources = list(A.sources).length ? list(A.sources) : list(A.corpus).length ? list(A.corpus) : A.url ? [String(A.url)] : []
if (!sources.length) return { run, error: 'no sources' }

phase('Read')
const slices = await pipeline(sources, (s, _item, i) => agent(
  `Research "${question}" using only this source: ${s}. Write ${at('research/' + nn(i) + '-' + slug(s) + '.md')} with cited facts ` +
  '(file/section/URL per claim), no speculation; do not edit anything else. Return {path, summary (5 lines max), count (number of facts)}; the reply stays under 2 KB.',
  { agentType: 'general-purpose', model: '{{model:explore}}', label: 'explore:source:' + (i + 1), phase: 'Read', schema: SLICE }))
const done = slices.map((r, i) => (ok(r) ? { source: sources[i], ...r } : null)).filter(Boolean)
const dead = sources.filter((_, i) => !ok(slices[i]))
if (dead.length) log(`sources with no result (not covered): ${dead.join(', ')}`)

let map = null
if (done.length) {
  phase('Synthesis')
  map = await agent(`Write ${at('research/00-FEATURES.md')} answering "${question}": one map of what, where, used here / not used, and an adoption note per item, ` +
    `citing these slice files: ${done.map(d => d.path).join(', ')}. Name the sources that were not covered: ${dead.join(', ') || 'none'}. ` +
    'Return {path, summary (5 lines max), count (items in the map)}.',
  { agentType: 'spec-architect', model: '{{model:judge}}', label: 'synthesis', phase: 'Synthesis', schema: SLICE })
}

return { run, slices: done, dead, map: ok(map) ? map.path : null, incomplete: dead.length > 0 || !ok(map) }
