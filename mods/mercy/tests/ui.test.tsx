import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

// Engine-level tests of the UI deck: the pane's views on two surfaces, the band, alerts
// (sound + desktop notification), the task list, command cards, /ui and the restyles.

const STATUS = '# branch.oid abc1234def\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +1 -0\n1 .M N... 100644 100644 100644 a b src/a.ts\n? notes.md\n'
const SS = 'LISTEN 0 511 0.0.0.0:5173 0.0.0.0:* users:(("node",pid=42,fd=21))\nLISTEN 0 4096 127.0.0.1:27017 0.0.0.0:*\n'
const PR = JSON.stringify({
  number: 12, title: 'Export', state: 'OPEN', url: 'https://github.com/o/r/pull/12', isDraft: false, reviewDecision: '',
  statusCheckRollup: [{ name: 'lint', status: 'COMPLETED', conclusion: 'FAILURE' }, { name: 'test', status: 'COMPLETED', conclusion: 'SUCCESS' }],
})
const presentation = { isFullscreen: true, columns: 160 }
const PANE = { title: 'mercy pulse', isFocused: true, bodyColumns: 90, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }
const BAND = { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 100, scroll: { offset: 0, bodyRows: 12 }, view: {} }

type WorldOpts = {
  testFails?: () => boolean; ghTimesOut?: () => boolean; ss?: () => string; head?: () => string; sid?: () => string; ctx?: () => number
  compactBusy?: () => boolean
}

function world(on: On, opts: WorldOpts = {}) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  const runs: string[] = []
  const toasts: string[] = []
  const statuses: string[] = []
  const opened: string[] = []
  const compacts: string[] = []
  const out =(stdout: string, exitCode = 0) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
  on('session.repo', () => ({ value: { root: '/r', remote: 'git@github.com:o/r.git', internal: false, name: null } }))
  on('session.cwd', () => ({ value: '/r' }))
  on('session.root', () => ({ value: '/r' }))
  on('session.id', () => ({ value: opts.sid?.() ?? 's1' }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 200_000, percent: opts.ctx?.() ?? 20 }, rateLimits: [], cost: { usd: 1 } } }) as never)
  on('session.compact', (_$, e) => {
    if (opts.compactBusy?.()) throw new Error('compact rejected: a turn is running')
    compacts.push(String((e as { instructions?: string }).instructions ?? ''))
    return { messages: [{ role: 'user', text: 'summary of the session so far', toolUses: [] }] } as never
  })
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('settings.read', () => ({ value: {} }))
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('fs.read', () => ({ value: '{"chains":{}}' }))
  // the root's package.json only; on Windows the engine resolves the cwd `/r` to a drive path
  on('fs.exists', (_$, e) => ({ value: /^(?:[A-Za-z]:)?[\\/]r[\\/]package\.json$/.test(e.path) }))
  on('ui.status', (_$, e) => {
    if (e.text) statuses.push(e.text)
    return { value: undefined }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.open', (_$, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } } as never
  })
  on('turn.complete', (_$, e) => ({ text: e.answer, reason: 'answer', usage: e.usage }) as never)
  on('turn.start', (_$, e) => ({ turnId: e.turnId }))
  on('classic.SessionStart', () => ({}))
  on('classic.Notification', () => ({}))
  on('classic.PreToolUse', () => ({}))
  on('classic.PostToolUse', () => ({}))
  on('process.run', (_$, e) => {
    const a = e.argv
    runs.push(a.join(' '))
    if (a[0] === 'git') {
      if (a.includes('status')) return out(opts.head ? STATUS.replace('abc1234def', opts.head()) : STATUS)
      if (a.includes('diff')) return out('4\t2\tsrc/a.ts\n')
      if (a.includes('log')) return out('abc1234\x1ffeat: export\x1f1000\n')
      return out(a.includes('config') ? 'me@example.com\n' : 'main\n')
    }
    if (a[0] === 'gh') {
      if (a[1] === 'pr' && opts.ghTimesOut?.()) throw new Error('gh pr view: still running after 20000 ms')
      return out(a[1] === '--version' ? 'gh version 2.80.0' : PR)
    }
    if (a[0] === 'ss') return out(opts.ss?.() ?? SS)
    if (a[0] === 'npm') return out(JSON.stringify({ react: { current: '18.2.0', wanted: '18.3.1', latest: '19.1.0' } }), 1)
    return out(a.includes('--only') ? '{}' : '')
  })
  on('tool.call', (_$, e) => {
    if (e.tool === 'Bash') return (opts.testFails?.() ? { isError: true, result: 'x', text: 'FAILED test_a' } : { result: 'ok', text: '3 passed' }) as never
    return { result: e.tool === 'Write' ? { filePath: '/r/src/a.ts' } : {} } as never
  })
  return { clock, runs, toasts, statuses, opened, compacts }
}

type Starter = { session: { start(input: { cwd: string; surface: 'terminal'; isInteractive: boolean }): Promise<unknown> } }

async function boot($: Starter, w: ReturnType<typeof world>): Promise<void> {
  await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
  await w.clock.advance(1500)
}

describe('deck: start, pane and band', () => {
  test('an interactive start loads git and CI, opens the pane, and a failing PR fills the band', async ($, on) => {
    const w = world(on)
    await boot($, w)
    expect(w.runs.some(r => r.includes('status --porcelain=v2 --branch'))).toBe(true)
    expect(w.runs.some(r => r.startsWith('gh pr view'))).toBe(true)
    expect(w.opened).toContain('mercy')
    const band = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect((await band.find({ type: 'Text', text: /CI failing on PR #12: lint/ }))?.props['color']).toBe('red')
    expect(await band.find({ key: 'mercy-ci' })).toBeDefined()
    expect(await band.find({ key: 'mercy-ci-pane' })).toBeDefined()
  })

  for (const surface of ['terminal', 'desktop'] as const) {
    test(`every pane view draws on ${surface}; tabs switch; the sparkline is terminal-only`, async ($, on) => {
      const w = world(on)
      await boot($, w)
      await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 4000, isAborted: false, turnId: 't1', usage: { input_tokens: 10, output_tokens: 900, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, model: 'claude-sonnet-5-5' } })
      const pane = await $.ui.mount({ plugin: 'mercy', surface, component: 'Pane', requestId: 'mercy', props: PANE })
      await pane.press({ key: 'tab-git' })
      expect(await pane.find({ text: /⎇ main → origin\/main {2}↑1/ })).toBeDefined()
      expect(await pane.find({ text: /src\/a\.ts {2}\+4 −2/ })).toBeDefined()
      await pane.press({ key: 'tab-ci' })
      expect(await pane.find({ text: /PR #12 Export/ })).toBeDefined()
      expect(await pane.find({ text: /✗ lint/ })).toBeDefined()
      await pane.press({ key: 'tab-usage' })
      expect(await pane.find({ text: /^Context/ })).toBeDefined()
      expect((await pane.findAll({ type: 'Raster' })).length).toBe(surface === 'terminal' ? 1 : 0)
      for (const v of ['overview', 'todo', 'files', 'commands', 'agents', 'hooks', 'brain']) {
        await pane.press({ key: `tab-${v}` })
        expect((await pane.findAll({ type: 'Text' })).length).toBeGreaterThan(0)
      }
    })
  }
})

describe('review fixes (SANTA-ui)', () => {
  test('a slow gh call keeps the CI watch on; the next poll recovers', async ($, on) => {
    let slow = true
    const w = world(on, { ghTimesOut: () => slow })
    await boot($, w)
    expect(w.runs).toContain('gh --version')
    slow = false
    await w.clock.advance(180_000)
    expect(w.runs.filter(r => r.startsWith('gh pr view')).length).toBe(2)
    const ci = await $.command.run({ command: 'ci', args: '', origin: { kind: 'composer' }, presentation })
    expect(ci.text).toContain('PR #12')
  })
  test("a card is drawn only under its own command's row", async ($, on) => {
    world(on)
    on('ui.render', { component: 'CommandOutput' }, ($e, e) => {
      const { Text } = $e.ui.resolve(e)
      return <Text>engine row</Text>
    })
    const wrap = await $.command.run({ command: 'wrapup', args: '', origin: { kind: 'composer' }, presentation })
    const stranger = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'CommandOutput', props: { command: 'ports', args: '', text: (wrap.text ?? '').replace('wrapup', 'ports'), isErrored: false } })
    expect(await stranger.find({ text: 'engine row' })).toBeDefined()
    const own = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'CommandOutput', props: { command: 'wrapup', args: '', text: wrap.text ?? '', isErrored: false } })
    expect(await own.find({ text: 'Session recap' })).toBeDefined()
  })
  test('/clear empties the task list and the turn history', async ($, on) => {
    const w = world(on)
    await boot($, w)
    await $.tool.call({ tool: 'TodoWrite', todos: [{ content: 'old task', status: 'pending', activeForm: 'Old' }] })
    await $.classic.SessionStart({ source: 'clear', session_id: 's2', transcript_path: '' } as never)
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    await pane.press({ key: 'tab-todo' })
    expect(await pane.find({ text: /^No task list yet/ })).toBeDefined()
  })
})

describe('autonomy: nothing needs a command', () => {
  test('ports are watched every minute; a dev server coming up toasts once', async ($, on) => {
    let ss = SS
    const w = world(on, { ss: () => ss })
    await boot($, w)
    await w.clock.advance(1000)
    ss += 'LISTEN 0 511 0.0.0.0:3000 0.0.0.0:* users:(("node",pid=77,fd=20))\n'
    await w.clock.advance(60_000)
    expect(w.toasts).toContain('mercy: ▲ :3000 dev (node) is up')
    await w.clock.advance(60_000)
    expect(w.toasts.filter(t => t.includes(':3000'))).toHaveLength(1)
  })
  test('context past 85% compacts between turns, keeping the plan; at most every 10 minutes', async ($, on) => {
    const w = world(on, { ctx: () => 88 })
    await boot($, w)
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 1000, isAborted: false, turnId: 't1' })
    await w.clock.advance(2000)
    expect(w.compacts).toHaveLength(1)
    expect(w.compacts[0]).toContain('plan')
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 1000, isAborted: false, turnId: 't2' })
    await w.clock.advance(2000)
    expect(w.compacts).toHaveLength(1)
  })
  test('a compaction rejected by a racing prompt is retried after the next turn (SANTA-autonomy)', async ($, on) => {
    let busy = true
    const w = world(on, { ctx: () => 90, compactBusy: () => busy })
    await boot($, w)
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 1000, isAborted: false, turnId: 't1' })
    await w.clock.advance(2000)
    expect(w.compacts).toHaveLength(0)
    busy = false
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 1000, isAborted: false, turnId: 't2' })
    await w.clock.advance(2000)
    expect(w.compacts).toHaveLength(1)
  })
  test("the next session's overview shows the previous session's recap", async ($, on) => {
    let sid = 's1'
    const w = world(on, { sid: () => sid })
    await boot($, w)
    await $.turn.start({ text: 'build it', turnId: 't1' })
    await $.tool.call({ tool: 'Write', file_path: '/r/src/a.ts', content: 'x' })
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 1000, isAborted: false, turnId: 't1' })
    await w.clock.advance(120_000)
    sid = 's2'
    await boot($, w)
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    await pane.press({ key: 'tab-overview' })
    expect(await pane.find({ type: 'Text', text: /^Previous session \(.* ago\): \d+ min · 1 turns · 1 files/ })).toBeDefined()
  })
  test("today's standup is made by itself and shown in the pane with a copy key", async ($, on) => {
    const w = world(on)
    await boot($, w)
    await w.clock.advance(5000)
    expect(w.runs.some(r => r.includes('log --since=') && r.includes('--author=me@example.com'))).toBe(true)
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    await pane.press({ key: 'tab-today' })
    expect((await pane.find({ type: 'Markdown' }))?.props['text']).toContain('feat: export')
    expect(await pane.find({ key: 'copy-standup' })).toBeDefined()
  })
  test('HEAD moving (a commit anywhere) re-probes the indexes', async ($, on) => {
    let head = 'abc1234def'
    const w = world(on, { head: () => head })
    await boot($, w)
    expect(w.runs.some(r => r.includes('index-lifecycle.py reprobe'))).toBe(false)
    head = 'fff9999aaa'
    await w.clock.advance(60_000)
    expect(w.runs.some(r => r.includes('index-lifecycle.py reprobe --root /r'))).toBe(true)
  })
})

describe('refresh through ui.press', () => {
  test('r re-runs git for the git view; a fresh view switch does not', async ($, on) => {
    const w = world(on)
    await boot($, w)
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    const gitRuns = () => w.runs.filter(r => r.includes('status --porcelain=v2')).length
    await pane.press({ key: 'tab-git' })
    await w.clock.advance(10)
    const afterSwitch = gitRuns()
    expect(afterSwitch).toBe(1)
    await pane.press({ key: 'refresh' })
    await w.clock.advance(10)
    expect(gitRuns()).toBe(afterSwitch + 1)
  })
})

describe('alerts', () => {
  test('a long answer plays the done sound and notifies; a short one and quiet mode stay silent', async ($, on) => {
    const w = world(on)
    await $.turn.complete({ reason: 'answer', answer: '## All tests pass.\nDetails', durationMs: 70_000, isAborted: false, turnId: 't1' })
    await w.clock.advance(10)
    expect(w.runs).toContain('canberra-gtk-play -i complete -d claude-code')
    expect(w.runs.some(r => r.startsWith('notify-send') && r.includes('All tests pass.'))).toBe(true)
    expect(w.toasts.some(t => t.startsWith('✓ done in 1m10s'))).toBe(true)
    w.runs.length = 0
    await w.clock.advance(5000)
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 3000, isAborted: false, turnId: 't2' })
    await w.clock.advance(10)
    expect(w.runs.some(r => r.startsWith('canberra'))).toBe(false)
    await $.command.run({ command: 'ui', args: 'quiet', origin: { kind: 'composer' }, presentation })
    await $.turn.complete({ reason: 'answer', answer: 'ok', durationMs: 90_000, isAborted: false, turnId: 't3' })
    await w.clock.advance(10)
    expect(w.runs.some(r => r.startsWith('canberra') || r.startsWith('notify-send'))).toBe(false)
  })
  test('a permission wait plays the input sound and sends a critical notification', async ($, on) => {
    const w = world(on)
    await $.classic.Notification({ message: 'Claude needs your permission to use Bash', title: 'Permission needed', notification_type: 'permission_prompt' } as never)
    await w.clock.advance(10)
    expect(w.runs).toContain('canberra-gtk-play -i message-new-instant -d claude-code')
    expect(w.runs.some(r => r.startsWith('notify-send') && r.includes('-u critical'))).toBe(true)
  })
})

describe('task list, verify flips, cards', () => {
  test("the model's TodoWrite list feeds the todo view and the status text", async ($, on) => {
    const w = world(on)
    await boot($, w)
    await $.tool.call({ tool: 'TodoWrite', todos: [{ content: 'write test', status: 'completed', activeForm: 'Writing' }, { content: 'fix bug', status: 'in_progress', activeForm: 'Fixing' }] })
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    await pane.press({ key: 'tab-todo' })
    expect(await pane.find({ text: /^1\/2 done/ })).toBeDefined()
    expect(await pane.find({ text: '◐ fix bug' })).toBeDefined()
    await w.clock.advance(1000)
    await $.tool.call({ tool: 'Write', file_path: '/r/src/a.ts', content: 'x' })
    expect(w.statuses.at(-1)).toContain('☑ 1/2')
  })
  test('a test command toasts its first failure and the flip back, once each', async ($, on) => {
    let fails = true
    const w = world(on, { testFails: () => fails })
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    fails = false
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    expect(w.toasts.filter(t => t.startsWith('✗ test failed'))).toHaveLength(1)
    expect(w.toasts.filter(t => t === '✓ test passing again')).toHaveLength(1)
  })
  test('/ports prints one tagged line and draws its card; /deps lists majors; /ui focus is reported', async ($, on) => {
    world(on)
    const ports = await $.command.run({ command: 'ports', args: '', origin: { kind: 'composer' }, presentation })
    expect(ports.text).toMatch(/^ports #\d+: 2 listening \(5173 node, 27017 mongodb\)$/)
    const card = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'CommandOutput', props: { command: 'ports', args: '', text: ports.text ?? '', isErrored: false } })
    expect(await card.find({ text: 'Listening ports' })).toBeDefined()
    expect((await card.find({ type: 'Markdown' }))?.props['text']).toContain('[5173](http://localhost:5173)')
    const deps = await $.command.run({ command: 'deps', args: '', origin: { kind: 'composer' }, presentation })
    expect(deps.text).toMatch(/^deps #\d+: 1 outdated \(1 major\) in 1 folder\(s\)$/)
    expect(deps.text).not.toBe(ports.text?.replace('ports', 'deps'))
    const ui = await $.command.run({ command: 'ui', args: 'focus', origin: { kind: 'composer' }, presentation })
    expect(ui.text).toBe('mercy ui: focus · sound on · notify on · auto pane off · toasts failures')
  })
})

describe('restyle', () => {
  test("the spinner names this turn's edits and commands; a task notification is one line", async ($, on) => {
    world(on)
    let suffix = ''
    on('ui.render', { component: 'Spinner' }, ($e, e) => {
      suffix = e.props.suffix
      const { Text } = $e.ui.resolve(e)
      return <Text>{e.props.word}</Text>
    })
    await $.tool.call({ tool: 'Write', file_path: '/r/src/a.ts', content: 'x' })
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Spinner', props: { word: 'Baking', message: null, suffix: '…', mode: 'tool-use' } })
    expect(suffix).toBe('… ✎1 ⚒1')
    const row = await $.ui.mount({
      plugin: 'mercy', surface: 'terminal', component: 'UserMessage',
      props: { text: 'Agent "docs sync" completed\n<details>', origin: { kind: 'task-notification' }, isExpanded: false, task: { status: 'completed', durationMs: 65_000 } },
    })
    expect(await row.find({ text: 'Agent "docs sync" completed · 1m05s' })).toBeDefined()
    expect((await row.find({ type: 'Text', text: '✓' }))?.props['color']).toBe('green')
  })
})
