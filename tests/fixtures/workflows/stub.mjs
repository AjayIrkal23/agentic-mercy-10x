// stub.mjs — a fake Workflow runtime for tests/test_workflows_lib.py (no model calls, no files written).
// Usage: node stub.mjs <script.js> <scenario.json>
// Prints ONE JSON line: {"meta", "calls", "logs", "result", "error"}; each call carries promptHead (160 chars)
// and the full prompt. Exit 0 even when the script throws
// (the message is in "error"); exit 2 only when the stub cannot read its own inputs.
// Scenario: {args, default, replies: [{label: <regex>, value}], workflow: {<name>: <result>}, workflow_unavailable}.
// A reply value of null models a skipped or dead agent (agent() returns null).
import fs from 'node:fs'
import vm from 'node:vm'

const fail = (msg) => { process.stderr.write(`stub: ${msg}\n`); process.exit(2) }
const [, , scriptPath, scenarioPath] = process.argv
if (!scriptPath || !scenarioPath) fail('usage: node stub.mjs <script.js> <scenario.json>')
let src, sc
try {
  src = fs.readFileSync(scriptPath, 'utf8')
  sc = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'))
} catch (e) { fail(String((e && e.message) || e)) }

// 1. Split `export const meta = {...}` (a pure literal) from the body; brace-match, skipping strings.
const m = /export\s+const\s+meta\s*=\s*\{/.exec(src)
if (!m) fail('no `export const meta = {` in script')
let i = m.index + m[0].length - 1
let depth = 0
let q = null
for (; i < src.length; i++) {
  const c = src[i]
  if (q) {
    if (c === '\\') { i++; continue }
    if (c === q) q = null
    continue
  }
  if (c === "'" || c === '"' || c === '`') q = c
  else if (c === '{') depth++
  else if (c === '}' && --depth === 0) { i++; break }
}
if (src[i] === ';') i++
const metaDecl = src.slice(m.index, i).replace(/^export\s+/, '')
const body = src.slice(i)
const code = `${metaDecl}\n__out.meta = meta;\n__out.result = (async () => {\n${body}\n})();`

// 2. The fake runtime.
const calls = []
const logs = []
let current = null
let n = 0
const clone = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)))
const pick = (label) => {
  for (const r of sc.replies || []) if (new RegExp(r.label).test(label || '')) return r.value
  return sc.default === undefined ? {} : sc.default
}
const agent = async (prompt, opts = {}) => {
  n++
  calls.push({
    n, phase: opts.phase ?? current, label: opts.label ?? null, agentType: opts.agentType ?? null,
    model: opts.model ?? null, effort: opts.effort ?? null, schema: !!opts.schema,
    promptHead: String(prompt).slice(0, 160), prompt: String(prompt),
  })
  const v = pick(opts.label)
  return v === null ? null : clone(v)
}
const parallel = async (thunks) => Promise.all(thunks.map((t) => Promise.resolve().then(t).catch(() => null)))
const pipeline = async (items, ...stages) => Promise.all(items.map(async (item, idx) => {
  let prev = item
  for (const st of stages) {
    try { prev = await st(prev, item, idx) } catch { return null }
  }
  return prev
}))
const workflow = async (name, a) => {
  if (sc.workflow_unavailable) throw new Error('workflow() unavailable')
  calls.push({ n: ++n, phase: current, label: `workflow:${name}`, workflow: true, args: clone(a) })
  if (!sc.workflow || !(name in sc.workflow)) throw new Error(`unknown workflow ${name}`)
  return clone(sc.workflow[name])
}
const throwing = (what) => () => { throw new Error(`${what} is unavailable in workflow scripts`) }
const SafeDate = function (...a) {
  if (!a.length) throwing('new Date()')()
  return new Date(...a)
}
SafeDate.now = throwing('Date.now()')
SafeDate.parse = Date.parse
SafeDate.UTC = Date.UTC
const SafeMath = Object.create(Math)
SafeMath.random = throwing('Math.random()')
const __out = { meta: null, result: undefined }
const ctx = vm.createContext({
  agent, parallel, pipeline, workflow, __out,
  phase: (t) => { current = t },
  log: (s) => { logs.push(String(s)) },
  args: sc.args, budget: { total: null, spent: () => 0, remaining: () => Infinity },
  Date: SafeDate, Math: SafeMath, JSON, Object, Array, String, Number, Boolean, Map, Set, Promise,
  Error, RegExp, console,
})

let error = null
let timer = null
try {
  vm.runInContext(code, ctx, { timeout: 5000, filename: scriptPath })
  await Promise.race([
    __out.result,
    new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('stub timeout 20s')), 20000) }),
  ])
} catch (e) { error = String((e && e.message) || e) }
if (timer) clearTimeout(timer)
let result
try { result = await __out.result } catch { result = undefined }
process.stdout.write(JSON.stringify({ meta: __out.meta, calls, logs, result: result === undefined ? null : result, error }) + '\n')
