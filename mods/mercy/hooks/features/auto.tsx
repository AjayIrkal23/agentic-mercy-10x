// Autonomous jobs: nothing here waits for a command. Listening ports every minute (a toast
// when a dev server comes up or stops), npm outdated once a day per package folder, today's
// standup at the first session of the day in a repo, this session's recap saved after every
// turn (the next session shows it), and compaction between turns at `autoCompact`.
// /ports, /deps and /standup stay as optional extras that print a card.

import type { EngineInterface, On } from 'claude-code'
import { update } from 'claude-code'

import type { Card, DepRow, DepsState, LastSession, PortRow, Standup } from '../../types'
import { dayKey, depsDue, sessionSummary, shouldCompact, standupDays, withCard, portChanges } from '../lib/auto'
import { depsMarkdown, portsMarkdown, standupMarkdown } from '../lib/deckviews'
import { clip } from '../lib/format'
import { join } from '../lib/paths'
import { netstatRows, npmFailed, parseNetstat, parseOutdated, parsePorts, parseTasklist, portCmds } from '../lib/probes'
import { hostOffsetMinutes, noteError, rt, ui } from '../lib/runtime'
import { snapshot } from '../lib/snap'
import { PANE_ID } from '../lib/specs'

const DECK = { plugin: 'mercy', key: 'deck' } as const
const VIEW = { plugin: 'mercy', key: 'view' } as const
const CARDS = { plugin: 'mercy', key: 'cards' } as const
const KEEP = 'Keep: the current plan and its next step, open tasks, files changed and which are not verified yet, commands that failed and why, and every decision the user made.'

let compactedAt = 0
let compacting = false

function toast($: EngineInterface, text: string, failure: boolean, timeoutMs = 6000): void {
  const t = ui().toasts
  if (t === 'all' || (t === 'failures' && failure)) $.ui.toast(text, { timeoutMs })
}

async function publish($: EngineInterface): Promise<void> {
  await $.state.set(DECK, rt.deck)
}

function later($: EngineInterface, ms: number, what: string, job: () => Promise<unknown>): void {
  $.clock.after(ms, () => void job().catch(err => noteError(what, err)))
}

const SCAN_MS = 10_000 // tasklist alone takes up to a second on a loaded box
const NAMES_MS = 120_000 // a pid name older than this is asked again (Windows reuses pids fast)
let names = new Map<number, string>() // pid → image name from the last tasklist
let namesAt = 0
let seen = new Set<string>() // `pid:port` of the listeners at the last tasklist

async function stdout($: EngineInterface, argv: string[]): Promise<string> {
  const r = await $.process.run(argv, { timeoutMs: SCAN_MS })
  if (r.exitCode !== 0) throw new Error(`${argv[0]} exited ${r.exitCode}${r.stderr.trim() ? `: ${clip(r.stderr.trim(), 100)}` : ''}`)
  return r.stdout
}

/** The listening TCP ports now; rejects with the reason when a scanner cannot run or fails. */
async function scanPorts($: EngineInterface): Promise<PortRow[]> {
  const [first = [], tcp6 = [], tasks = []] = portCmds(rt.windows, rt.systemRoot)
  if (!rt.windows) return parsePorts(await stdout($, first))
  const [v4, v6] = await Promise.all([stdout($, first), stdout($, tcp6)])
  const now = await $.clock.now()
  // tasklist is the slow one: asked again for a pid it has not named, for a listener (pid, port) that is new (a
  // reused pid keeps its old name otherwise, A2v2-01), and after NAMES_MS
  const listeners = [...netstatRows(v4), ...netstatRows(v6)].filter(r => r.pid > 0)
  if (now - namesAt > NAMES_MS || listeners.some(r => !names.has(r.pid) || !seen.has(`${r.pid}:${r.port}`))) {
    names = parseTasklist(await stdout($, tasks))
    namesAt = now
    seen = new Set(listeners.map(r => `${r.pid}:${r.port}`))
  }
  return parseNetstat(v4, v6, names)
}

/** A failed scan keeps the last good rows and sets `portsError` (pane, card and summary say so); the next good scan clears it. */
async function refreshPorts($: EngineInterface, announce: boolean): Promise<void> {
  const ports = await scanPorts($).catch((err: unknown) => {
    rt.deck.portsError = clip(err instanceof Error ? err.message : String(err), 160)
    return undefined
  })
  if (ports) {
    const changes = announce ? portChanges(rt.deck.ports, ports) : []
    rt.deck.ports = ports
    delete rt.deck.portsError
    await publish($)
    for (const line of changes) toast($, `mercy: ${line}`, false)
  } else await publish($)
}

/** The repo root and its first-level folders that hold a package.json (at most 6). */
async function packageDirs($: EngineInterface, root: string): Promise<string[]> {
  const entries = await $.fs.list(root).catch(() => [])
  const dirs = [root, ...entries.filter(e => e.kind === 'dir' && !e.name.startsWith('.') && e.name !== 'node_modules').map(e => join(root, e.name))]
  const out: string[] = []
  for (const d of dirs) if (out.length < 6 && (await $.fs.exists(join(d, 'package.json')))) out.push(d)
  return out
}

/** The folder's outdated packages, or why npm could not say (a string): exit 1 only means "some are outdated". */
async function outdated($: EngineInterface, dir: string): Promise<DepRow[] | string> {
  try {
    const r = await $.process.run(['npm', 'outdated', '--json'], { cwd: dir, timeoutMs: 120_000 })
    if (r.exitCode >= 2) return `npm exited ${r.exitCode}`
    if (npmFailed(r.stdout)) return 'npm reported an error (offline or registry unreachable)'
    return parseOutdated(r.stdout)
  } catch (err) {
    return err instanceof Error ? err.message : String(err) // the canary: an engine that cannot start npm shows up in /mercy status
  }
}

async function refreshDeps($: EngineInterface): Promise<DepsState | undefined> {
  const root = rt.repoRoot ?? (await $.session.cwd().catch(() => ''))
  if (!root) return undefined
  const dirs = await packageDirs($, root)
  if (!dirs.length) return undefined
  const checked: DepsState['dirs'] = []
  const failures: string[] = []
  for (const dir of dirs) {
    const rows = await outdated($, dir)
    if (typeof rows === 'string') failures.push(rows)
    else checked.push({ dir, rows })
  }
  // a folder npm could not check is not stored as current: the next session asks again
  if (!checked.length) throw new Error(`npm outdated could not check any folder (${clip(failures[0] ?? '', 120)})`)
  if (failures.length) noteError('deps', new Error(`npm outdated could not check ${failures.length} of ${dirs.length} folders (${clip(failures[0] ?? '', 120)})`))
  const deps: DepsState = { at: await $.clock.now(), dirs: checked, ...(failures.length ? { partial: true } : {}) }
  rt.deck.deps = deps
  await $.store.set(`deps:${root}`, deps)
  await publish($)
  const majors = checked.reduce((n, d) => n + d.rows.filter(r => r.bump === 'major').length, 0)
  if (majors) toast($, `mercy: ${majors} major npm update${majors > 1 ? 's' : ''} available (pane, d)`, false, 8000)
  return deps
}

async function makeStandup($: EngineInterface): Promise<Standup | undefined> {
  const root = rt.repoRoot
  if (!root) return undefined
  const now = await $.clock.now()
  const days = standupDays(now, hostOffsetMinutes())
  const email = await $.process.run(['git', 'config', 'user.email'], { cwd: root, timeoutMs: 3000 }).then(r => r.stdout.trim(), () => '')
  const argv = ['git', '--no-optional-locks', '-c', 'safe.directory=*', 'log', `--since=${days} days ago 00:00`, '--no-merges', '--format=%h%x1f%s%x1f%ct', ...(email ? [`--author=${email}`] : [])]
  const out = await $.process.run(argv, { cwd: root, timeoutMs: 5000 }).then(r => (r.exitCode === 0 ? r.stdout : ''), () => '')
  const commits = out.split('\n').map(l => l.split('\x1f')).filter(p => p[0] && p[1] !== undefined).map(([sha, subject, ct]) => ({ sha: sha ?? '', subject: subject ?? '', at: Number(ct) * 1000 }))
  const since = days === 1 ? 'yesterday' : `${days} days ago`
  const standup: Standup = { day: dayKey(now, hostOffsetMinutes()), markdown: standupMarkdown(commits, since, snapshot(now), rt.deck), at: now }
  rt.deck.standup = standup
  await $.store.set(`standup:${root}`, standup)
  await publish($)
  return standup
}

async function card($: EngineInterface, command: string, title: string, markdown: string, summary: string, copy?: string): Promise<string> {
  const now = await $.clock.now()
  rt.cardSeq = Math.max(now, rt.cardSeq + 1)
  const c: Card = { id: rt.cardSeq, command, title, markdown, copy, at: now }
  await update($, CARDS, all => withCard(all, c))
  return `${command} #${c.id}: ${summary}`
}

export function registerAuto(on: On): void {
  // runs inside deck.tsx's session.start (registered earlier), after rt.deck is settled
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    try {
      const root = rt.repoRoot
      if (root) {
        const now = await $.clock.now()
        const deps = (await $.store.get(`deps:${root}`)) as DepsState | undefined
        const standup = (await $.store.get(`standup:${root}`)) as Standup | undefined
        const last = (await $.store.get(`recap:${root}`)) as LastSession | undefined
        if (deps?.dirs) rt.deck.deps = deps
        if (standup?.markdown) rt.deck.standup = standup
        if (last?.at && last.at < rt.ledger.startedAt) rt.deck.lastSession = last // not this session's own, after a reload
        await publish($)
        if (standup?.day !== dayKey(now, hostOffsetMinutes())) later($, 4000, 'standup', async () => (await makeStandup($)) && toast($, "mercy: today's standup is ready (pane, s)", false))
        if (depsDue(deps, now)) later($, 60_000, 'deps', () => refreshDeps($))
      }
      later($, 2000, 'ports', () => refreshPorts($, false))
      $.clock.every(60_000, () => void refreshPorts($, true).catch(err => noteError('ports', err)))
    } catch (err) {
      noteError('auto start', err)
    }
    return next(e)
  })

  on('turn.complete', { isAborted: false }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (e.agentId !== undefined) return r
      const now = await $.clock.now()
      if (rt.repoRoot) await $.store.set(`recap:${rt.repoRoot}`, sessionSummary(rt.ledger, now, rt.costUsd))
      const ctx = (await $.session.usage().catch(() => undefined))?.context.percent ?? rt.contextPct
      if (!compacting && shouldCompact({ threshold: rt.options.autoCompact, contextPct: ctx, now, lastAt: compactedAt, interactive: rt.interactive })) {
        compacting = true
        toast($, `mercy: context ${Math.round(ctx)}%, compacting between turns`, false)
        // the 10-minute spacing counts from a compaction that happened: one a racing prompt
        // rejected is tried again after the next turn (SANTA-autonomy)
        later($, 1500, 'auto-compact', async () => {
          try {
            const done = (await $.session.compact({ instructions: KEEP })) as { skip?: unknown } | undefined
            if (!done?.skip) compactedAt = await $.clock.now()
          } finally {
            compacting = false
          }
        })
      }
    } catch (err) {
      noteError('auto turn.complete', err)
    }
    return r
  })

  on('ui.press', { requestId: PANE_ID }, async ($, e, next) => {
    const r = await next(e)
    try {
      const force = e.element === 'refresh'
      const view = force ? (await $.state.get(VIEW)).value : e.element.replace(/^tab-/, '')
      if (view === 'ports') later($, 0, 'ports', () => refreshPorts($, true))
      if (view === 'deps' && (force || !rt.deck.deps)) later($, 0, 'deps', () => refreshDeps($))
      if (view === 'today' && (force || !rt.deck.standup)) later($, 0, 'standup', () => makeStandup($))
    } catch (err) {
      noteError('auto refresh', err)
    }
    return r
  })

  on('command.run', { command: ['ports', 'deps', 'standup'] }, async ($, e) => {
    try {
      if (e.command === 'ports') {
        await refreshPorts($, false)
        const ports = rt.deck.ports ?? []
        const failed = rt.deck.portsError
        const listed = `${ports.length} listening (${ports.slice(0, 4).map(p => `${p.port} ${p.process ?? p.label ?? '?'}`).join(', ')}${ports.length > 4 ? ', …' : ''})`
        return { text: await card($, 'ports', 'Listening ports', portsMarkdown(ports, failed), failed ? `port scan failed: ${failed}` : listed) }
      }
      if (e.command === 'deps') {
        const deps = await refreshDeps($)
        if (!deps) return { text: 'deps: no package.json in this repo.' }
        const md = deps.dirs.map(d => depsMarkdown(d.rows, d.dir)).join('\n\n')
        const n = deps.dirs.reduce((s, d) => s + d.rows.length, 0)
        const majors = deps.dirs.reduce((s, d) => s + d.rows.filter(x => x.bump === 'major').length, 0)
        return { text: await card($, 'deps', 'Outdated packages', md, `${n} outdated (${majors} major) in ${deps.dirs.length} folder(s)`) }
      }
      const s = await makeStandup($)
      if (!s) return { text: 'standup: not in a git repo.' }
      return { text: await card($, 'standup', 'Standup', s.markdown, `ready for ${s.day}`, s.markdown) }
    } catch (err) {
      noteError(`/${e.command}`, err)
      return { text: `/${e.command} failed: ${err instanceof Error ? err.message : String(err)}` }
    }
  })
}
