import { describe, expect, test } from 'claude-code/testing'

import { addNote, applyMarkers, brainSection, emptyFacts, learnCommands, learnFixes, storeKey } from '../hooks/lib/brain'
import { focusListing } from '../hooks/lib/focus'
import { govern, governAll } from '../hooks/lib/governor'
import { emptyLedger, recordCommand, recordEdit } from '../hooks/lib/ledger'
import { busy, done, enqueue, idle, size, take } from '../hooks/lib/queue'
import { nextWallClock, parseResetText, resumeAt } from '../hooks/lib/resume'
import { bandModel, paneRows, stateLine, statusText } from '../hooks/lib/views'

const ROUTER = [
  '<!-- prompt-router v3 -->',
  '[Critical directives]',
  'First substantive change this session: orient with codebase-intel-first + project-reference-linkage, then run dead-code-and-change-audit on your changes.',
  '',
  '[Skills for this task]',
  '- **tech-debt-audit** (MUST-READ) — Whole-repo tech debt and architecture audit producing TECH_DEBT_AUDIT.md with file-cited findings.',
  '  ACTION: Skill("tech-debt-audit") before the related work.',
  '- **debug-investigation** (SHOULD-READ) — Evidence-first debugging: reproduce, classify the failing surface, form hypotheses.',
  '  ACTION: Skill("debug-investigation") before the related work.',
  '',
  '[Suggested routing]',
  'Non-trivial reasoning → call mcp__sequential-thinking__sequentialthinking now (one thought per step) before deciding or answering.',
  '',
  '[Model]',
  'Heavy task (HEAVY_ARCHITECTURE, size L, risk 2): consider /model opus for this work.',
].join('\n')

const facts = (turn: number, extra: Partial<{ loaded: string[]; mcp: string[]; wrote: boolean; opus: boolean }> = {}) => ({
  turn, window: 6, loadedSkills: new Set(extra.loaded ?? []), mcpUsed: new Set(extra.mcp ?? []), wroteCode: extra.wrote ?? false, onOpus: extra.opus ?? false,
})

describe('governor', () => {
  test('first turn keeps everything, a repeat inside the window is dropped', () => {
    const first = govern(ROUTER, facts(1), { blocks: {}, skills: {} })
    expect(first.text).toContain('tech-debt-audit')
    expect(first.text.startsWith('<!-- prompt-router v3 -->')).toBe(true)
    const second = govern(ROUTER, facts(2), first.seen)
    expect(second.text).not.toContain('[Critical directives]')
    expect(second.text).not.toContain('debug-investigation')
    expect(govern(ROUTER, facts(8), first.seen).text).toContain('debug-investigation')
  })
  test("this turn's rank-1 MUST-READ is never dropped as a repeat: Python enforces it (C-15)", () => {
    const first = govern(ROUTER, facts(1), { blocks: {}, skills: {} })
    const second = govern(ROUTER, facts(2), first.seen)
    expect(second.text).toContain('- **tech-debt-audit** (MUST-READ)')
    expect(second.text).toContain('[Skills for this task]')
    // once loaded, the gate is satisfied, so the line may go
    expect(govern(ROUTER, facts(3, { loaded: ['tech-debt-audit'] }), second.seen).text).not.toContain('tech-debt-audit')
  })
  test('an inlined skill body stays in the skills section and goes as one item (C-15)', () => {
    const text = [
      '<!-- prompt-router v3 -->', '[Skills for this task]',
      '- **debug-investigation** (SHOULD-READ)', '  ACTION: Skill("debug-investigation")',
      '[inlined skill: tech-debt-audit]', '# Tech debt audit', '- **Rule** cite files', '[Not a header]', 'body end',
      '', '[Model]', 'Heavy task: consider /model opus for this work.',
    ].join('\n')
    const r = govern(text, facts(1), { blocks: {}, skills: {} })
    expect(r.text.split('\n').filter(l => l.startsWith('['))).toEqual(['[Skills for this task]', '[inlined skill: tech-debt-audit]', '[Not a header]', '[Model]'])
    const dropped = govern(text, facts(1, { loaded: ['tech-debt-audit'], opus: true }), { blocks: {}, skills: {} }).text
    expect(dropped).not.toContain('[Model]')
    expect(dropped).toContain('debug-investigation')
    expect(dropped).not.toContain('inlined skill')
    expect(dropped).not.toContain('cite files')
    expect(dropped).not.toContain('body end')
  })
  test('session knowledge drops loaded skills, used MCPs, first-write after a write, opus advice on opus', () => {
    const r = govern(ROUTER, facts(1, { loaded: ['tech-debt-audit'], mcp: ['sequential-thinking'], wrote: true, opus: true }), { blocks: {}, skills: {} })
    expect(r.text).not.toContain('tech-debt-audit')
    expect(r.text).toContain('debug-investigation')
    expect(r.text).not.toContain('First substantive change')
    expect(r.text).not.toContain('sequential-thinking')
    expect(r.text).not.toContain('/model opus')
    expect(r.text).not.toContain('[Model]')
  })
  test('a preamble line before the first skill item survives', () => {
    const text = '<!-- prompt-router v3 -->\n[Skills for this task]\nPick one:\n- **caveman** (SHOULD-READ) — terse prose for every reply the user reads in this session.'
    const r = govern(text, facts(1, { loaded: ['caveman'] }), { blocks: {}, skills: {} })
    expect(r.text).toContain('Pick one:')
    expect(r.text).not.toContain('caveman')
  })
  test('only router entries are governed; emptied entries disappear', () => {
    const soft = ROUTER.replace('MUST-READ', 'SHOULD-READ')
    const first = governAll(['other hook text', soft], facts(1), { blocks: {}, skills: {} })
    expect(first.entries).toHaveLength(2)
    const second = governAll(['other hook text', soft], facts(2), first.seen)
    expect(second.entries).toEqual(['other hook text'])
    expect(second.dropped).toBeGreaterThan(0)
  })
})

describe('focus', () => {
  const listing = [
    'The following skills are available for use with the Skill tool:',
    '',
    '- caveman: Ultra-compressed communication mode.',
    '- small-business:ad-manager: The ads consultant.',
    'second line of the ads description',
    '- sales:forecast: Generate the forecast.',
    '- engineering:code-review: Review code changes.',
    '- firecrawl:firecrawl-scrape: Extract clean markdown.',
  ].join('\n')
  test('hides listed families with their continuation lines and says so', () => {
    const r = focusListing(listing, ['small-business', 'sales'])
    expect(r.hidden).toBe(2)
    expect(r.text).toContain('- caveman:')
    expect(r.text).toContain('- engineering:code-review:')
    expect(r.text).toContain('- firecrawl:firecrawl-scrape:')
    expect(r.text).not.toContain('ad-manager')
    expect(r.text).not.toContain('second line of the ads')
    expect(r.text).toContain('mercy focus: 2 business-plugin skills')
  })
  test('nothing to hide leaves the text untouched', () => {
    expect(focusListing(listing, []).text).toBe(listing)
    expect(focusListing(listing, ['legal']).hidden).toBe(0)
  })
})

describe('resume', () => {
  const now = Date.UTC(2026, 9, 4, 19, 35)
  test('exhausted window reset wins, plus grace', () => {
    const at = resumeAt(now, 'rate_limit', [{ kind: 'five_hour', percentUsed: 100, resetsAt: '2026-10-04T23:40:00.000Z' }], undefined, 330)
    expect(at).toBe(Date.UTC(2026, 9, 4, 23, 40) + 90_000)
  })
  test('falls back to the message text in its own zone', () => {
    expect(parseResetText("You've hit your session limit · resets 5:10am (Asia/Kolkata)", now, 330)).toBe(Date.UTC(2026, 9, 4, 23, 40))
    expect(parseResetText('resets 5:10am', now, 330)).toBe(Date.UTC(2026, 9, 4, 23, 40))
    expect(parseResetText('no time here', now, 330)).toBeUndefined()
  })
  test('transient errors retry soon; other errors never', () => {
    expect(resumeAt(now, 'overloaded', [], undefined, 0)).toBe(now + 180_000)
    expect(resumeAt(now, 'invalid_request', [], undefined, 0)).toBeUndefined()
    expect(resumeAt(now, 'rate_limit', [], 'gibberish', 0)).toBe(now + 1_800_000)
  })
  test('wall clock rolls to tomorrow when the time passed', () => {
    expect(nextWallClock(Date.UTC(2026, 9, 5, 0, 0), 5, 10, 330)).toBe(Date.UTC(2026, 9, 5, 23, 40))
  })
})

describe('brain', () => {
  test('learns verify commands, fixes and notes; renders one section', () => {
    const f = emptyFacts('/r/app', 0)
    const l = emptyLedger('s', 0)
    recordCommand(l, { key: 'pnpm test', command: 'pnpm test', kinds: ['test'], verify: ['test'], ok: false, at: 10, ms: 900, turn: 1, agent: '', error: 'FAIL src/a.test.ts' })
    recordEdit(l, '/r/app/src/a.ts', 20, '')
    recordCommand(l, { key: 'pnpm test', command: 'pnpm test', kinds: ['test'], verify: ['test'], ok: true, at: 30, ms: 1200, turn: 1, agent: '' })
    recordCommand(l, { key: 'ls', command: 'ls', kinds: ['other'], verify: [], ok: true, at: 31, ms: 5, turn: 1, agent: '' })
    learnCommands(f, l.commands, 0)
    learnFixes(f, l)
    expect(Object.keys(f.commands)).toEqual(['pnpm test'])
    expect(f.commands['pnpm test']?.passes).toBe(1)
    expect(f.fixes[0]?.files).toEqual(['src/a.ts'])
    expect(addNote(f, 'API base URL comes from VITE_API_URL', 40)).toBe(true)
    expect(addNote(f, 'API base URL comes from VITE_API_URL', 41)).toBe(false)
    applyMarkers(f, ['pnpm-lock.yaml', 'vite.config.ts'])
    const s = brainSection(f) ?? ''
    expect(s).toContain('`pnpm test`')
    expect(s).toContain('pnpm, vite')
    expect(s).toContain('VITE_API_URL')
    expect(brainSection(emptyFacts('/r/x', 0))).toBeUndefined()
    expect(storeKey('Z:\\Work\\Proj')).toBe('repo:z:/work/proj')
  })
})

describe('queue and views', () => {
  test('lanes run in order, slow lane coalesces per key, idle resolves', async () => {
    const job = (lane: 'fast' | 'slow', key: string) => ({ lane, event: 'post-tool-use' as const, ids: ['x'], payload: key, key, queuedAt: 0 })
    enqueue(job('slow', '/a.ts'))
    enqueue(job('slow', '/a.ts'))
    enqueue(job('slow', '/b.ts'))
    expect(size()).toBe(2)
    const waiting = idle('slow')
    expect(take('slow')?.key).toBe('/a.ts')
    expect(take('slow')).toBeUndefined()
    done('slow')
    expect(take('slow')?.key).toBe('/b.ts')
    done('slow')
    await waiting
    expect(busy('slow')).toBe(false)
  })
  test('status, band and state line reflect unverified edits', () => {
    const l = emptyLedger('s', 0)
    recordEdit(l, '/r/src/a.ts', 10, '')
    const snap = { now: 60_000, ledger: l, bridge: { owned: [], queued: 0, ran: 0, failed: 0, savedMs: 0, delivered: 0 }, brain: null, contextPct: 23, costUsd: 1.2, pending: 0, queued: 0, verifyCommand: 'pnpm test' }
    expect(statusText(snap)).toContain('✎ 1 (1 unverified)')
    expect(bandModel(snap)?.actions[0]?.prompt).toContain('pnpm test')
    expect(stateLine(snap)).toContain('1 edited code file(s) not verified')
    expect(bandModel({ ...snap, ledger: emptyLedger('s', 0) })).toBeUndefined()
    expect(paneRows('files', snap, 80)[0]).toContain('a.ts')
  })
})
