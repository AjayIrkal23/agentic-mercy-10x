// agent.spawn model cap (MERGE-PLAN R3.3 enforcement point 3): every subagent spawn, the
// bridge's and workflow agents' included, gets the plan tier's ceiling and the usage-guard
// step-down from hooks/model-policy.json + state/plan-tier.json + state/usage-guard.json
// (read at most once a minute). UI-side parity only: hooks/opus-guard.py stays the floor.
// No policy file → the spawn passes untouched. An engine without `agent.spawn` makes `on`
// throw: register.ts marks the feature `error` and every other feature still loads.

import type { EngineInterface, On } from 'claude-code'

import type { Policy } from '../lib/modelcaps'
import { capModel } from '../lib/modelcaps'
import { join, statePathFrom } from '../lib/paths'
import { noteError, rt } from '../lib/runtime'

type Inputs = { at: number; tier: string; usage: boolean; policy: Policy | undefined }
const TTL_MS = 60_000

let cache: Inputs | undefined

async function readJson($: EngineInterface, path: string): Promise<Record<string, unknown> | undefined> {
  try {
    const d: unknown = JSON.parse(await $.fs.read(path))
    return typeof d === 'object' && d !== null && !Array.isArray(d) ? (d as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

async function inputs($: EngineInterface): Promise<Inputs> {
  const now = await $.clock.now()
  if (cache && now - cache.at < TTL_MS) return cache
  const tier = (await readJson($, statePathFrom(rt.hooksDir, 'plan-tier.json')))?.['tier']
  const usage = (await readJson($, statePathFrom(rt.hooksDir, 'usage-guard.json')))?.['active'] === true
  const policy = (await readJson($, join(rt.hooksDir, 'model-policy.json'))) as Policy | undefined
  cache = { at: now, tier: typeof tier === 'string' ? tier : 'max20', usage, policy }
  return cache
}

export function registerModelCaps(on: On): void {
  on('agent.spawn', async ($, e, next) => {
    try {
      if (rt.hooksDir) {
        const { tier, usage, policy } = await inputs($)
        if (policy?.tiers) {
          const label = (e as { label?: unknown }).label
          const r = capModel({ model: e.model, subagentType: e.subagentType, label: typeof label === 'string' ? label : undefined, fork: e.fork }, tier, usage, policy)
          if (r.model !== e.model) {
            rt.modelCaps.applied += 1
            rt.modelCaps.last = `${e.subagentType}: ${e.model ?? 'inherit'} → ${r.model} (${r.reason}, ${tier}${usage ? ', usage-guard' : ''})`
            return next({ ...e, model: r.model })
          }
        }
      }
    } catch (err) {
      noteError('model-caps', err)
    }
    return next(e)
  })
}
