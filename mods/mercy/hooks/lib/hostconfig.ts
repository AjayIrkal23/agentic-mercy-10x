// Pure readers of the workbench's own files at session start: the rendered settings
// (which interpreter runs dispatch.py), skills-index.json (skills hidden from the model)
// and where `hooks/` sits relative to the mod.

/** `~/.claude/mods/mercy` → `~/.claude/hooks`, keeping the platform's separator. */
export function hooksDirFrom(pluginRoot: string): string {
  const sep = pluginRoot.includes('\\') && !pluginRoot.includes('/') ? '\\' : '/'
  const parts = pluginRoot.replace(/[\\/]+$/, '').split(/[\\/]/)
  return [...parts.slice(0, -2), 'hooks'].join(sep)
}

/** The interpreter argv in front of `dispatch.py` in a rendered settings hook command. */
function interpreterFrom(command: string): string[] | undefined {
  const tokens = command.match(/"[^"]*"|'[^']*'|\S+/g) ?? []
  const at = tokens.findIndex(t => /dispatch\.py["']?$/.test(t))
  if (at <= 0) return undefined
  // an unquoted profile path with a space splits into tokens: the interpreter ends where a path starts
  const path = tokens.findIndex((t, i) => i > 0 && /^(?:[A-Za-z]:[\\/]|\/|~)/.test(t))
  return tokens.slice(0, path < 0 ? at : Math.min(at, path)).map(t => t.replace(/^["']|["']$/g, ''))
}

type HookGroups = Record<string, Array<{ hooks?: Array<{ command?: string }> }>>

/** The interpreter argv in front of `dispatch.py` in the rendered PreToolUse hooks. */
export function pythonFrom(settings: unknown): string[] | undefined {
  const hooks = (settings as { hooks?: HookGroups }).hooks ?? {}
  for (const group of hooks['PreToolUse'] ?? []) {
    for (const h of group.hooks ?? []) {
      const argv = h.command ? interpreterFrom(h.command) : undefined
      if (argv) return argv
    }
  }
  return undefined
}

/** Skill names flagged `hidden` in skills-index.json. */
export function hiddenFrom(text: string): Set<string> {
  const skills = (JSON.parse(text) as { skills?: Record<string, { hidden?: boolean }> }).skills ?? {}
  return new Set(Object.entries(skills).filter(([, v]) => v && v.hidden).map(([k]) => k))
}
