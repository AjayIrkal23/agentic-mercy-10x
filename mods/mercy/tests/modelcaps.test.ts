import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { capModel } from '../hooks/lib/modelcaps'

const POLICY = {
  model_order: ['haiku', 'sonnet', 'opus', 'fable'],
  roles: { agents: { 'santa-reviewer': 'judge', 'implementation-engineer': 'impl', explore: 'explore' }, labels: { review: 'judge', backend: 'impl' } },
  tiers: {
    pro: { ceiling: 'sonnet', roles: { judge: 'sonnet', impl: 'haiku', explore: 'haiku', default: 'haiku' }, usage_guard: { ceiling: 'haiku', judge: 'haiku' } },
    max5: { ceiling: 'opus', roles: { judge: 'sonnet', impl: 'sonnet', explore: 'haiku', default: 'sonnet' }, usage_guard: { ceiling: 'sonnet', judge: 'sonnet' } },
    max20: { ceiling: 'fable', roles: { judge: 'opus', impl: 'sonnet', explore: 'haiku', default: 'sonnet' }, usage_guard: { ceiling: 'sonnet', judge: 'sonnet' } },
  },
}

describe('capModel', () => {
  test('caps never raise and follow the tier ceiling', () => {
    expect(capModel({ model: 'opus', subagentType: 'santa-reviewer' }, 'pro', false, POLICY)).toEqual({ model: 'sonnet', reason: 'tier-cap' })
    expect(capModel({ model: 'haiku', subagentType: 'santa-reviewer' }, 'max20', false, POLICY)).toEqual({ model: 'haiku', reason: 'kept' })
    expect(capModel({ model: undefined, subagentType: 'santa-reviewer' }, 'pro', false, POLICY)).toEqual({ model: 'sonnet', reason: 'role-default' })
    expect(capModel({ model: undefined, subagentType: 'general-purpose' }, 'max20', false, POLICY)).toEqual({ model: undefined, reason: 'engine' })
    expect(capModel({ model: 'opus', subagentType: 'x', label: 'review phase' }, 'max5', false, POLICY)).toEqual({ model: 'opus', reason: 'kept' })
    expect(capModel({ model: 'opus', subagentType: 'implementation-engineer' }, 'max20', true, POLICY)).toEqual({ model: 'sonnet', reason: 'usage-guard' })
    expect(capModel({ model: 'opus', subagentType: 'santa-reviewer' }, 'max20', true, POLICY)).toEqual({ model: 'sonnet', reason: 'usage-guard' })
    expect(capModel({ model: 'claude-opus-4-1-20250805', subagentType: 'santa-reviewer' }, 'pro', false, POLICY).model).toBe('sonnet')
    expect(capModel({ model: 'opus', subagentType: 'santa-reviewer', fork: true }, 'pro', false, POLICY)).toEqual({ model: 'opus', reason: 'fork' })
    expect(capModel({ model: 'opus', subagentType: 'santa-reviewer' }, 'api', false, POLICY)).toEqual({ model: 'opus', reason: 'kept' }) // api → max5
  })
  test('an id it cannot classify is never touched', () => {
    expect(capModel({ model: 'my-local-model', subagentType: 'santa-reviewer' }, 'pro', false, POLICY)).toEqual({ model: 'my-local-model', reason: 'kept' })
  })
})

function engine(on: On, files: Record<string, string>) {
  mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('session.repo', () => ({ value: undefined }) as never)
  on('settings.read', () => ({ value: {} }))
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('fs.read', (_$, e) => {
    const hit = Object.entries(files).find(([suffix]) => e.path.replace(/\\/g, '/').endsWith(suffix))
    if (!hit) throw new Error('ENOENT')
    return { value: hit[1] }
  })
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('env.set', () => ({ value: undefined }) as never)
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
  on('ui.status', () => ({ value: undefined }))
  const spawned: Array<string | undefined> = []
  on('agent.spawn', (_$, e) => {
    spawned.push(e.model)
    return { model: e.model ?? 'inherit', agentId: 'a1' } as never
  })
  return { spawned }
}

const SPAWN = { prompt: 'review', description: 'review', subagentType: 'santa-reviewer' }

describe('model-caps feature', () => {
  test('a pro plan caps an opus judge spawn at sonnet; without a policy the spawn is untouched', async ($, on) => {
    const { spawned } = engine(on, { 'hooks/model-policy.json': JSON.stringify(POLICY), 'state/plan-tier.json': '{"schema":1,"tier":"pro"}' })
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.agent.spawn({ ...SPAWN, model: 'opus' } as never)
    expect(spawned).toEqual(['sonnet'])
  })
  test('no model-policy.json: nothing changes', async ($, on) => {
    const { spawned } = engine(on, { 'state/plan-tier.json': '{"schema":1,"tier":"pro"}' })
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.agent.spawn({ ...SPAWN, model: 'opus' } as never)
    expect(spawned).toEqual(['opus'])
  })
})
