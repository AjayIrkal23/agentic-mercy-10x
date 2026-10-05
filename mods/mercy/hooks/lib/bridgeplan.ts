// Pure planning for the Python bridge: which dispatch links the mod takes over, when each
// one still has to run, and how to talk to `dispatch.py --only`. Python stays the truth
// for every gate; the mod only decides WHEN a link runs (async, or only when it can fire).

import type { DispatchConfig } from './dispatch'
import { linkById, toolMatches } from './dispatch'
import { isDoc, join } from './paths'

export type BridgeEvent = 'pre-tool-use' | 'post-tool-use'
export type RunMode = 'async' | 'sync'

export type PlanFacts = {
  tool: string
  input: Record<string, unknown>
  jcodemunchUsed: boolean
  /** For writes: whether the file's git root already has a CLAUDE.md (undefined = unknown). */
  rootHasClaudeMd: boolean | undefined
}

/** `syncWhen`: calls where an async link runs in line instead (its advisory can still shape the call). */
type Policy = { id: string; event: BridgeEvent; mode: RunMode; when: (f: PlanFacts) => boolean; syncWhen?: (f: PlanFacts) => boolean }

const SHELL_WRITE = /(^|[^0-9&<>|])>{1,2}(?!&)\s*[^\s&|>]|\btee\b|<<-?\s*['"]?[A-Za-z_]/
const GIT_COMMIT = /\bgit\b[^|;&\n]*\bcommit\b/
const SEMGREP = /\bsemgrep\b/
const SKILL_MD = /[\\/]skills[\\/][^\\/]+[\\/]SKILL\.md$/

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

const always = (): boolean => true

/** Every link the bridge can own. Links absent or disabled in dispatch.config.json are skipped. */
const POLICIES: readonly Policy[] = [
  { id: 'tdd-guard-launcher-pre', event: 'pre-tool-use', mode: 'async', when: always },
  // the graph nudge is for an Explore agent about to start: in line for Agent/Task (as Python ran it), async for Bash (B1-22)
  { id: 'graphify-enforce', event: 'pre-tool-use', mode: 'async', when: always, syncWhen: f => f.tool === 'Agent' || f.tool === 'Task' },
  { id: 'bash-write-gate', event: 'pre-tool-use', mode: 'sync', when: f => SHELL_WRITE.test(str(f.input['command'])) },
  { id: 'blocking-doc-enforcer', event: 'pre-tool-use', mode: 'sync', when: f => GIT_COMMIT.test(str(f.input['command'])) },
  { id: 'jdoc-doc-steer', event: 'pre-tool-use', mode: 'sync', when: f => isDoc(str(f.input['file_path'] ?? f.input['path'])) },
  { id: 'jcm-gate-read', event: 'pre-tool-use', mode: 'sync', when: f => !f.jcodemunchUsed },
  { id: 'dox-write-gate-write', event: 'pre-tool-use', mode: 'sync', when: f => f.rootHasClaudeMd !== true },
  { id: 'fullstack-post', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'codex-capture', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'post-write-aggregator', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'desloppify-cleanup', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'mcp-post-hints', event: 'post-tool-use', mode: 'async', when: always },
  {
    id: 'security-semgrep-tracker', event: 'post-tool-use', mode: 'sync',
    when: f => f.tool.startsWith('mcp__semgrep__') || SEMGREP.test(str(f.input['command'])),
  },
  { id: 'skill-invocation-tracker', event: 'post-tool-use', mode: 'sync', when: f => f.tool === 'Skill' || SKILL_MD.test(str(f.input['file_path'])) },
]

export type OwnOptions = { tddGuard: 'async' | 'sync' | 'off'; bashWriteDenyArmed: boolean }

/** The link ids the mod claims this session: present, enabled, and safe to claim. */
export function ownedLinks(cfg: DispatchConfig, o: OwnOptions): string[] {
  return POLICIES.filter(p => {
    const link = linkById(cfg, p.event, p.id)
    if (!link || link.enabled === false) return false
    if (p.id === 'tdd-guard-launcher-pre' && o.tddGuard === 'sync') return false
    if (p.id === 'bash-write-gate' && o.bashWriteDenyArmed) return false
    return true
  }).map(p => p.id)
}

export type Plan = { sync: string[]; async: string[] }

/** Which owned links must run for this tool call, and how. */
export function planFor(cfg: DispatchConfig, owned: readonly string[], event: BridgeEvent, f: PlanFacts, tddGuard: 'async' | 'sync' | 'off'): Plan {
  const plan: Plan = { sync: [], async: [] }
  for (const p of POLICIES) {
    if (p.event !== event || !owned.includes(p.id)) continue
    if (p.id === 'tdd-guard-launcher-pre' && tddGuard === 'off') continue
    const link = linkById(cfg, event, p.id)
    if (!link || !toolMatches(link.tools, f.tool) || !p.when(f)) continue
    plan[p.syncWhen?.(f) ? 'sync' : p.mode].push(p.id)
  }
  return plan
}

/** The PreToolUse stdin a settings hook receives, rebuilt from the classic envelope. */
export function prePayload(env: Record<string, unknown>, base: { sessionId: string; transcriptPath: string; cwd: string }): string {
  const { tool, tool_use_id, ...input } = env
  return JSON.stringify({
    session_id: base.sessionId,
    transcript_path: base.transcriptPath,
    cwd: base.cwd,
    hook_event_name: 'PreToolUse',
    tool_name: tool,
    tool_input: input,
    tool_use_id,
  })
}

export type HookOutput = { decision?: 'deny' | 'ask'; reason?: string; context?: string }

/** Reads dispatch.py's merged JSON answer. */
export function parseHookOutput(stdout: string): HookOutput {
  const s = stdout.trim()
  if (!s.startsWith('{')) return {}
  try {
    const raw = JSON.parse(s) as Record<string, unknown>
    const hso = (raw['hookSpecificOutput'] ?? {}) as Record<string, unknown>
    const decision = (hso['permissionDecision'] ?? raw['permissionDecision']) as unknown
    const reason = (hso['permissionDecisionReason'] ?? raw['permissionDecisionReason']) as unknown
    const context = (hso['additionalContext'] ?? raw['additionalContext']) as unknown
    return {
      decision: decision === 'deny' || decision === 'ask' ? decision : undefined,
      reason: typeof reason === 'string' ? reason : undefined,
      context: typeof context === 'string' && context.trim() ? context.trim() : undefined,
    }
  } catch {
    return {}
  }
}

export function dispatchArgv(python: readonly string[], hooksDir: string, event: BridgeEvent, ids: readonly string[]): string[] {
  return [...python, join(hooksDir, 'dispatch.py'), event, '--only', ids.join(',')]
}
