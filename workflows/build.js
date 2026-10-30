// GENERATED from workflows/src/build.js.tpl by scripts/build_workflows.py (tier max20). Do not edit; edit the template.
// build — implement a PACKAGES.json file wave by wave: spec -> implement -> verify -> (diagnose -> fix -> reverify) x2
// per package, then integrate, adversarial review, a final judge and a final verification.
// Args: {packages_file, run, worktree, notes?, waves?[[id]], max_parallel? (1-8, default 4), task?, corpus?[], tier_hint?}.
// The script cannot read files: one explore agent lists the packages; the caller passes max_parallel (the launcher's
// state/launch-caps/<pid>.json is read by the router/caller, never by a script). Specs/reports live in the run folder.
// Review runs one santa per chunk of <= 6 owned_paths, at most 8 chunks per package (the chunk grows past 48 paths);
// a null reviewer retries once (halved); a null spec/verify/judge retries once with a RETRY note; uncovered scope is
// returned (review_uncovered), never silently dropped. Parallel reviewers and verifiers keep notes in <run>/notes/.
export const meta = {
  name: 'build',
  description: 'Build a packages file: per package spec, implement, verify and a two-round fix loop in dependency waves; then integrate, Santa review per package, final judge and final verify',
  whenToUse: 'The router names it to build/implement the packages of a PACKAGES.json (size L). Pass {packages_file, run, worktree, notes?, waves?, max_parallel?}.',
  phases: [
    { title: 'Packages', model: 'sonnet' },
    { title: 'Integrate', model: 'sonnet' },
    { title: 'Review', model: 'opus' },
    { title: 'Judge', model: 'opus' },
    { title: 'Verify', model: 'haiku' },
  ],
}

const A = (args && typeof args === 'object') ? args : {}
const run = String(A.run || '.claude/runs/build').replace(/\/+$/, '')
const at = (f) => `${run}/${f}`
const ESC = A.tier_hint === 'escalate'   // set by workflow-model-guard / the router (I-5)
const up = (o, m) => (ESC ? { ...o, model: m } : o)   // executors only; judges never move
const ok = (x) => x !== null && x !== undefined
const CHUNK = 6                                  // owned_paths entries per reviewer (a glob counts as one)
const MAX_CHUNKS = 8                             // per package, like review.js: CHUNK grows past 48 paths
const chunkSize = (n) => Math.max(CHUNK, Math.ceil(n / MAX_CHUNKS))
const splitN = (xs, n) => { const o = []; for (let i = 0; i < xs.length; i += n) o.push(xs.slice(i, i + n)); return o }
const fname = (s) => String(s).replace(/[^A-Za-z0-9._-]/g, '-')   // labels carry ':' (illegal in NTFS names)
const RETRY = 'RETRY: the previous run of exactly this task hit its turn cap and returned nothing. Create the artifact within ' +
  'your first 5 turns, append to it as you go, and return (StructuredOutput) by the deliver-by turn in your start context, ' +
  'listing what you could not cover as uncovered. '
async function once(label, call) {              // call(notePrefix, labelSuffix) -> result | null; ONE retry, never more
  const r = await call('', '')
  if (ok(r)) return r
  log(`${label} returned nothing (turn cap or dead agent): retrying once`)
  return call(RETRY, ':retry')
}
const PKF = A.packages_file || (Array.isArray(A.corpus) && A.corpus[0]) || 'the packages file named in the task'
const W = A.worktree || 'the current repository'
const MAXP = Number.isInteger(A.max_parallel) && A.max_parallel >= 1 && A.max_parallel <= 8 ? A.max_parallel : 4

const LIST = { type: 'object', required: ['packages'], properties: { packages: { type: 'array', items: { type: 'object', required: ['id', 'title'],
  properties: { id: { type: 'string' }, title: { type: 'string' }, risk: { type: 'string' }, depends_on: { type: 'array', items: { type: 'string' } }, owned_paths: { type: 'array', items: { type: 'string' } } } } } } }
const SPEC = { type: 'object', properties: { spec_file: { type: 'string' }, steps: { type: 'number' }, summary: { type: 'string' } }, required: ['spec_file', 'summary'] }
const IMPL = { type: 'object', properties: { status: { type: 'string', enum: ['done', 'partial', 'blocked'] }, files_changed: { type: 'array', items: { type: 'string' } }, tests_added: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['status', 'files_changed', 'notes'] }
const VERIFY = { type: 'object', properties: { pass: { type: 'boolean' }, failures: { type: 'array', items: { type: 'object', properties: { check: { type: 'string' }, output: { type: 'string' } }, required: ['check', 'output'] } }, summary: { type: 'string' } }, required: ['pass', 'failures', 'summary'] }
const FINDINGS = { type: 'object', properties: { findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['high', 'med', 'low'] }, file: { type: 'string' }, line: { type: 'number' }, issue: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'file', 'issue', 'fix'] } }, incomplete: { type: 'boolean' }, uncovered: { type: 'array', items: { type: 'string' } } }, required: ['findings'] }
const JUDGE = { type: 'object', properties: { go: { type: 'boolean' }, gaps: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['high', 'med', 'low'] }, gap: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'gap', 'fix'] } }, summary: { type: 'string' } }, required: ['go', 'gaps', 'summary'] }

const SAFE = `Ground rules: work only in ${W}; never git commit, stash, checkout, reset or clean; never start servers, daemons or services; ` +
  'never apply system-level changes (systemd units, sudo, swap, package installs, shell profiles): build them as code plus tests with dry-run modes; ' +
  'files change only through Edit/Write (no sed -i, heredoc or interpreter writes); keep every Write/Edit under ~2,500 words; ' +
  'no secrets or machine-specific values in tracked files; everything must run on Ubuntu and Windows. Run single test files while building, ' +
  `never more than one test run at a time. Other packages are built at the same time, each on its own owned_paths (see ${PKF}); never touch theirs.` +
  (A.notes ? ` Notes: ${A.notes}` : '')
const entry = (p) => `Package "${p.id}" (${p.title}). Its full entry (goal, brief, owned_paths, depends_on, acceptance) is in ${PKF}; read it first. Owned paths are the ONLY paths it may touch.`
const stepsFile = (p) => at('PKG-' + p.id + '-STEPS.md')
const reportFile = (p) => at('PKG-' + p.id + '-REPORT.md')
const specPrompt = (p, extra) => `You are the architect writing the implementation spec an engineer will follow literally. ${entry(p)}\n${extra || ''}\n` +
  `Read the real code in ${W} before specifying. Write ${stepsFile(p)} in parts (each Write under ~2,500 words): numbered test-first steps; per step the exact file, ` +
  'functions, a code sketch for non-trivial logic, edge cases, fail-open and timeout behaviour, Windows handling and the command that proves it. ' +
  'End with the acceptance commands and a rollback note. Return {spec_file, steps, summary}.'
const implPrompt = (p, specFile) => `Implement ${entry(p)}\nFollow ${specFile} step by step, tests first.\n${SAFE}\n` +
  `Run every acceptance command of the package. If the spec is wrong or impossible, deviate minimally and record why. Write ${reportFile(p)} (what changed, deviations, test output tails). Return the structured result.`
const verifyPrompt = (p, strict) => `Verify ${entry(p)} The worktree is ${W}. Do not edit any file under the worktree; your only artifact is ${at('notes/verify-' + fname(p.id) + '.md')} (create it within your first 5 turns, append as you go). 1) Run every acceptance command of the package. ` +
  `2) Run the tests for the owned paths${strict ? ', then the full suite; every failure counts' : '; other packages are mid-build, so count only failures in code this package owns or calls'}. ` +
  '3) Smoke-run each hook the package changed with realistic, malformed and empty stdin: no crash, exits within its timeout, fails open. ' +
  `4) git status: flag changed files that belong to no package. 5) Read ${stepsFile(p)} and confirm each step is done (not stubbed). ` +
  'Return pass=false with exact failing commands and output tails when anything fails.'

async function buildPackage(p, ph, strict, extra) {
  const spec = await once('spec:' + p.id, (note, sfx) => agent(note + specPrompt(p, extra),
    { agentType: 'spec-architect', model: 'opus', label: 'spec:' + p.id + sfx, phase: ph, schema: SPEC }))
  if (!ok(spec)) return { id: p.id, status: 'spec-failed', failures: [{ check: 'spec', output: 'spec agent returned nothing' }] }
  let impl = await agent(implPrompt(p, spec.spec_file), up({ agentType: 'implementation-engineer', model: 'sonnet', label: 'build:' + p.id, phase: ph, schema: IMPL }, 'opus'))
  let ver = await once('verify:' + p.id, (note, sfx) => agent(note + verifyPrompt(p, strict),
    { agentType: 'qa-verifier', model: 'haiku', label: 'verify:' + p.id + sfx, phase: ph, schema: VERIFY }))
  for (let round = 1; round <= 2 && ok(ver) && !ver.pass; round++) {
    const fixFile = at('PKG-' + p.id + '-FIX-' + round + '.md')
    const fails = (Array.isArray(ver.failures) ? ver.failures : []).map(f => `- ${f.check}: ${f.output}`).join('\n')
    await agent(`${entry(p)}\nIt failed verification (round ${round}). Failures:\n${fails}\n\nRead ${spec.spec_file}, ${reportFile(p)} and the real code in ${W}. ` +
      `Find the root cause (not the symptom) and write the exact fix steps to ${fixFile} (files, code sketches, proving commands). Return a one-paragraph diagnosis.`,
    { agentType: 'debug-detective', model: 'opus', label: 'diagnose:' + p.id + ':' + round, phase: ph })
    impl = await agent(`Previous attempt failed verification. Apply the fix in ${fixFile} for ${entry(p)}\n${SAFE}\nAppend what you did to ${reportFile(p)}. Return the structured result.`,
      up({ agentType: 'implementation-engineer', model: 'sonnet', label: 'fix:' + p.id + ':' + round, phase: ph, schema: IMPL }, 'opus'))
    ver = await once('reverify:' + p.id + ':' + round, (note, sfx) => agent(note + verifyPrompt(p, strict),
      { agentType: 'qa-verifier', model: 'haiku', label: 'reverify:' + p.id + ':' + round + sfx, phase: ph, schema: VERIFY }))
  }
  return { id: p.id, status: ok(ver) && ver.pass ? 'pass' : 'FAILED', impl: ok(impl) ? impl.status : null,
    failures: ok(ver) ? (ver.failures || []).slice(0, 5) : [{ check: 'verifier', output: 'returned nothing' }], summary: ok(ver) ? ver.summary : null }
}

// ---------- package list and waves ----------
phase('Packages')
const listed = await agent(`Read ${PKF} and list every package: {id, title, risk, depends_on, owned_paths}. Do not edit anything. ` +
  'Return {packages}; owned_paths verbatim and COMPLETE from the file (the list may be long; never summarise, sample or truncate it; a dropped path is never reviewed).',
  { agentType: 'general-purpose', model: 'haiku', label: 'explore:packages', phase: 'Packages', schema: LIST })
if (!ok(listed) || !Array.isArray(listed.packages) || !listed.packages.length) {
  return { run, error: 'could not list packages', packages: [], dead: ['list'], incomplete: true }
}
const all = listed.packages.filter(p => ok(p) && p.id)
log(`packages listed: ${all.map(p => `${p.id}:${Array.isArray(p.owned_paths) ? p.owned_paths.length : 0}`).join(' ')}`)
const byId = Object.fromEntries(all.map(p => [p.id, p]))
const integ = byId.integrate || null
const pkgs = all.filter(p => p.id !== 'integrate')

function levels(items) {
  const ids = new Set(items.map(p => p.id))
  const placed = new Set()
  const out = []
  let rest = items.slice()
  while (rest.length) {
    const lvl = rest.filter(p => (p.depends_on || []).every(d => !ids.has(d) || placed.has(d)))
    if (!lvl.length) { log(`dependency cycle among ${rest.map(p => p.id).join(', ')}: building them in one wave`); out.push(rest); break }
    lvl.forEach(p => placed.add(p.id))
    out.push(lvl)
    rest = rest.filter(p => !placed.has(p.id))
  }
  return out
}
const chunk = (xs) => splitN(xs, MAXP)
let waves
if (Array.isArray(A.waves) && A.waves.length) {
  const unknown = A.waves.flat().filter(id => !byId[id])
  if (unknown.length) log(`waves name unknown packages (skipped): ${unknown.join(', ')}`)
  waves = A.waves.map(w => (Array.isArray(w) ? w : [w]).map(id => byId[id]).filter(p => ok(p) && p.id !== 'integrate')).filter(w => w.length)
} else {
  waves = levels(pkgs).flatMap(chunk)
}

const results = []
for (let w = 0; w < waves.length; w++) {
  const wave = waves[w]
  log(`wave ${w + 1}/${waves.length}: ${wave.map(p => p.id).join(', ')}`)
  const r = await parallel(wave.map(p => () => buildPackage(p, 'Packages', false)))
  results.push(...r.map((x, i) => (ok(x) ? x : { id: wave[i].id, status: 'FAILED', failures: [{ check: 'pipeline', output: 'returned nothing' }] })))
}

// ---------- integrate ----------
let intRes = null
if (integ) {
  phase('Integrate')
  intRes = await buildPackage(integ, 'Integrate', true, 'Results of the other packages (FAILED ones need your attention or a clear note): ' +
    JSON.stringify(results.map(r => ({ id: r.id, status: r.status, failures: (r.failures || []).slice(0, 3) }))))
}

// ---------- review ----------
phase('Review')
const santaPrompt = (p, paths, tag, note) => `${note}Adversarial review of ${entry(p)} Keep working notes in ${at('notes/santa-' + fname(p.id) + '-' + fname(tag) + '.md')}; never write SANTA-REVIEW.md. The changes are uncommitted in ${W}: use git diff on ` +
  (paths.length ? `ONLY these owned paths (other chunks have their own reviewer): ${paths.join(', ')}` : 'its owned_paths') +
  ` plus untracked files there. Spec: ${stepsFile(p)}. Hunt real bugs: crashes, hooks that fail closed or hang, lost behaviour, races on shared ` +
  'state files, Windows breakage, secrets or machine data in tracked files, token-cost regressions. Verify each finding against the code before ' +
  'reporting (drop it if you cannot show the failing input). Return confirmed findings only; set incomplete=true and list uncovered paths if you stop early.'
const santa = (p, paths, tag, note) => agent(santaPrompt(p, paths, tag, note),
  { agentType: 'santa-reviewer', model: 'opus', label: 'santa:' + p.id + ':' + tag, phase: 'Review', schema: FINDINGS })
const scopeOf = (ps) => (ps.length ? ps : ['<all owned_paths>'])
// what a reviewer left unread: all of its scope when dead, its own list (or all of its scope) when it reports incomplete
const lostOf = (r, ps) => (!ok(r) ? scopeOf(ps) : r.incomplete ? (Array.isArray(r.uncovered) && r.uncovered.length ? r.uncovered : scopeOf(ps)) : [])
async function reviewChunk(p, paths, n) {        // {findings, uncovered}; retries ONCE: halves when splittable, else same scope + RETRY
  const tag = String(n)
  const first = await santa(p, paths, tag, '')
  if (ok(first)) return { findings: Array.isArray(first.findings) ? first.findings : [], uncovered: lostOf(first, paths) }
  log(`santa:${p.id}:${tag} returned nothing (turn cap or dead agent): retrying once${paths.length > 1 ? ' as two halves' : ''}`)
  const half = Math.ceil(paths.length / 2)
  const parts = paths.length > 1 ? [paths.slice(0, half), paths.slice(half)] : [paths]
  const again = await parallel(parts.map((ps, i) => () => santa(p, ps, tag + (parts.length > 1 ? 'ab'[i] : ':retry'), RETRY)))
  const findings = again.flatMap((r) => (ok(r) && Array.isArray(r.findings) ? r.findings : []))
  const uncovered = parts.flatMap((ps, i) => lostOf(again[i], ps))
  return { findings, uncovered }
}
const pathsOf = (p) => (Array.isArray(p.owned_paths) ? p.owned_paths.filter((x) => typeof x === 'string') : [])
const planned = pkgs.reduce((a, p) => a + Math.max(1, Math.ceil(pathsOf(p).length / chunkSize(pathsOf(p).length))), 0)
log(`review fan-out: ${planned} santa reviewers across ${pkgs.length} packages (max ${MAX_CHUNKS} per package)`)
const reviewed = await parallel(pkgs.map((p) => async () => {
  const paths = pathsOf(p)
  const chunks = splitN(paths, chunkSize(paths.length))
  const per = await parallel((chunks.length ? chunks : [[]]).map((ps, i) => () => reviewChunk(p, ps, i + 1)))
  const got = per.filter(ok)
  return { pkg: p.id, chunks: chunks.length || 1, findings: got.flatMap((r) => r.findings),
    uncovered: got.flatMap((r) => r.uncovered).concat(per.some((r) => !ok(r)) ? ['<chunk thunk failed>'] : []) }
}))
const rv = reviewed.map((r, i) => r || { pkg: pkgs[i].id, chunks: 0, findings: [], uncovered: ['<review failed>'] })
const dead = rv.filter((r) => r.uncovered.length).map((r) => 'review:' + r.pkg)
const uncoveredAll = rv.filter((r) => r.uncovered.length).map((r) => ({ pkg: r.pkg, paths: r.uncovered }))
if (uncoveredAll.length) log(`review left uncovered: ${uncoveredAll.map((u) => u.pkg + ' [' + u.paths.join(', ') + ']').join('; ')}`)
const findings = rv.flatMap((r) => r.findings.map((f) => ({ pkg: r.pkg, ...f }))).filter((f) => f.severity !== 'low')
log(`review: ${rv.reduce((a, r) => a + r.chunks, 0)} reviewer chunk(s) over ${pkgs.length} package(s), ${findings.length} high/med findings`)
let reviewVerify = null
if (findings.length) {
  const triage = await agent(`Triage these confirmed review findings for ${W} and write one fix spec per affected package to ${at('REVIEW-FIX-<package>.md')} ` +
    '(exact files, code sketches, proving commands; drop any finding you can show is wrong, with the reason):\n' +
    findings.map(f => `- [${f.severity}] ${f.pkg} ${f.file}:${f.line || ''} ${f.issue} -> ${f.fix}`).join('\n') + '\nReturn the list of packages that got a fix spec.',
  { agentType: 'planning-director', model: 'opus', label: 'triage', phase: 'Review' })
  if (!ok(triage)) dead.push('triage')
  const touched = [...new Set(findings.map(f => f.pkg))].filter(id => byId[id])
  await parallel(touched.map(id => () => agent(`Apply ${at('REVIEW-FIX-' + id + '.md')} if it exists (skip quietly if every finding for this package was dropped). ${entry(byId[id])}\n${SAFE}\nReturn the structured result.`,
    up({ agentType: 'implementation-engineer', model: 'sonnet', label: 'review-fix:' + id, phase: 'Review', schema: IMPL }, 'opus'))))
  const allPkg = integ || { id: 'all', title: 'every package' }
  reviewVerify = await once('verify:after-review', (note, sfx) => agent(note + verifyPrompt(allPkg, true),
    { agentType: 'qa-verifier', model: 'haiku', label: 'verify:after-review' + sfx, phase: 'Review', schema: VERIFY }))
}

// ---------- judge ----------
phase('Judge')
const judgePrompt = `Final judgment of ${W} against ${PKF}: every package goal met, acceptance commands pass, nothing lost or duplicated, ` +
  `tests green. Write ${at('FINAL-JUDGMENT.md')} in parts. Return go and gaps.`
let judge = await once('judge', (note, sfx) => agent(note + judgePrompt,
  { agentType: 'spec-architect', model: 'opus', label: 'judge' + sfx, phase: 'Judge', schema: JUDGE }))
const serious = (ok(judge) && Array.isArray(judge.gaps) ? judge.gaps : []).filter(g => g.severity !== 'low')
if (!ok(judge)) dead.push('judge')
if (serious.length) {
  await agent(`Write exact fix steps for these final-judgment gaps to ${at('JUDGE-FIX.md')}, grouped by owning package (owners in ${PKF}), with proving commands:\n` +
    serious.map(g => `- [${g.severity}] ${g.gap} -> ${g.fix}`).join('\n'),
  { agentType: 'spec-architect', model: 'opus', label: 'judge-fix-spec', phase: 'Judge' })
  await agent(`Apply every step in ${at('JUDGE-FIX.md')}.\n${SAFE}\nAppend a log to ${at('JUDGE-FIX-REPORT.md')}. Return the structured result.`,
    up({ agentType: 'implementation-engineer', model: 'sonnet', label: 'judge-fix', phase: 'Judge', schema: IMPL }, 'opus'))
  const rejudgePrompt = `Re-judge only these gaps after the fixes in ${at('JUDGE-FIX-REPORT.md')}, in ${W}:\n${serious.map(g => '- ' + g.gap).join('\n')}\n` +
    `Append the outcome to ${at('FINAL-JUDGMENT.md')}. Return go and the gaps that remain.`
  const re = await once('rejudge', (note, sfx) => agent(note + rejudgePrompt,
    { agentType: 'spec-architect', model: 'opus', label: 'rejudge' + sfx, phase: 'Judge', schema: JUDGE }))
  if (ok(re)) judge = re
  else dead.push('rejudge')
}

// ---------- final verification ----------
phase('Verify')
const finPrompt = `Final verification of ${W}. Do not edit tracked files. Run the full test suite, parse every tracked JSON file, run the documented installer render in dry-run, ` +
  'scan every changed file for secrets and machine-specific values (never print them), lint changed code for Windows portability, check new scripts for shell writes and server starts, ' +
  `and node --check every saved workflow. Write ${at('FINAL-VERIFY.md')}. Return pass and failures.`
const fin = await once('final-verify', (note, sfx) => agent(note + finPrompt,
  { agentType: 'qa-verifier', model: 'haiku', label: 'final-verify' + sfx, phase: 'Verify', schema: VERIFY }))
if (!ok(fin)) dead.push('final-verify')

const failedPkgs = results.filter(r => r.status !== 'pass').map(r => r.id)
return {
  run,
  packages: results.map(r => ({ id: r.id, status: r.status, failures: (r.failures || []).slice(0, 5) })),
  integrate: intRes && { status: intRes.status, failures: (intRes.failures || []).slice(0, 5) },
  review_findings: findings.length,
  review_uncovered: uncoveredAll,
  review_verify: reviewVerify && { pass: reviewVerify.pass, failures: (reviewVerify.failures || []).slice(0, 5) },
  judge: ok(judge) ? { go: judge.go, gaps: judge.gaps, summary: judge.summary } : null,
  final_verify: ok(fin) ? { pass: fin.pass, failures: fin.failures, summary: fin.summary } : null,
  dead,
  incomplete: dead.length > 0 || uncoveredAll.length > 0 || failedPkgs.length > 0 || (intRes !== null && intRes.status !== 'pass') || !(ok(fin) && fin.pass),
}
