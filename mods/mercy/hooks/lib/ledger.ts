// Pure session ledger: what happened this session, built from tool calls and turns.
// Features read it to decide (guard, bridge), to remember (brain) and to show (pulse).

import type { AgentRun, Block, CommandRun, Failure, FileTouch, Ledger, VerifyKind } from '../../types'
import { isCode, isGenerated, isTest } from './paths'

const MAX_COMMANDS = 120
const MAX_AGENTS = 50
const MAX_BLOCKS = 20
const EVIDENCE: readonly VerifyKind[] = ['test', 'typecheck', 'build']

export function emptyLedger(sessionId: string, now: number): Ledger {
  return {
    sessionId, startedAt: now, turn: 0, turnStartedAt: now, files: {}, reads: 0, commands: [], failures: {},
    lastPass: {}, lastFail: {}, lastCodeEditAt: 0, tools: {}, errors: {}, mcp: {}, skills: [], agents: [],
    hooks: {}, blocks: [], usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, turnEdits: {},
  }
}

export function beginTurn(l: Ledger, now: number): void {
  l.turn += 1
  l.turnStartedAt = now
  l.turnEdits = {}
}

/** `mcp__claude_ai_Gmail__create_draft` → `claude_ai_Gmail`; built-ins → undefined. */
export function mcpServer(tool: string): string | undefined {
  if (!tool.startsWith('mcp__')) return undefined
  const rest = tool.slice(5)
  const cut = rest.indexOf('__')
  return cut > 0 ? rest.slice(0, cut) : rest
}

export function recordTool(l: Ledger, tool: string, isError: boolean): void {
  l.tools[tool] = (l.tools[tool] ?? 0) + 1
  if (isError) l.errors[tool] = (l.errors[tool] ?? 0) + 1
  // only a call that worked counts as using the server (as Python's PostToolUse tracker sees it)
  const server = isError ? undefined : mcpServer(tool)
  if (server) l.mcp[server] = (l.mcp[server] ?? 0) + 1
  if (tool === 'Read') l.reads += 1
}

export function recordEdit(l: Ledger, path: string, now: number, agent: string): FileTouch {
  const prev = l.files[path]
  const touch: FileTouch = prev ?? { path, edits: 0, firstAt: now, lastAt: now, lastTurn: l.turn, agents: [], code: isCode(path), test: isTest(path) }
  touch.edits += 1
  touch.lastAt = now
  touch.lastTurn = l.turn
  if (!touch.agents.includes(agent)) touch.agents.push(agent)
  l.files[path] = touch
  l.turnEdits[path] = (l.turnEdits[path] ?? 0) + 1
  if (touch.code && !isGenerated(path)) l.lastCodeEditAt = now
  return touch
}

export function recordCommand(l: Ledger, run: CommandRun): Failure | undefined {
  l.commands.push(run)
  if (l.commands.length > MAX_COMMANDS) l.commands.splice(0, l.commands.length - MAX_COMMANDS)
  for (const k of run.verify) {
    if (run.ok) l.lastPass[k] = run.at
    else l.lastFail[k] = run.at
  }
  if (run.ok) {
    delete l.failures[run.key]
    return undefined
  }
  const prev = l.failures[run.key]
  const sig = run.error ?? ''
  const f: Failure = prev && prev.sig === sig ? { ...prev, n: prev.n + 1, lastAt: run.at } : { n: 1, sig, lastAt: run.at, command: run.command }
  l.failures[run.key] = f
  return f
}

export function recordSkill(l: Ledger, name: string): void {
  if (name && !l.skills.includes(name)) l.skills.push(name)
}

export function recordAgentStart(l: Ledger, run: AgentRun): void {
  l.agents.push(run)
  if (l.agents.length > MAX_AGENTS) l.agents.splice(0, l.agents.length - MAX_AGENTS)
}

export function recordAgentEnd(l: Ledger, toolUseId: string, patch: Partial<AgentRun>): AgentRun | undefined {
  const run = l.agents.find(a => a.toolUseId === toolUseId)
  if (run) Object.assign(run, patch)
  return run
}

export function recordHook(l: Ledger, name: string, ms: number): void {
  const s = l.hooks[name] ?? { n: 0, ms: 0, max: 0 }
  s.n += 1
  s.ms += ms
  s.max = Math.max(s.max, ms)
  l.hooks[name] = s
}

export function recordBlock(l: Ledger, block: Block): void {
  l.blocks.push(block)
  if (l.blocks.length > MAX_BLOCKS) l.blocks.splice(0, l.blocks.length - MAX_BLOCKS)
}

export function addUsage(l: Ledger, u: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number | null; cache_creation_input_tokens?: number | null }): void {
  l.usage.input += u.input_tokens ?? 0
  l.usage.output += u.output_tokens ?? 0
  l.usage.cacheRead += u.cache_read_input_tokens ?? 0
  l.usage.cacheWrite += u.cache_creation_input_tokens ?? 0
}

/** When verification last passed (test, typecheck or build), 0 when never. */
export function lastEvidenceAt(l: Ledger): number {
  return Math.max(0, ...EVIDENCE.map(k => l.lastPass[k] ?? 0))
}

/** Whether `path` passed a test/typecheck/build after its last edit (unknown paths: false). */
export function verifiedSince(l: Ledger, path: string | undefined): boolean {
  const f = path === undefined ? undefined : l.files[path]
  return f !== undefined && lastEvidenceAt(l) > f.lastAt
}

/** Code files edited after the last passing test/typecheck/build. */
export function unverified(l: Ledger): FileTouch[] {
  const since = lastEvidenceAt(l)
  return Object.values(l.files).filter(f => f.code && !isGenerated(f.path) && f.lastAt > since)
}

export function loops(l: Ledger, min = 3): Failure[] {
  return Object.values(l.failures).filter(f => f.n >= min)
}

export function runningAgents(l: Ledger): AgentRun[] {
  return l.agents.filter(a => a.endedAt === undefined)
}
