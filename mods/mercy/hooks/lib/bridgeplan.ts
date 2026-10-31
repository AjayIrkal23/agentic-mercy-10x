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
  /** For writes: whether the file's git root already has a CLAUDE.md (undefined = unknown). */
  rootHasClaudeMd: boolean | undefined
}

/** `syncWhen`: calls where an async link runs in line instead (its advisory can still shape the call). */
type Policy = { id: string; event: BridgeEvent; mode: RunMode; when: (f: PlanFacts) => boolean; syncWhen?: (f: PlanFacts) => boolean }

const SHELL_WRITE = /(^|[^0-9&<>|])>{1,2}(?!&)\s*[^\s&|>]|\btee\b|<<-?\s*['"]?[A-Za-z_]/
// PowerShell writers `bash-write-gate.py` detects (`_PS_WRITERS`, `_PS_DOTNET_RE`): the write cmdlets, `sc`/`ac` in command
// position, `[IO.File]::Write*/Append*`. A superset is fine (a false hit costs one `--only` run); a miss skips the gate.
const PS_WRITE = /\b(?:set-content|add-content|out-file)\b|(?:^|[;&|(\n"']\s*)(?:sc|ac)\s+\S|\[(?:system\.)?io\.file\]::(?:write|append)/i
// Layer-1 kinds bash-write-gate.py classifies (`_INPLACE_RE`, `_INTERP_INLINE_RE`, `_INTERP_STDIN_RE`): command-position
// anchored like its `_CMD_POS`, so `git commit -m "... sed -i ..."` is a mention, not a write. Python keeps the exact
// classification, the /tmp silence and the once-per-kind dedupe; these four regexes only decide that the link runs (R2-F1).
const CMD_POS = String.raw`(?:^|[\n;&|(]|\$\()\s*`
const INTERP = String.raw`(?:python3?(?:\.\d+)?|node|nodejs|ruby|perl|php|deno|bun)`
const IN_PLACE = new RegExp(CMD_POS + String.raw`(?:sed|perl|ruby)\s+(?:-[A-Za-z]*i\b|--in-place)`, 'm')
const INTERP_WRITE = new RegExp(CMD_POS + INTERP + String.raw`\b[^\n;|&]*?\s-(?:c|e)\b|` + CMD_POS + INTERP + String.raw`\b[^\n;|&]*?\s-\s*<<`, 'm')
const bashWrite = (c: string): boolean => SHELL_WRITE.test(c) || PS_WRITE.test(c) || IN_PLACE.test(c) || INTERP_WRITE.test(c)
const GIT_COMMIT = /\bgit\b[^|;&\n]*\bcommit\b/
const SEMGREP = /\bsemgrep\b/
// B-02: shell reads/searches the jcodemunch gate judges (`lib/shell_reads.py` decides the target; this only decides it runs).
const SHELL_READ = new RegExp(CMD_POS + String.raw`(?:sudo\s+)?(?:grep|egrep|fgrep|rg|ag|ack|cat|bat|head|tail|less|more|nl|find|fd|sed\s+-n)\b`, 'm')
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
  { id: 'bash-write-gate', event: 'pre-tool-use', mode: 'sync', when: f => bashWrite(str(f.input['command'])) },
  { id: 'blocking-doc-enforcer', event: 'pre-tool-use', mode: 'sync', when: f => GIT_COMMIT.test(str(f.input['command'])) },
  { id: 'jdoc-doc-steer', event: 'pre-tool-use', mode: 'sync', when: f => isDoc(str(f.input['file_path'] ?? f.input['path'])) },
  // B-03/B-04: Python keys the gate per agent and per user turn, so the session ledger cannot predict it: always run
  { id: 'jcm-gate-read', event: 'pre-tool-use', mode: 'sync', when: always },
  { id: 'jcm-gate-shell', event: 'pre-tool-use', mode: 'sync', when: f => SHELL_READ.test(str(f.input['command'])) },
  { id: 'dox-write-gate-write', event: 'pre-tool-use', mode: 'sync', when: f => f.rootHasClaudeMd !== true },
  { id: 'fullstack-post', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'codex-capture', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'post-write-aggregator', event: 'post-tool-use', mode: 'async', when: always },
  { id: 'desloppify-cleanup', event: 'post-tool-use', mode: 'async', when: always },
  // B-10: in line, so a "call context7 / semgrep now" hint lands before the next call (3 s link, state I/O only)
  { id: 'mcp-post-hints', event: 'post-tool-use', mode: 'sync', when: always },
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
export function prePayload(env: Record<string, unknown>, base: { sessionId: string; transcriptPath: string; cwd: string; agentId?: string }): string {
  const { tool, tool_use_id, ...input } = env
  return JSON.stringify({
    session_id: base.sessionId,
    transcript_path: base.transcriptPath,
    cwd: base.cwd,
    hook_event_name: 'PreToolUse',
    tool_name: tool,
    tool_input: input,
    tool_use_id,
    // a subagent's call: Python keys its gate state per agent (B-03)
    ...(base.agentId ? { agent_id: base.agentId } : {}),
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
