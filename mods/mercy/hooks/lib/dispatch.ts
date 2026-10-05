// Pure reading of hooks/dispatch.config.json, the Python hook chain map. The bridge uses
// it to know which links would run for a tool call, so it only claims links it can run
// itself and never guesses at the chain's shape.

export type LinkType = 'gate' | 'mutator' | 'advisory' | 'exec'

export type Link = {
  id: string
  type: LinkType
  tools?: string
  enabled?: boolean
  async?: boolean
  priority?: number
  timeout_ms?: number
}

export type DispatchConfig = { chains: Record<string, Link[]> }

export function parseConfig(text: string): DispatchConfig | undefined {
  try {
    const raw = JSON.parse(text) as { chains?: Record<string, unknown> }
    if (!raw || typeof raw !== 'object' || !raw.chains || typeof raw.chains !== 'object') return undefined
    const chains: Record<string, Link[]> = {}
    for (const [event, list] of Object.entries(raw.chains)) {
      if (!Array.isArray(list)) continue
      chains[event] = list.filter((l): l is Link => !!l && typeof l === 'object' && typeof (l as Link).id === 'string')
    }
    return { chains }
  } catch {
    return undefined
  }
}

const CACHE = new Map<string, RegExp | null>()

/** Python's `re.fullmatch(f"(?:{pat})", tool)`; a bad pattern matches (never drops a trigger). */
export function toolMatches(pattern: string | undefined, tool: string): boolean {
  if (!pattern) return true
  let re = CACHE.get(pattern)
  if (re === undefined) {
    try {
      // patterns come from the repo's own hooks/dispatch.config.json, never from tool input
      re = new RegExp(`^(?:${pattern})$`) // nosemgrep
    } catch {
      re = null
    }
    CACHE.set(pattern, re)
  }
  return re === null ? true : re.test(tool)
}

export function linkById(cfg: DispatchConfig, event: string, id: string): Link | undefined {
  return (cfg.chains[event] ?? []).find(l => l.id === id)
}
