import { describe, expect, test } from 'claude-code/testing'

import { blocks, dedupe, hash, prune } from '../hooks/lib/dedupe'
import { linkById, parseConfig, toolMatches } from '../hooks/lib/dispatch'
import { compact, duration, meter } from '../hooks/lib/format'
import { beginTurn, emptyLedger, lastEvidenceAt, loops, mcpServer, recordCommand, recordEdit, unverified, verifiedSince } from '../hooks/lib/ledger'
import { isCode, isTest, shortPath } from '../hooks/lib/paths'
import { rt, takePending } from '../hooks/lib/runtime'
import { findSecret, isSecretHome, writtenText } from '../hooks/lib/secrets'

describe('dedupe', () => {
  const ctx = '[Critical directives]\n' + 'Orient with codebase-intel-first before the first change. '.repeat(4) + '\n\n[Model]\nshort line'
  test('blocks split on headers and blank lines', () => {
    expect(blocks(ctx)).toHaveLength(2)
  })
  test('drops a long block resent inside the window, keeps short ones', () => {
    const first = dedupe(ctx, {}, 1)
    expect(first.dropped).toBe(0)
    const second = dedupe(ctx, first.seen, 2)
    expect(second.dropped).toBe(1)
    expect(second.text).toBe('[Model]\nshort line')
  })
  test('resends once the window passed', () => {
    const first = dedupe(ctx, {}, 1)
    expect(dedupe(ctx, first.seen, 7).dropped).toBe(0)
  })
  test('hash folds whitespace; prune forgets old blocks', () => {
    expect(hash('a  b\n c')).toBe(hash('a b c'))
    expect(Object.keys(prune({ x: 1, y: 50 }, 60))).toEqual(['y'])
  })
})

describe('dispatch config', () => {
  const cfg = parseConfig(JSON.stringify({ chains: { 'pre-tool-use': [
    { id: 'danger', type: 'gate', tools: 'Bash' },
    { id: 'writes', type: 'gate', tools: 'Write|Edit|MultiEdit' },
    { id: 'off', type: 'gate', tools: 'Bash', enabled: false },
    { id: 'any', type: 'advisory' },
  ] } }))
  test('parses and matches like re.fullmatch', () => {
    expect(cfg).toBeDefined()
    if (!cfg) return
    expect(linkById(cfg, 'pre-tool-use', 'off')?.enabled).toBe(false)
    expect(linkById(cfg, 'pre-tool-use', 'nope')).toBeUndefined()
    expect(toolMatches('Write|Edit|MultiEdit', 'Edit')).toBe(true)
    expect(toolMatches(undefined, 'Anything')).toBe(true)
    expect(toolMatches('Bash', 'BashX')).toBe(false)
    expect(toolMatches('mcp__jcodemunch__.*', 'mcp__jcodemunch__search_symbols')).toBe(true)
    expect(toolMatches('(', 'Bash')).toBe(true)
  })
  test('bad json is undefined', () => {
    expect(parseConfig('{nope')).toBeUndefined()
  })
})

describe('ledger', () => {
  test('edits after the last passing test are unverified', () => {
    const l = emptyLedger('s', 0)
    beginTurn(l, 1)
    recordEdit(l, '/r/src/a.ts', 10, '')
    recordEdit(l, '/r/README.md', 11, '')
    expect(unverified(l).map(f => f.path)).toEqual(['/r/src/a.ts'])
    recordCommand(l, { key: 'npm test', command: 'npm test', kinds: ['test'], verify: ['test'], ok: true, at: 20, ms: 900, turn: 1, agent: '' })
    expect(lastEvidenceAt(l)).toBe(20)
    expect(unverified(l)).toHaveLength(0)
    expect(verifiedSince(l, '/r/src/a.ts')).toBe(true)
    expect(verifiedSince(l, '/r/src/never-edited.ts')).toBe(false)
    expect(verifiedSince(l, undefined)).toBe(false)
    recordEdit(l, '/r/src/a.ts', 30, 'agent-1')
    expect(unverified(l)).toHaveLength(1)
    expect(verifiedSince(l, '/r/src/a.ts')).toBe(false)
    expect(l.files['/r/src/a.ts']?.agents).toEqual(['', 'agent-1'])
  })
  test('a tdd-guard advisory is dropped once its file passed a test after the edit', () => {
    const tdd = 'TDD GUARD: write the failing test first'
    rt.ledger = emptyLedger('s', 0)
    recordEdit(rt.ledger, '/r/src/a.ts', 10, '')
    rt.pending = [tdd, 'docs: update the README']
    rt.pendingFiles = new Map([[tdd, '/r/src/a.ts']])
    expect(takePending()).toEqual([tdd, 'docs: update the README'])
    recordCommand(rt.ledger, { key: 'npm test', command: 'npm test', kinds: ['test'], verify: ['test'], ok: true, at: 20, ms: 900, turn: 1, agent: '' })
    rt.pending = [tdd]
    rt.pendingFiles.set(tdd, '/r/src/a.ts')
    expect(takePending()).toEqual([])
  })
  test('identical failures count up; a pass clears them', () => {
    const l = emptyLedger('s', 0)
    const run = { key: 'pytest', command: 'pytest', kinds: ['test' as const], verify: ['test' as const], ok: false, at: 1, ms: 5, turn: 1, agent: '', error: 'E boom' }
    recordCommand(l, run)
    recordCommand(l, { ...run, at: 2 })
    const third = recordCommand(l, { ...run, at: 3 })
    expect(third?.n).toBe(3)
    expect(loops(l)).toHaveLength(1)
    recordCommand(l, { ...run, ok: true, at: 4 })
    expect(loops(l)).toHaveLength(0)
  })
  test('mcp server names', () => {
    expect(mcpServer('mcp__claude_ai_Gmail__create_draft')).toBe('claude_ai_Gmail')
    expect(mcpServer('Read')).toBeUndefined()
  })
})

describe('paths, secrets, format', () => {
  test('classification', () => {
    expect(isCode('/r/src/a.tsx')).toBe(true)
    expect(isCode('/r/node_modules/x/a.js')).toBe(false)
    expect(isTest('/r/src/a.test.ts')).toBe(true)
    expect(isTest('/r/pkg/a_test.go')).toBe(true)
    expect(shortPath('/a/b/c/d.ts')).toBe('…/c/d.ts')
  })
  test('secrets', () => {
    // fixtures are split so this tracked file holds no literal key (the guard would deny rewriting it)
    expect(findSecret(`const k = "${'AKIA' + 'ABCDEFGHIJKLMNOP'}"`)?.kind).toBe('AWS access key')
    expect(findSecret('const k = "AKIAIOSFODNN7EXAMPLE"')).toBeUndefined()
    expect(findSecret('-----BEGIN OPENSSH ' + 'PRIVATE KEY-----')?.kind).toBe('private key')
    expect(findSecret('const ok = "sk-short"')).toBeUndefined()
    expect(isSecretHome('/r/.env.local')).toBe(true)
    expect(isSecretHome('/r/.env.production')).toBe(true)
    expect(isSecretHome('/r/src/env.ts')).toBe(false)
    // committed templates are not where secrets live (audit H-05)
    for (const t of ['/r/.env.example', '/r/server/.env.sample', '/r/.env.template', '/r/.env.dist', '/r/.env.defaults']) {
      expect(isSecretHome(t), t).toBe(false)
    }
    expect(writtenText({ edits: [{ new_string: 'a' }, { new_string: 'b' }] })).toBe('a\nb')
  })
  test('format', () => {
    expect(duration(950)).toBe('950ms')
    expect(duration(3400)).toBe('3.4s')
    expect(duration(125_000)).toBe('2m05s')
    expect(compact(12_345)).toBe('12k')
    expect(meter(50, 4)).toBe('▰▰▱▱')
  })
})
