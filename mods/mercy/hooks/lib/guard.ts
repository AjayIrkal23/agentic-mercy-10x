// Pure guard decisions. The feature files call these with facts they gathered and turn
// the answers into denies, tool-result context or Stop blocks. Every message names the
// rule it enforces and what to do instead, so a refusal is a route, not a dead end.

import type { Failure, KnownCommand, Ledger } from '../../types'
import type { CommandInfo } from './commands'
import { clip } from './format'
import { shortPath } from './paths'
import type { SecretHit } from './secrets'
import { lastEvidenceAt, unverified } from './ledger'

export function bashDeny(command: string, info: CommandInfo, agentId: string | undefined): string | undefined {
  const shown = clip(command.replace(/\s+/g, ' '), 90)
  if (info.isServer) {
    return `mercy guard: \`${shown}\` starts a dev server or long-running service. The user runs apps themselves (CLAUDE.md §5): verify with a build, the tests or a linter instead. If the user explicitly asked for it, ask them to start it, or they can turn off guard in /config.`
  }
  if (info.isWatch) {
    return `mercy guard: \`${shown}\` starts a watcher that never exits (CLAUDE.md §5). Use the one-shot form instead: \`vitest run\`, \`jest\` without --watch, \`tsc --noEmit\`.`
  }
  if (agentId !== undefined && (info.isCommit || info.isPush)) {
    return `mercy guard: subagents never commit or push (CLAUDE.md §2). Leave the change in the working tree and list it in your report; the lead commits when the user asks.`
  }
  return undefined
}

export function secretDeny(path: string, hit: SecretHit): string {
  const fixture = hit.kind === 'private key'
    ? "if this is a test fixture, split the header (`'-----BEGIN ' + 'PRIVATE KEY-----'`) so the file holds no literal key"
    : 'if this is a fake fixture value, mark it (e.g. EXAMPLE) and retry'
  return `mercy guard: the text for ${shortPath(path, 3)} contains what looks like a live ${hit.kind} (${hit.sample}). Keep secrets in a gitignored .env or a secret store and read them by name; ${fixture}.`
}

/** A nudge at the 3rd and 6th identical failure of the same command. */
export function loopNudge(f: Failure): string | undefined {
  if (f.n !== 3 && f.n !== 6) return undefined
  return `mercy: \`${clip(f.command, 80)}\` has failed ${f.n} times in a row with the same error (${clip(f.sig, 110)}). Stop re-running it as is: read the failing code path and find the root cause first (debug-investigation / superpowers:systematic-debugging).`
}

/** A nudge when one file is patched again and again inside a single turn. */
export function thrashNudge(path: string, editsThisTurn: number): string | undefined {
  if (editsThisTurn !== 8) return undefined
  return `mercy: ${shortPath(path, 3)} was edited ${editsThisTurn} times this turn. Step back: re-read the whole file and make one deliberate change instead of more incremental patches.`
}

/** The command to suggest for verification: this session's last passing one, else the brain's best. */
export function bestVerifyCommand(l: Ledger, known: Record<string, KnownCommand> | undefined): string | undefined {
  for (let i = l.commands.length - 1; i >= 0; i--) {
    const c = l.commands[i]
    if (c && c.ok && c.verify.some(k => k !== 'lint')) return c.command
  }
  const ranked = Object.values(known ?? {})
    .filter(k => k.kind !== 'lint' && k.passes > 0)
    .sort((a, b) => Number(b.kind === 'test') - Number(a.kind === 'test') || b.passes - a.passes || b.lastAt - a.lastAt)
  return ranked[0]?.command
}

export type VerifyFacts = {
  mode: 'block' | 'advise' | 'off'
  stopHookActive: boolean
  backgroundBusy: boolean
  /** Any Stop block (Python, verify, late advisories) already happened this human turn. */
  alreadyBlockedThisTurn: boolean
  command: string | undefined
  /** The user's last prompt told the agent to stop (lib/consent). */
  consent?: boolean
}

export type VerifyDecision = { kind: 'block' | 'advise'; text: string }

/** Code edited this turn after the last passing test/typecheck/build → one block per turn. */
export function verifyDecision(l: Ledger, f: VerifyFacts): VerifyDecision | undefined {
  if (f.mode === 'off' || f.consent || f.stopHookActive || f.backgroundBusy || f.alreadyBlockedThisTurn) return undefined
  const files = unverified(l).filter(t => t.lastTurn === l.turn)
  if (files.length === 0) return undefined
  const names = files.slice(0, 5).map(t => shortPath(t.path, 2)).join(', ') + (files.length > 5 ? ` +${files.length - 5} more` : '')
  const failedAfter = Math.max(0, ...Object.values(l.lastFail).map(v => v ?? 0)) > lastEvidenceAt(l)
  const why = failedAfter ? 'the last verification run after them FAILED' : 'nothing verified them after the last edit'
  if (f.mode === 'block' && f.command) {
    return {
      kind: 'block',
      text: `mercy verify gate: ${files.length} code file(s) changed this turn (${names}) and ${why}. Run \`${clip(f.command, 120)}\` (or the narrower test for these files) and report the result before finishing (CLAUDE.md §5: evidence before "done"). If verification is impossible here, say why in one line.`,
    }
  }
  return { kind: 'advise', text: `mercy: ${files.length} changed code file(s) not verified (${names}).` }
}
