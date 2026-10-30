// Pure subagent model cap (MERGE-PLAN R3.3 enforcement point 3): the same ceiling and
// usage-guard step-down hooks/opus-guard.py applies, read from hooks/model-policy.json,
// state/plan-tier.json and state/usage-guard.json. It never raises a model: the phrase
// logic ("use opus") stays Python's; this only guarantees the ceiling at spawn time.

export type TierRow = {
  ceiling: string
  roles?: Record<string, string>
  usage_guard?: { ceiling?: string; judge?: string }
}
export type Policy = {
  model_order?: string[]
  roles?: { agents?: Record<string, string>; labels?: Record<string, string> }
  tiers?: Record<string, TierRow>
}
export type CapInput = { model?: string; subagentType?: string; label?: string; fork?: boolean }
export type CapReason = 'fork' | 'engine' | 'kept' | 'role-default' | 'tier-cap' | 'usage-guard'
export type CapResult = { model: string | undefined; reason: CapReason }

const FAMILIES = ['fable', 'opus', 'sonnet', 'haiku'] as const
const DEFAULT_ORDER = ['haiku', 'sonnet', 'opus', 'fable']

/** The model family a name or full id belongs to; undefined for an unknown id (never touched). */
export function family(model: string | undefined): string | undefined {
  const m = (model ?? '').toLowerCase()
  return FAMILIES.find(f => m.includes(f))
}

/** A Workflow label's role: the first `roles.labels` key the label contains. */
function labelRole(label: string | undefined, labels: Record<string, string> | undefined): string | undefined {
  if (!label || !labels) return undefined
  const low = label.toLowerCase()
  for (const [k, role] of Object.entries(labels)) if (low.includes(k.toLowerCase())) return role
  return undefined
}

export function capModel(input: CapInput, tier: string, usageActive: boolean, policy: Policy): CapResult {
  if (input.fork) return { model: input.model, reason: 'fork' }
  const tiers = policy.tiers ?? {}
  const tb = tiers[tier === 'api' ? 'max5' : tier] ?? tiers['max5']
  if (!tb) return { model: input.model, reason: 'kept' }
  const role = policy.roles?.agents?.[(input.subagentType ?? '').toLowerCase()] ?? labelRole(input.label, policy.roles?.labels) ?? 'default'
  const order = policy.model_order?.length ? policy.model_order : DEFAULT_ORDER
  const ceiling = usageActive ? (role === 'judge' ? tb.usage_guard?.judge : tb.usage_guard?.ceiling) ?? tb.ceiling : tb.ceiling
  let base: string | undefined
  if (input.model) {
    base = family(input.model)
    if (base === undefined) return { model: input.model, reason: 'kept' } // an id we cannot classify
  } else if (role === 'default' && tier === 'max20') {
    base = undefined // unknown role on the top tier: the agent's own model, then the parent's
  } else {
    base = tb.roles?.[role] ?? tb.roles?.['default']
  }
  if (base === undefined) return { model: undefined, reason: 'engine' }
  const capped = order.indexOf(base) > order.indexOf(ceiling) && order.indexOf(ceiling) >= 0 ? ceiling : base
  if (capped !== base) return { model: capped, reason: usageActive ? 'usage-guard' : 'tier-cap' }
  return input.model ? { model: input.model, reason: 'kept' } : { model: capped, reason: 'role-default' }
}
