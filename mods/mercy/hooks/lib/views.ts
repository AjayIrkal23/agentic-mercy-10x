// Pure view models for the pulse UI: the status line, the action band and the pane rows.
// The render hooks only map these to elements, so every surface draws the same facts.

import type { BridgeStats, Deck, Ledger, PulseView, RepoFacts } from '../../types'
import { deckBand } from './deckviews'
import { ago, clip, compact, duration, meter, usd } from './format'
import { lastEvidenceAt, loops, runningAgents, unverified } from './ledger'
import { shortPath } from './paths'

export type Snapshot = {
  now: number
  ledger: Ledger
  bridge: BridgeStats
  brain: RepoFacts | null
  contextPct: number
  costUsd: number
  pending: number
  queued: number
  resumeLabel?: string
  verifyCommand?: string
  /** The deck's watched state, and the host's minutes east of UTC for clock labels. */
  deck?: Deck
  offset?: number
  autoCompact?: number
  errors?: number
}

/** Workflow facts only: model, context, cost and git live in the settings status line. */
export function statusText(s: Snapshot): string {
  const l = s.ledger
  const files = Object.values(l.files).filter(f => f.code).length
  const open = unverified(l).length
  const parts = ['mercy']
  if (files) parts.push(`✎ ${files}${open ? ` (${open} unverified)` : ''}`)
  const ev = lastEvidenceAt(l)
  if (ev) parts.push(`✓ verified ${ago(s.now, ev)}`)
  const todos = s.deck?.todos ?? []
  if (todos.length) parts.push(`☑ ${todos.filter(t => t.status === 'completed').length}/${todos.length}`)
  const ci = s.deck?.ci?.overall
  if (ci === 'fail' || ci === 'pending' || ci === 'pass') parts.push(`CI ${ci === 'fail' ? '✗' : ci === 'pending' ? '◌' : '✓'}`)
  const agents = runningAgents(l).length
  if (agents) parts.push(`⚙ ${agents} agent${agents > 1 ? 's' : ''}`)
  if (s.queued) parts.push(`⏳ ${s.queued} hook${s.queued > 1 ? 's' : ''}`)
  if (s.resumeLabel) parts.push(`⏰ resume ${s.resumeLabel}`)
  if (s.errors) parts.push(`⚠ ${s.errors} hook error${s.errors > 1 ? 's' : ''}`)
  return parts.join(' · ')
}

export type BandAction = { key: string; label: string; prompt?: string; command?: 'hide' | 'cancel-resume' | 'open-pane' | 'compact' | 'open-ci' }
export type BandModel = { lines: string[]; actions: BandAction[] }

/** Only what the user can act on; undefined keeps the band empty. */
export function bandModel(s: Snapshot): BandModel | undefined {
  const lines: string[] = []
  const actions: BandAction[] = []
  const open = unverified(s.ledger)
  if (open.length && s.verifyCommand) {
    lines.push(`⚠ ${open.length} changed code file${open.length > 1 ? 's' : ''} not verified since the last passing check`)
    actions.push({ key: 'verify', label: 'Run checks', prompt: `Run \`${s.verifyCommand}\` and fix any failures it reports.` })
  }
  const loop = loops(s.ledger)[0]
  if (loop) {
    lines.push(`⟳ \`${clip(loop.command, 48)}\` failed ${loop.n}× with the same error`)
    actions.push({ key: 'debug', label: 'Root-cause it', prompt: `\`${loop.command}\` keeps failing with: ${clip(loop.sig, 160)}. Find the root cause before re-running it (debug-investigation).` })
  }
  if (s.resumeLabel) {
    lines.push(`⏰ usage limit: auto-resume scheduled for ${s.resumeLabel}`)
    actions.push({ key: 'cancel-resume', label: 'Cancel resume', command: 'cancel-resume' })
  }
  for (const d of deckBand(s)) {
    lines.push(d.line)
    if (d.label) actions.push({ key: d.key, label: d.label, prompt: d.prompt, command: d.command })
  }
  if (s.deck?.ci?.overall === 'fail') actions.push({ key: 'ci-pane', label: 'Checks', command: 'open-ci' })
  if (lines.length === 0) return undefined
  actions.push({ key: 'pane', label: 'Pulse', command: 'open-pane' }, { key: 'hide', label: 'Hide', command: 'hide' })
  return { lines, actions }
}

/** One line of live session state for the next prompt; undefined when nothing is notable. */
export function stateLine(s: Snapshot): string | undefined {
  const l = s.ledger
  const open = unverified(l)
  const loop = loops(l)[0]
  const agents = runningAgents(l)
  if (!open.length && !loop && !agents.length) return undefined
  const parts: string[] = []
  if (open.length) {
    const names = open.slice(0, 4).map(f => shortPath(f.path, 2)).join(', ')
    parts.push(`${open.length} edited code file(s) not verified yet (${names}${open.length > 4 ? ', …' : ''})${s.verifyCommand ? `; verify with \`${clip(s.verifyCommand, 80)}\`` : ''}`)
  }
  if (loop) parts.push(`\`${clip(loop.command, 60)}\` failed ${loop.n}× in a row with the same error`)
  if (agents.length) parts.push(`${agents.length} subagent(s) still running (${agents.slice(0, 3).map(a => a.type).join(', ')})`)
  return `mercy session state: ${parts.join(' · ')}. Full detail: mcp__mercy__session_state.`
}

export const VIEWS: readonly PulseView[] = ['overview', 'usage', 'git', 'ci', 'todo', 'today', 'ports', 'deps', 'files', 'commands', 'agents', 'hooks', 'brain']
/** The pane's tab hotkeys: mnemonic letters (a Button hotkey is one digit or lowercase letter). */
export const VIEW_KEYS: Record<PulseView, string> = {
  overview: 'o', usage: 'u', git: 'g', ci: 'i', todo: 't', today: 's', ports: 'p', deps: 'd', files: 'f', commands: 'c', agents: 'a', hooks: 'h', brain: 'b',
}

export function paneRows(view: PulseView, s: Snapshot, width: number): string[] {
  const w = Math.max(30, width)
  const l = s.ledger
  const fit = (t: string): string => clip(t, w)
  if (view === 'files') {
    const files = Object.values(l.files).sort((a, b) => b.lastAt - a.lastAt)
    const since = lastEvidenceAt(l)
    if (!files.length) return ['No files edited this session.']
    return files.slice(0, 40).map(f => fit(`${f.code && f.lastAt > since ? '⚠' : '·'} ${shortPath(f.path, 3)}  ×${f.edits}  ${ago(s.now, f.lastAt)}${f.agents.some(a => a) ? '  (subagent)' : ''}`))
  }
  if (view === 'commands') {
    if (!l.commands.length) return ['No Bash commands yet.']
    return l.commands.slice(-30).reverse().map(c => fit(`${c.ok ? '✓' : '✗'} ${c.kinds.filter(k => k !== 'other').join('+') || 'cmd'}  ${duration(c.ms)}  ${c.command.replace(/\s+/g, ' ')}`))
  }
  if (view === 'agents') {
    if (!l.agents.length) return ['No subagents yet.']
    return l.agents.slice(-25).reverse().map(a => fit(`${a.endedAt === undefined ? '⚙' : a.ok === false ? '✗' : '✓'} ${a.type}${a.model ? ` [${a.model}]` : ''}  ${a.endedAt ? duration(a.endedAt - a.startedAt) : `${duration(s.now - a.startedAt)} running`}  ${a.description}`))
  }
  if (view === 'hooks') {
    const rows = Object.entries(l.hooks).sort(([, a], [, b]) => b.ms - a.ms).slice(0, 14)
      .map(([name, h]) => fit(`${name}  n=${h.n}  avg ${duration(h.ms / Math.max(1, h.n))}  max ${duration(h.max)}`))
    const b = s.bridge
    return [
      fit(`Python links owned by the bridge: ${b.owned.length ? b.owned.join(', ') : 'none (Python runs every link)'}`),
      fit(`Background runs: ${b.ran} done, ${b.failed} failed, ${s.queued} queued · advisories delivered: ${b.delivered} · blocking time saved ≈ ${duration(b.savedMs)}`),
      ...(b.lastError ? [fit(`Last bridge error: ${b.lastError}`)] : []),
      'Python hook chains (classic.*, measured in-process):',
      ...rows,
    ]
  }
  if (view === 'brain') {
    const f = s.brain
    if (!f) return ['No repo brain yet (not in a git repo, or nothing learned).']
    return [
      fit(`${f.name} · ${f.sessions} session(s) · toolchain: ${[f.packageManager, ...f.stack].filter(Boolean).join(', ') || '?'}`),
      ...Object.values(f.commands).map(k => fit(`${k.lastOk ? '✓' : '✗'} ${k.kind}  ${k.command}  (${k.passes} pass / ${k.fails} fail)`)),
      ...f.fixes.slice(-5).map(x => fit(`fix: ${x.command} ← ${x.files.join(', ')}`)),
      ...f.notes.slice(-6).map(n => fit(`note: ${n.text}`)),
    ]
  }
  const ev = lastEvidenceAt(l)
  return [
    fit(`Turn ${l.turn} · session ${duration(s.now - l.startedAt)} · tools ${compact(Object.values(l.tools).reduce((a, b) => a + b, 0))} · errors ${compact(Object.values(l.errors).reduce((a, b) => a + b, 0))}`),
    fit(`Context ${meter(s.contextPct)} ${Math.round(s.contextPct)}% · cost ${usd(s.costUsd) || '?'} · tokens in ${compact(l.usage.input + l.usage.cacheRead + l.usage.cacheWrite)} out ${compact(l.usage.output)}`),
    fit(`Files edited ${Object.keys(l.files).length} · unverified ${unverified(l).length} · last verification ${ev ? ago(s.now, ev) : 'never'}`),
    fit(`Agents ${l.agents.length} (${runningAgents(l).length} running) · skills loaded ${l.skills.length} · MCP servers used ${Object.keys(l.mcp).length}`),
    fit(`Bridge: ${s.bridge.owned.length} links owned · ${s.queued} queued · saved ≈ ${duration(s.bridge.savedMs)}`),
    ...(s.resumeLabel ? [fit(`Auto-resume scheduled for ${s.resumeLabel}`)] : []),
    ...loops(l).slice(0, 3).map(f => fit(`⟳ ${f.command} failed ${f.n}×: ${f.sig}`)),
  ]
}
