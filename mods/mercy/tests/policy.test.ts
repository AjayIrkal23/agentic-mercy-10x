import { describe, expect, test } from 'claude-code/testing'

import { dispatchArgv, ownedLinks, parseHookOutput, planFor, prePayload } from '../hooks/lib/bridgeplan'
import { analyze } from '../hooks/lib/commands'
import { parseConfig } from '../hooks/lib/dispatch'
import { bashDeny, bestVerifyCommand, loopNudge, thrashNudge, verifyDecision } from '../hooks/lib/guard'
import { emptyLedger, recordCommand, recordEdit } from '../hooks/lib/ledger'

const deny = (cmd: string, agent?: string) => bashDeny(cmd, analyze(cmd), agent)

describe('guard', () => {
  test('servers, watchers and subagent commits are denied with a route', () => {
    expect(deny('npm run dev')).toContain('dev server')
    expect(deny('vite --port 5173')).toContain('CLAUDE.md §5')
    expect(deny('jest --watch')).toContain('watcher')
    expect(deny('git commit -m x', 'agent-1')).toContain('subagents never commit')
    expect(deny('git push origin main', 'agent-1')).toContain('subagents never commit')
    expect(deny('git commit -m x')).toBeUndefined()
    expect(deny('npm test')).toBeUndefined()
    expect(deny('npm run build && npx vitest run')).toBeUndefined()
  })
  test('loop and thrash nudges fire at their thresholds only', () => {
    const f = { n: 3, sig: 'E boom', lastAt: 1, command: 'pytest' }
    expect(loopNudge(f)).toContain('failed 3 times')
    expect(loopNudge({ ...f, n: 4 })).toBeUndefined()
    expect(thrashNudge('/r/a.ts', 8)).toContain('edited 8 times')
    expect(thrashNudge('/r/a.ts', 7)).toBeUndefined()
  })
  test('verify gate blocks once per turn, only with a known command', () => {
    const l = emptyLedger('s', 0)
    recordCommand(l, { key: 'pnpm test', command: 'pnpm test', kinds: ['test'], verify: ['test'], ok: true, at: 5, ms: 1, turn: 0, agent: '' })
    recordEdit(l, '/r/src/a.ts', 10, '')
    const facts = { mode: 'block' as const, stopHookActive: false, backgroundBusy: false, alreadyBlockedThisTurn: false, command: bestVerifyCommand(l, undefined) }
    expect(facts.command).toBe('pnpm test')
    expect(verifyDecision(l, facts)?.kind).toBe('block')
    expect(verifyDecision(l, { ...facts, stopHookActive: true })).toBeUndefined()
    expect(verifyDecision(l, { ...facts, alreadyBlockedThisTurn: true })).toBeUndefined()
    expect(verifyDecision(l, { ...facts, backgroundBusy: true })).toBeUndefined()
    expect(verifyDecision(l, { ...facts, command: undefined })?.kind).toBe('advise')
    l.turn = 1
    expect(verifyDecision(l, facts)).toBeUndefined()
  })
  test('bestVerifyCommand falls back to the brain, test first', () => {
    const l = emptyLedger('s', 0)
    const known = {
      a: { command: 'pnpm lint', kind: 'lint' as const, passes: 9, fails: 0, lastAt: 9, lastOk: true, ms: 1 },
      b: { command: 'pnpm tsc --noEmit', kind: 'typecheck' as const, passes: 3, fails: 0, lastAt: 8, lastOk: true, ms: 1 },
      c: { command: 'pnpm vitest run', kind: 'test' as const, passes: 2, fails: 1, lastAt: 7, lastOk: true, ms: 1 },
    }
    expect(bestVerifyCommand(l, known)).toBe('pnpm vitest run')
  })
})

const CFG = parseConfig(JSON.stringify({ chains: {
  'pre-tool-use': [
    { id: 'dangerous-bash-gate', type: 'gate', tools: 'Bash' },
    { id: 'bash-write-gate', type: 'gate', tools: 'Bash' },
    { id: 'blocking-doc-enforcer', type: 'gate', tools: 'Bash' },
    { id: 'jcm-gate-read', type: 'gate', tools: 'Read|Grep|Glob' },
    { id: 'jdoc-doc-steer', type: 'advisory', tools: 'Read|mcp__lean-ctx__ctx_read' },
    { id: 'dox-write-gate-write', type: 'gate', tools: 'Write|Edit|MultiEdit|NotebookEdit' },
    { id: 'tdd-guard-launcher-pre', type: 'advisory', tools: 'Write|Edit|MultiEdit' },
    { id: 'graphify-enforce', type: 'advisory', tools: 'Task|Agent|Bash' },
    { id: 'opus-guard', type: 'mutator', tools: 'Agent|Task' },
  ],
  'post-tool-use': [
    { id: 'skill-invocation-tracker', type: 'exec', tools: 'Skill|Read' },
    { id: 'fullstack-post', type: 'advisory', tools: 'Write|Edit|MultiEdit|NotebookEdit' },
    { id: 'post-write-aggregator', type: 'advisory', tools: 'Write|Edit|MultiEdit|NotebookEdit' },
    { id: 'codex-capture', type: 'advisory', tools: 'Write|Edit|MultiEdit', enabled: false },
    { id: 'security-semgrep-tracker', type: 'exec', tools: 'Bash|mcp__semgrep__.*' },
  ],
} }))

describe('bridge plan', () => {
  if (!CFG) throw new Error('config fixture did not parse')
  const owned = ownedLinks(CFG, { tddGuard: 'async', bashWriteDenyArmed: false })
  const facts = (tool: string, input: Record<string, unknown>, extra: Partial<{ jcodemunchUsed: boolean; rootHasClaudeMd: boolean }> = {}) =>
    ({ tool, input, jcodemunchUsed: false, rootHasClaudeMd: undefined, ...extra })
  test('owns only present, enabled, claimable links; never real deny gates', () => {
    expect(owned).not.toContain('dangerous-bash-gate')
    expect(owned).not.toContain('opus-guard')
    expect(owned).not.toContain('codex-capture')
    expect(owned).toContain('tdd-guard-launcher-pre')
    expect(ownedLinks(CFG, { tddGuard: 'sync', bashWriteDenyArmed: true })).not.toContain('tdd-guard-launcher-pre')
    expect(ownedLinks(CFG, { tddGuard: 'sync', bashWriteDenyArmed: true })).not.toContain('bash-write-gate')
  })
  test('Bash: predicates pick the rare sync links; graphify goes async', () => {
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Bash', { command: 'npm test' }), 'async')).toEqual({ sync: [], async: ['graphify-enforce'] })
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Bash', { command: 'git add -A && git commit -m x' }), 'async').sync).toEqual(['blocking-doc-enforcer'])
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Bash', { command: 'echo hi > notes.txt' }), 'async').sync).toEqual(['bash-write-gate'])
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Bash', { command: 'npm test 2>&1' }), 'async').sync).toEqual([])
  })
  test('writes: dox only when the root lacks CLAUDE.md; tdd async unless off', () => {
    const edit = (has: boolean | undefined) => planFor(CFG, owned, 'pre-tool-use', facts('Edit', { file_path: '/r/a.ts' }, { rootHasClaudeMd: has }), 'async')
    expect(edit(true)).toEqual({ sync: [], async: ['tdd-guard-launcher-pre'] })
    expect(edit(false).sync).toEqual(['dox-write-gate-write'])
    expect(edit(undefined).sync).toEqual(['dox-write-gate-write'])
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Edit', { file_path: '/r/a.ts' }, { rootHasClaudeMd: true }), 'off').async).toEqual([])
  })
  test('reads: jcm gate until jcodemunch is used; doc steer for docs only', () => {
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Read', { file_path: '/r/a.ts' }), 'async').sync).toEqual(['jcm-gate-read'])
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Read', { file_path: '/r/a.ts' }, { jcodemunchUsed: true }), 'async').sync).toEqual([])
    expect(planFor(CFG, owned, 'pre-tool-use', facts('Read', { file_path: '/r/README.md' }, { jcodemunchUsed: true }), 'async').sync).toEqual(['jdoc-doc-steer'])
  })
  test('post: write advisories async; trackers sync only when relevant', () => {
    expect(planFor(CFG, owned, 'post-tool-use', facts('Write', { file_path: '/r/a.ts' }), 'async')).toEqual({ sync: [], async: ['fullstack-post', 'post-write-aggregator'] })
    expect(planFor(CFG, owned, 'post-tool-use', facts('Bash', { command: 'semgrep scan --config auto' }), 'async').sync).toEqual(['security-semgrep-tracker'])
    expect(planFor(CFG, owned, 'post-tool-use', facts('Bash', { command: 'ls' }), 'async').sync).toEqual([])
    expect(planFor(CFG, owned, 'post-tool-use', facts('Read', { file_path: '/h/.claude/skills/caveman/SKILL.md' }), 'async').sync).toEqual(['skill-invocation-tracker'])
    expect(planFor(CFG, owned, 'post-tool-use', facts('Read', { file_path: '/r/a.ts' }), 'async').sync).toEqual([])
  })
  test('payload, output parsing and argv', () => {
    const p = JSON.parse(prePayload({ tool: 'Edit', tool_use_id: 't1', file_path: '/r/a.ts', old_string: 'a', new_string: 'b' }, { sessionId: 's', transcriptPath: '/t.jsonl', cwd: '/r' }))
    expect(p).toEqual({ session_id: 's', transcript_path: '/t.jsonl', cwd: '/r', hook_event_name: 'PreToolUse', tool_name: 'Edit', tool_input: { file_path: '/r/a.ts', old_string: 'a', new_string: 'b' }, tool_use_id: 't1' })
    expect(parseHookOutput('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"no"}}')).toEqual({ decision: 'deny', reason: 'no', context: undefined })
    expect(parseHookOutput('{"hookSpecificOutput":{"additionalContext":"  hint  "}}').context).toBe('hint')
    expect(parseHookOutput('garbage')).toEqual({})
    expect(dispatchArgv(['python3'], '/h/.claude/hooks', 'post-tool-use', ['a', 'b'])).toEqual(['python3', '/h/.claude/hooks/dispatch.py', 'post-tool-use', '--only', 'a,b'])
    expect(dispatchArgv(['py', '-3'], 'Z:\\w\\.claude\\hooks', 'pre-tool-use', ['x'])[2]).toBe('Z:\\w\\.claude\\hooks\\dispatch.py')
  })
})
