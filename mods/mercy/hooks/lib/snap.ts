// Pure snapshot of the runtime for the view models and the session_state tool.

import { bestVerifyCommand } from './guard'
import { lastEvidenceAt, loops, runningAgents, unverified } from './ledger'
import { size } from './queue'
import { clockLabel } from './resume'
import { hostOffsetMinutes, rt } from './runtime'
import type { Snapshot } from './views'

export function snapshot(now: number): Snapshot {
  return {
    now,
    ledger: rt.ledger,
    bridge: rt.bridge,
    brain: rt.brain,
    contextPct: rt.contextPct,
    costUsd: rt.costUsd,
    pending: rt.pending.length,
    queued: size(),
    resumeLabel: rt.resumeAt ? clockLabel(rt.resumeAt, hostOffsetMinutes()) : undefined,
    verifyCommand: bestVerifyCommand(rt.ledger, rt.brain?.commands),
    deck: rt.deck,
    offset: hostOffsetMinutes(),
    autoCompact: rt.options.autoCompact,
    errors: rt.health.errors,
  }
}

/** The session_state tool's answer: compact, model-facing JSON. */
export function sessionState(now: number): Record<string, unknown> {
  const l = rt.ledger
  const since = lastEvidenceAt(l)
  return {
    turn: l.turn,
    repo: rt.repoRoot ?? null,
    branch: rt.branch ?? null,
    files: Object.values(l.files)
      .sort((a, b) => b.lastAt - a.lastAt)
      .slice(0, 40)
      .map(f => ({ path: f.path, edits: f.edits, code: f.code, unverified: f.code && f.lastAt > since, bySubagent: f.agents.some(a => a !== '') })),
    unverifiedCount: unverified(l).length,
    lastVerification: since ? { at: new Date(since).toISOString(), passed: Object.keys(l.lastPass) } : null,
    suggestedVerifyCommand: bestVerifyCommand(l, rt.brain?.commands) ?? null,
    recentCommands: l.commands.slice(-12).map(c => ({ command: c.command, ok: c.ok, kinds: c.kinds, ms: c.ms, error: c.error })),
    repeatedFailures: loops(l).map(f => ({ command: f.command, times: f.n, error: f.sig })),
    agents: { total: l.agents.length, running: runningAgents(l).map(a => ({ type: a.type, description: a.description, model: a.model })) },
    skillsLoaded: l.skills,
    mcpServersUsed: Object.keys(l.mcp),
    queuedHookAdvisories: rt.pending.length,
    routerGovernor: rt.governed,
    skillListingFocus: rt.focusHidden,
    bridge: { owned: rt.bridge.owned, backgroundRuns: rt.bridge.ran, failed: rt.bridge.failed, queued: size() },
    contextPercent: Math.round(rt.contextPct),
    elapsed: `${Math.round((now - l.startedAt) / 60000)} min`,
  }
}
