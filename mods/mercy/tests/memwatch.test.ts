import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { memBand, memRows } from '../hooks/lib/deckviews'
import { parseMemPressure } from '../hooks/lib/probes'

const NOW = 1_761_740_000_000
const WARN = JSON.stringify({
  schema: 1, ts: 1_761_739_990, level: 'warn', mem_available_mb: 6100, swap_free_pct: 1.2, psi_some_avg10: 12.5,
  top: [{ name: 'tsserver', rss_mb: 3800, unit: 'ptyxis-spawn-1.scope' }], stuck: [{ sid: 's', since: 1 }], shed: [], notify_owner: 'mod',
})
const PANE = { title: 'mercy pulse', isFocused: true, bodyColumns: 90, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }
const BAND = { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 100, scroll: { offset: 0, bodyRows: 12 }, view: {} }

describe('parseMemPressure', () => {
  test('reads the contract and tolerates missing keys', () => {
    const m = parseMemPressure(WARN, NOW)
    expect(m).toMatchObject({ level: 'warn', rawLevel: 'warn', stale: false, memAvailableMb: 6100, swapFreePct: 1.2, psi: 12.5, stuck: 1, notifyOwner: 'mod' })
    expect(m?.top[0]).toEqual({ name: 'tsserver', rssMb: 3800, unit: 'ptyxis-spawn-1.scope' })
    expect(parseMemPressure('{"level":"crit"}', NOW)?.level).toBe('ok') // no ts → stale → ok
    expect(parseMemPressure('{"level":"crit"}', NOW)?.rawLevel).toBe('crit')
  })
  test('a file older than 30 s reads as ok but keeps rawLevel; garbage is undefined', () => {
    const m = parseMemPressure(JSON.stringify({ ts: NOW / 1000 - 90, level: 'crit' }), NOW)
    expect(m).toMatchObject({ level: 'ok', rawLevel: 'crit', stale: true })
    expect(parseMemPressure('{nope', NOW)).toBeUndefined()
    expect(parseMemPressure('[]', NOW)).toBeUndefined()
    expect(parseMemPressure(JSON.stringify({ ts: NOW / 1000, level: 'bogus' }), NOW)?.level).toBe('ok')
  })
})

describe('memory rows and band', () => {
  test('band only at warn and above; rows name the numbers and the top hogs', () => {
    const m = parseMemPressure(WARN, NOW)
    if (!m) throw new Error('parse failed')
    expect(memBand(m)?.line).toContain('6.1 GB free')
    expect(memBand(m)?.command).toBe('open-mem')
    expect(memBand({ ...m, level: 'ok' })).toBeUndefined()
    expect(memBand({ ...m, level: 'crit' })?.line.startsWith('✗ memory CRIT')).toBe(true)
    const rows = memRows(m, NOW, 80).map(r => r.text)
    expect(rows[0]).toMatch(/memory WARN/)
    expect(rows.some(r => r.includes('tsserver') && r.includes('3.8 GB'))).toBe(true)
    expect(memRows(undefined, NOW, 80)[0]?.text).toContain('no memwatch state')
    expect(memRows({ ...m, unsupported: true }, NOW, 80)[0]?.text).toContain('not supported')
  })
})

function engine(on: On, file: () => string | undefined, windows = false) {
  const clock = mock.clock(on, { now: NOW })
  mock.store(on)
  mock.env(on, windows ? { OS: 'Windows_NT' } : {})
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('session.repo', () => ({ value: undefined }) as never)
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 200_000 }, rateLimits: [] } }))
  on('settings.read', () => ({ value: {} }))
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  const reads: string[] = []
  on('fs.read', (_$, e) => {
    reads.push(e.path)
    const t = e.path.endsWith('mem-pressure.json') ? file() : e.path.endsWith('dispatch.config.json') ? '{"chains":{}}' : undefined
    if (t === undefined) throw new Error('ENOENT')
    return { value: t }
  })
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
  on('env.set', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  const toasts: string[] = []
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const processRuns: string[][] = []
  on('process.run', (_$, e) => {
    processRuns.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { clock, toasts, reads, processRuns }
}

describe('memwatch feature', () => {
  test('polls every 15 s, toasts once per tier change, band shows at warn, pane tab m lists hogs', async ($, on) => {
    let text: string | undefined
    const { clock, toasts } = engine(on, () => text)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await clock.advance(15_000)
    expect(toasts.filter(t => t.includes('memory'))).toEqual([]) // missing file: silent
    text = WARN.replace('1761739990', String(Math.floor((NOW + 15_000) / 1000)))
    await clock.advance(15_000)
    expect(toasts.filter(t => t.includes('memory warn'))).toHaveLength(1)
    text = WARN.replace('1761739990', String(Math.floor((NOW + 30_000) / 1000)))
    await clock.advance(15_000)
    expect(toasts.filter(t => t.includes('memory warn'))).toHaveLength(1) // same tier: no repeat
    const band = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect(await band.find({ text: /6\.1 GB free/ })).toBeDefined()
    const pane = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'Pane', requestId: 'mercy', props: PANE })
    await pane.press({ key: 'tab-memory' })
    expect(await pane.find({ text: /tsserver/ })).toBeDefined()
    text = JSON.stringify({ ts: Math.floor((NOW + 60_000) / 1000), level: 'ok' })
    await clock.advance(15_000)
    expect(toasts.some(t => t.includes('memory ok'))).toBe(true)
  })
  test('crit toasts in-pane only: the desktop notification is memwatch.py\'s', async ($, on) => {
    let text: string | undefined = WARN.replace('1761739990', String(Math.floor(NOW / 1000)))
    const { clock, toasts, processRuns } = engine(on, () => text)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    text = JSON.stringify({ ts: Math.floor((NOW + 15_000) / 1000), level: 'crit', mem_available_mb: 900 })
    await clock.advance(15_000)
    expect(toasts.some(t => t.includes('memory crit'))).toBe(true)
    expect(processRuns.filter(argv => argv[0] === 'notify-send')).toHaveLength(0)
  })
  test('does nothing on Windows', async ($, on) => {
    const { clock, reads } = engine(on, () => WARN, true)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await clock.advance(30_000)
    expect(reads.filter(p => p.endsWith('mem-pressure.json'))).toEqual([])
  })
  test('a corrupt file keeps the previous state and never toasts', async ($, on) => {
    let text: string | undefined = WARN.replace('1761739990', String(Math.floor(NOW / 1000)))
    const { clock, toasts } = engine(on, () => text)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    text = '{bad'
    await clock.advance(15_000)
    expect(toasts.filter(t => t.includes('memory'))).toEqual([])
    const band = await $.ui.mount({ plugin: 'mercy', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect(await band.find({ text: /memory WARN/ })).toBeDefined()
  })
})
