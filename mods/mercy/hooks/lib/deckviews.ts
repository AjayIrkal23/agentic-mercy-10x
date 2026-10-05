// Pure view models for the deck: the usage, git, ci and todo pane views (coloured rows)
// and the markdown of the slash command cards. The render hooks only map these to elements.

import type { CiState, Deck, GitState, Limit, Todo } from '../../types'
import { crossed, resetLabel } from './deck'
import { ago, clip, compact, duration, meter, usd } from './format'
import { lastEvidenceAt, loops, runningAgents, unverified } from './ledger'
import { shortPath } from './paths'
import type { Outdated, Port } from './probes'
import type { Snapshot } from './views'

/** One pane line; `spark` marks where the usage view draws its Raster sparkline. */
export type Row = { text: string; color?: string; dim?: boolean; bold?: boolean; spark?: true }

const LIMIT_NAMES: Record<string, string> = { five_hour: '5-hour', seven_day: '7-day', spend_limit: 'spend' }
const STATE_COLOR: Record<string, string> = { M: 'yellow', A: 'green', D: 'red', R: 'cyan', U: 'red', '?': 'gray' }
const CHECK_MARK = { pass: ['✓', 'green'], fail: ['✗', 'red'], pending: ['◌', 'yellow'], skip: ['–', 'gray'] } as const

function severity(percent: number): string {
  return percent >= 80 ? 'red' : percent >= 50 ? 'yellow' : 'green'
}

function limitName(l: Limit): string {
  return LIMIT_NAMES[l.kind] ?? l.kind
}

/** $/hour over the session, once it has run five minutes. */
function burnRate(costUsd: number, elapsedMs: number): number | undefined {
  return elapsedMs >= 300_000 && costUsd > 0 ? costUsd / (elapsedMs / 3_600_000) : undefined
}

export function usageRows(s: Snapshot, width: number): Row[] {
  const d = s.deck
  const fit = (t: string): string => clip(t, Math.max(30, width))
  const elapsed = s.now - s.ledger.startedAt
  const burn = burnRate(s.costUsd, elapsed)
  const u = s.ledger.usage
  const rows: Row[] = [
    { text: fit(`Context   ${meter(s.contextPct)} ${Math.round(s.contextPct)}%`), color: severity(s.contextPct) },
    ...(d?.limits ?? []).map(l => ({
      text: fit(`${limitName(l).padEnd(9)} ${meter(l.percent)} ${Math.round(l.percent)}%  ${l.resetsAt ? `resets ${resetLabel(l.resetsAt, s.now, s.offset ?? 0)}` : ''}`),
      color: severity(l.percent),
    })),
    { text: fit(`Cost      ${usd(s.costUsd) || '$0.00'}${burn ? ` · burn ${usd(burn)}/h` : ''} · ${s.ledger.turn} turns · session ${duration(elapsed)}`) },
    { text: fit(`Tokens    in ${compact(u.input + u.cacheRead + u.cacheWrite)} (cache read ${compact(u.cacheRead)}) · out ${compact(u.output)}`), dim: true },
  ]
  const turns = d?.turns ?? []
  if (turns.length) {
    rows.push({ text: 'Output tokens per turn (newest right):', dim: true })
    rows.push({ text: '', spark: true })
    for (const t of turns.slice(-5).reverse()) {
      rows.push({ text: fit(`${ago(s.now, t.at).padEnd(10)} ${duration(t.ms).padEnd(7)} ${(usd(t.costUsd) || '$0.00').padEnd(7)} out ${compact(t.output).padEnd(6)} ctx ${Math.round(t.ctxPct)}%`), dim: true })
    }
  }
  return rows
}

export function gitRows(g: GitState | undefined, now: number, width: number): Row[] {
  const fit = (t: string): string => clip(t, Math.max(30, width))
  if (!g) return [{ text: 'No git data yet (not a git repo, or the first refresh has not run). Press r to refresh.', dim: true }]
  const counts = [`staged ${g.staged}`, `modified ${g.modified}`, `untracked ${g.untracked}`, ...(g.conflicts ? [`conflicts ${g.conflicts}`] : [])]
  const rows: Row[] = [
    { text: fit(`⎇ ${g.branch}${g.upstream ? ` → ${g.upstream}` : ' (no upstream)'}${g.ahead ? `  ↑${g.ahead}` : ''}${g.behind ? `  ↓${g.behind}` : ''}`), bold: true },
    { text: counts.join(' · '), color: g.conflicts ? 'red' : undefined, dim: !g.conflicts },
    ...g.files.slice(0, 20).map(f => ({ text: fit(`${f.state.padEnd(2)} ${f.path}${f.add || f.del ? `  +${f.add} −${f.del}` : ''}`), color: STATE_COLOR[f.state] })),
  ]
  if (g.total > 20) rows.push({ text: `… ${g.total - 20} more`, dim: true })
  if (!g.files.length) rows.push({ text: 'Working tree clean.', color: 'green' })
  if (g.commits.length) rows.push({ text: 'Recent commits:', dim: true }, ...g.commits.map(c => ({ text: fit(`${c.sha}  ${c.subject}  (${ago(now, c.at)})`), dim: true })))
  rows.push({ text: `updated ${ago(now, g.at)}`, dim: true })
  return rows
}

export function ciLine(ci: CiState | undefined): string {
  if (!ci || ci.source === 'none') return 'no PR or workflow runs for this branch'
  if (ci.source === 'error') return `CI unavailable: ${clip(ci.error ?? 'gh failed', 80)}`
  const n = (st: string): number => ci.checks.filter(c => c.state === st).length
  const head = ci.pr ? `PR #${ci.pr.number}` : 'workflow runs'
  return `${head}: ${n('pass')}/${ci.checks.length} checks pass${n('fail') ? `, ${n('fail')} failing (${ci.checks.filter(c => c.state === 'fail').map(c => c.name).slice(0, 3).join(', ')})` : ''}${n('pending') ? `, ${n('pending')} pending` : ''}`
}

export function ciRows(ci: CiState | undefined, now: number, width: number): Row[] {
  const fit = (t: string): string => clip(t, Math.max(30, width))
  if (!ci) return [{ text: 'No CI data yet. Press r to refresh (needs gh and a GitHub remote).', dim: true }]
  const rows: Row[] = []
  if (ci.pr) {
    const p = ci.pr
    rows.push({ text: fit(`PR #${p.number} ${p.title}`), bold: true })
    rows.push({ text: fit(`${p.state.toLowerCase()}${p.draft ? ' · draft' : ''}${p.review ? ` · ${p.review.toLowerCase().replace(/_/g, ' ')}` : ''} · ${p.url}`), dim: true })
  }
  const mark = ci.overall === 'none' ? CHECK_MARK.skip : CHECK_MARK[ci.overall]
  rows.push({ text: fit(`${mark[0]} ${ciLine(ci)}`), color: mark[1] })
  for (const c of ci.checks) rows.push({ text: fit(`  ${CHECK_MARK[c.state][0]} ${c.name}`), color: CHECK_MARK[c.state][1] })
  rows.push({ text: `updated ${ago(now, ci.at)}`, dim: true })
  return rows
}

export function todoRows(todos: readonly Todo[], width: number): Row[] {
  const fit = (t: string): string => clip(t, Math.max(30, width))
  if (!todos.length) return [{ text: 'No task list yet: the model has not used TodoWrite or TaskCreate this session.', dim: true }]
  const done = todos.filter(t => t.status === 'completed').length
  return [
    { text: `${done}/${todos.length} done  ${meter((done / todos.length) * 100)}`, color: done === todos.length ? 'green' : undefined, bold: true },
    ...todos.map(t => (t.status === 'completed' ? { text: fit(`☑ ${t.text}`), dim: true } : t.status === 'in_progress' ? { text: fit(`◐ ${t.text}`), color: 'yellow', bold: true } : { text: fit(`☐ ${t.text}`) })),
  ]
}

/** Band rows the deck adds: context, the 5-hour window, a failing CI. */
export function deckBand(s: Snapshot): Array<{ line: string; key: string; label?: string; prompt?: string; command?: 'compact' | 'open-ci' }> {
  const out: Array<{ line: string; key: string; label?: string; prompt?: string; command?: 'compact' | 'open-ci' }> = []
  const t = s.autoCompact ?? 0
  if (s.contextPct >= 80) out.push({ line: `◔ context ${Math.round(s.contextPct)}%${t ? `: compacts by itself between turns at ${t}%` : ''}`, key: 'compact', label: 'Compact now', command: 'compact' })
  const five = s.deck?.limits.find(l => l.kind === 'five_hour')
  if (five && five.percent >= 85) out.push({ line: `⏳ 5-hour usage ${Math.round(five.percent)}%${five.resetsAt ? `, resets ${resetLabel(five.resetsAt, s.now, s.offset ?? 0)}` : ''}`, key: 'limit' })
  const ci = s.deck?.ci
  if (ci?.overall === 'fail') {
    const names = ci.checks.filter(c => c.state === 'fail').map(c => c.name).slice(0, 3).join(', ')
    const where = ci.pr ? `PR #${ci.pr.number}` : 'this branch'
    out.push({ line: `✗ CI failing on ${where}: ${names}`, key: 'ci', label: 'Fix CI', prompt: `CI is failing on ${where} (${names}). Read the failing logs with \`gh run view --log-failed\`, find the root cause, fix it and verify locally.` })
  }
  return out
}

/** Toast lines for usage marks crossed between two readings. */
export function usageToasts(prevCtx: number, ctx: number, prev: readonly Limit[], next: readonly Limit[]): string[] {
  const out: string[] = []
  const c = crossed(prevCtx, ctx, [70, 85])
  if (c) out.push(`context ${Math.round(ctx)}%: mercy compacts between turns at its threshold`)
  for (const l of next) {
    const m = crossed(prev.find(p => p.kind === l.kind)?.percent ?? 0, l.percent, [80, 95])
    if (m) out.push(`${limitName(l)} usage ${Math.round(l.percent)}%`)
  }
  return out
}

// ---- command cards (markdown) --------------------------------------------------------

export function recapMarkdown(s: Snapshot, deck: Deck | undefined): string {
  const l = s.ledger
  const files = Object.values(l.files).sort((a, b) => b.edits - a.edits)
  const failed = l.commands.filter(c => !c.ok).length
  const ev = lastEvidenceAt(l)
  const tools = Object.entries(l.tools).sort(([, a], [, b]) => b - a).slice(0, 6).map(([t, n]) => `${t} ${n}`).join(' · ')
  const burn = burnRate(s.costUsd, s.now - l.startedAt)
  const done = deck?.todos.filter(t => t.status === 'completed').length ?? 0
  return [
    '### Session recap',
    '| | |', '|---|---|',
    `| Duration | ${duration(s.now - l.startedAt)} · ${l.turn} turns |`,
    `| Cost | ${usd(s.costUsd) || '$0.00'}${burn ? ` (burn ${usd(burn)}/h)` : ''} |`,
    `| Context | ${Math.round(s.contextPct)}% |`,
    `| Files edited | ${files.length} (${unverified(l).length} not verified yet) |`,
    `| Commands | ${l.commands.length} (${failed} failed) · last verification ${ev ? ago(s.now, ev) : 'never'} |`,
    `| Subagents | ${l.agents.length} (${runningAgents(l).length} running) |`,
    ...(deck?.todos.length ? [`| Tasks | ${done}/${deck.todos.length} done |`] : []),
    `| Top tools | ${tools || '-'} |`,
    '',
    ...(files.length ? [`**Files:** ${files.slice(0, 12).map(f => `\`${shortPath(f.path, 2)}\` ×${f.edits}`).join(', ')}${files.length > 12 ? ', …' : ''}`] : []),
    ...loops(l).slice(0, 3).map(f => `**Repeated failure:** \`${clip(f.command, 60)}\` ×${f.n}`),
  ].join('\n')
}

export function standupMarkdown(commits: ReadonlyArray<{ sha: string; subject: string; at: number }>, sinceLabel: string, s: Snapshot, deck: Deck | undefined): string {
  const l = s.ledger
  const files = Object.values(l.files).sort((a, b) => b.lastAt - a.lastAt)
  const doing = deck?.todos.filter(t => t.status !== 'completed') ?? []
  const blockers = [
    ...(deck?.ci?.overall === 'fail' ? [`CI failing: ${ciLine(deck.ci)}`] : []),
    ...loops(l).slice(0, 2).map(f => `\`${clip(f.command, 50)}\` keeps failing`),
  ]
  return [
    `### Standup (since ${sinceLabel})`,
    '**Done**',
    ...(commits.length ? commits.slice(0, 15).map(c => `- ${c.subject} (\`${c.sha}\`)`) : ['- no commits']),
    ...(files.length ? [`- This session: edited ${files.length} file(s) (${files.slice(0, 5).map(f => shortPath(f.path, 2)).join(', ')}${files.length > 5 ? ', …' : ''}); ${unverified(l).length ? `${unverified(l).length} not verified yet` : 'all verified'}`] : []),
    '**Next**',
    ...(doing.length ? doing.slice(0, 6).map(t => `- ${t.text}`) : ['- (no open tasks)']),
    '**Blockers**',
    ...(blockers.length ? blockers.map(b => `- ${b}`) : ['- none']),
  ].join('\n')
}

export function portsMarkdown(ports: readonly Port[]): string {
  if (!ports.length) return 'Nothing is listening on TCP.'
  return [
    '### Listening ports',
    '| Port | Address | Process | PID | What |', '|---:|---|---|---:|---|',
    ...ports.map(p => {
      const local = p.address === '127.0.0.1' || p.address === '0.0.0.0' || p.address === '::' || p.address === '*'
      const port = local && p.label && /dev|vite|expo/.test(p.label) ? `[${p.port}](http://localhost:${p.port})` : String(p.port)
      return `| ${port} | ${p.address} | ${p.process ?? '-'} | ${p.pid ?? '-'} | ${p.label ?? ''} |`
    }),
  ].join('\n')
}

export function depsMarkdown(rows: readonly Outdated[], dir: string): string {
  if (!rows.length) return `All npm packages in \`${dir}\` are current.`
  return [
    `### Outdated packages in \`${dir}\``,
    '| Package | Current | Wanted | Latest | Bump |', '|---|---|---|---|---|',
    ...rows.map(r => `| ${r.name} | ${r.current} | ${r.wanted} | ${r.latest} | ${r.bump === 'major' ? '**major**' : r.bump} |`),
  ].join('\n')
}
