// The deck's watchers: git (every minute and after writes or git commands), GitHub CI
// (every 3 minutes and after a push), context and rate limits (session.measure), the
// model's task list, verify pass/fail flips; `/ci` and `/ui`. Display only: nothing here
// reaches the model except the one-line text a command prints.

import type { EngineInterface, On, Timer } from 'claude-code'

import type { CiState, UiMode, UiPrefs } from '../../types'
import { analyze } from '../lib/commands'
import { applyTodo, gitState, parsePr, parseRuns } from '../lib/deck'
import { ciLine, usageToasts } from '../lib/deckviews'
import { clip } from '../lib/format'
import { join } from '../lib/paths'
import { noteError, rt, ui } from '../lib/runtime'
import { PANE_ID, PREFS_KEY } from '../lib/specs'

const DECK = { plugin: 'mercy', key: 'deck' } as const
const VIEW = { plugin: 'mercy', key: 'view' } as const
const CONTEXT = { plugin: 'mercy', key: 'contextPct' } as const
const COST = { plugin: 'mercy', key: 'costUsd' } as const
const SHELLS = ['Bash', 'mcp__lean-ctx__ctx_shell', 'mcp__lean-ctx__shell']
const TODO_TOOLS = ['TodoWrite', 'TaskCreate', 'TaskUpdate']
const GIT_CHANGE = /\bgit\s+(?:-c\s+\S+\s+)*(?:commit|checkout|switch|merge|rebase|pull|reset|stash|add|restore|push|cherry-pick|revert|fetch)\b/
const MODES: readonly UiMode[] = ['full', 'focus', 'quiet', 'off']

let ciOn = false
let githubRemote = false
let gitTimer: Timer | undefined
const verifyLast = new Map<string, boolean>()

function toast($: EngineInterface, text: string, failure: boolean, timeoutMs = 6000): void {
  const t = ui().toasts
  if (t === 'all' || (t === 'failures' && failure)) $.ui.toast(text, { timeoutMs })
}

async function publish($: EngineInterface): Promise<void> {
  await $.state.set(DECK, rt.deck)
}

async function refreshGit($: EngineInterface): Promise<void> {
  const root = rt.repoRoot
  if (!root) return
  const git = (argv: string[]): Promise<string> =>
    // read-only polling: never take index.lock from under the user's own git commands
    $.process.run(['git', '--no-optional-locks', '-c', 'safe.directory=*', ...argv], { cwd: root, timeoutMs: 4000 }).then(r => (r.exitCode === 0 ? r.stdout : ''), () => '')
  const [status, numstat, log] = await Promise.all([
    git(['status', '--porcelain=v2', '--branch']),
    git(['diff', '--numstat', 'HEAD']),
    git(['log', '-5', '--format=%h%x1f%s%x1f%ct']),
  ])
  if (!status) return
  const before = rt.deck.git?.head
  rt.deck.git = gitState(status, numstat, log, await $.clock.now())
  rt.branch = rt.deck.git.branch
  await publish($)
  // HEAD moved (a commit, pull or checkout, here or in the user's own terminal): refresh the indexes
  if (before && rt.deck.git.head && before !== rt.deck.git.head && rt.hooksDir) {
    const argv = [...rt.python, join(rt.hooksDir, 'index-lifecycle.py'), 'reprobe', '--root', root]
    $.clock.after(0, () => void $.process.run(argv, { cwd: root, timeoutMs: 15_000 }).catch(err => noteError('index reprobe', err)))
  }
}

/** Debounced: a burst of writes (parallel subagents) costs one refresh, not one per write. */
function gitSoon($: EngineInterface, ms = 2500): void {
  gitTimer?.cancel()
  gitTimer = $.clock.after(ms, () => void refreshGit($).catch(err => noteError('git refresh', err)))
}

async function refreshCi($: EngineInterface): Promise<CiState | undefined> {
  const root = rt.repoRoot
  if (!ciOn || !root) return rt.deck.ci
  const now = await $.clock.now()
  const fail = (error: string): CiState => ({ source: 'error', overall: 'none', checks: [], error: clip(error, 160), at: now })
  let next: CiState
  try {
    const pr = await $.process.run(['gh', 'pr', 'view', '--json', 'number,title,state,url,isDraft,reviewDecision,statusCheckRollup'], { cwd: root, timeoutMs: 20000 })
    if (pr.exitCode === 0) next = parsePr(pr.stdout, now)
    else if (/no (open )?pull requests? found/i.test(pr.stderr)) {
      const runs = await $.process.run(['gh', 'run', 'list', '--branch', rt.branch ?? 'HEAD', '-L', '8', '--json', 'workflowName,status,conclusion,url'], { cwd: root, timeoutMs: 20000 })
      next = runs.exitCode === 0 ? parseRuns(runs.stdout, now) : fail(runs.stderr.trim() || `gh exited ${runs.exitCode}`)
    } else next = fail(pr.stderr.trim() || `gh exited ${pr.exitCode}`)
  } catch (err) {
    // a rejection is a missing binary or a timeout: only a missing gh stops the polling
    const present = await $.process.run(['gh', '--version'], { timeoutMs: 5000 }).then(() => true, () => false)
    if (!present) ciOn = false
    next = fail(`${present ? 'gh timed out' : 'gh is not installed'}: ${err instanceof Error ? err.message : String(err)}`)
  }
  const prev = rt.deck.ci
  rt.deck.ci = next
  await publish($)
  if (prev && prev.overall !== next.overall && (next.overall === 'pass' || next.overall === 'fail')) {
    toast($, `${next.overall === 'fail' ? '✗ CI failing' : '✓ CI passed'}: ${ciLine(next)}`, next.overall === 'fail', 10000)
  }
  return next
}

function ciSoon($: EngineInterface, ms: number): void {
  $.clock.after(ms, () => void refreshCi($).catch(err => noteError('ci refresh', err)))
}

async function setPrefs($: EngineInterface, patch: UiPrefs): Promise<void> {
  rt.deck.prefs = { ...rt.deck.prefs, ...patch }
  await $.store.set(PREFS_KEY, rt.deck.prefs)
  await publish($)
  $.ui.invalidate('ui.render')
}

function prefsLine(): string {
  const f = ui()
  const on = (b: boolean): string => (b ? 'on' : 'off')
  return `mercy ui: ${rt.deck.prefs.mode ?? rt.options.pulse} · sound ${on(f.sound)} · notify ${on(f.notify)} · auto pane ${on(f.paneAuto)} · toasts ${f.toasts}`
}

export function registerDeck(on: On): void {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    try {
      const stored = (await $.store.get(PREFS_KEY)) as UiPrefs | undefined
      rt.deck.prefs = stored && typeof stored === 'object' ? stored : {}
      const held = (await $.state.get(DECK)).value
      // a hot reload keeps this session's deck (todos, turns); another session starts clean
      rt.deck = held && held.sessionId === rt.sessionId ? { ...held, prefs: rt.deck.prefs } : { todos: [], turns: [], limits: [], prefs: rt.deck.prefs, sessionId: rt.sessionId }
      githubRemote = /github\.com/.test((await $.session.repo())?.remote ?? '')
      ciOn = rt.options.ci === 'on' && githubRemote
      gitSoon($, 0)
      $.clock.every(60_000, () => void refreshGit($).catch(err => noteError('git refresh', err)))
      if (ciOn) {
        ciSoon($, 1000)
        $.clock.every(180_000, () => void refreshCi($).catch(err => noteError('ci refresh', err)))
      }
      if (ui().paneAuto) void $.ui.open({ id: PANE_ID, title: 'mercy pulse' })
    } catch (err) {
      noteError('deck start', err)
    }
    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    const r = await next(e)
    try {
      const prevCtx = rt.contextPct
      const prevLimits = rt.deck.limits
      rt.contextPct = e.context.percent ?? rt.contextPct
      if (e.cost) rt.costUsd = e.cost.usd
      rt.deck.limits = e.rateLimits.map(l => ({ kind: l.kind, percent: l.percentUsed, resetsAt: l.resetsAt }))
      await $.state.set(CONTEXT, rt.contextPct)
      await $.state.set(COST, rt.costUsd)
      await publish($)
      for (const line of usageToasts(prevCtx, rt.contextPct, prevLimits, rt.deck.limits)) toast($, `mercy: ${line}`, true, 8000)
    } catch (err) {
      noteError('session.measure', err)
    }
    return r
  })

  on('tool.call', { tool: /^(?:Bash|mcp__lean-ctx__(?:ctx_)?shell|TodoWrite|TaskCreate|TaskUpdate|Write|Edit|MultiEdit|NotebookEdit)$/ }, async ($, e, next) => {
    const r = await next(e)
    try {
      if (r.deny !== undefined) return r
      const input = e as unknown as Record<string, unknown>
      if (TODO_TOOLS.includes(e.tool)) {
        if (e.agentId === undefined && r.isError !== true) {
          rt.deck.todos = applyTodo(rt.deck.todos, e.tool, input, r.result)
          await publish($)
        }
      } else if (SHELLS.includes(e.tool)) {
        const command = typeof input['command'] === 'string' ? input['command'] : ''
        if (GIT_CHANGE.test(command)) gitSoon($)
        if (/\bgit\s+push\b/.test(command) && r.isError !== true) ciSoon($, 20_000)
        if (input['run_in_background'] !== true) {
          for (const kind of analyze(command).verify) {
            const ok = r.isError !== true
            const before = verifyLast.get(kind)
            verifyLast.set(kind, ok)
            if (before === undefined ? !ok : before !== ok) toast($, ok ? `✓ ${kind} passing again` : `✗ ${kind} failed: ${clip(command, 60)}`, !ok, 7000)
          }
        }
      } else if (r.isError !== true) gitSoon($)
    } catch (err) {
      noteError('deck tool.call', err)
    }
    return r
  })

  // a pane tab or its refresh button (the plugin's own state writes skip its own state.set
  // hooks, a press does not): reload what that view shows, when stale or asked
  on('ui.press', { requestId: PANE_ID }, async ($, e, next) => {
    const r = await next(e)
    try {
      const force = e.element === 'refresh'
      const view = force ? (await $.state.get(VIEW)).value : e.element.replace(/^tab-/, '')
      const now = await $.clock.now()
      if (view === 'git' && (force || now - (rt.deck.git?.at ?? 0) > 5000)) gitSoon($, 0)
      if (view === 'ci' && (force || now - (rt.deck.ci?.at ?? 0) > 30_000)) ciSoon($, 0)
    } catch (err) {
      noteError('deck refresh', err)
    }
    return r
  })

  on('command.run', { command: 'ci' }, async $ => {
    if (rt.options.ci === 'off') return { text: 'CI watch is off (userConfig ci: off).' }
    if (!githubRemote) return { text: 'CI watch needs a GitHub remote; this repo has none.' }
    ciOn = true // re-arm after a missing gh was installed, or an auth fix

    const ci = await refreshCi($)
    await $.state.set(VIEW, 'ci')
    await $.ui.open({ id: PANE_ID, title: 'mercy pulse' })
    return { text: `CI: ${ciLine(ci)}` }
  })

  on('command.run', { command: 'ui' }, async ($, e) => {
    const [a, b] = e.args.trim().toLowerCase().split(/\s+/)
    if (a && (MODES as readonly string[]).includes(a)) {
      await setPrefs($, { mode: a as UiMode })
      if (a === 'off') $.ui.status(undefined)
    } else if ((a === 'sound' || a === 'notify' || a === 'pane') && (b === 'on' || b === 'off')) {
      await setPrefs($, { [a]: b === 'on' })
    } else if (a === 'reset') {
      rt.deck.prefs = {}
      await setPrefs($, {})
    } else if (a) {
      return { text: 'usage: /ui [full|focus|quiet|off] | /ui sound|notify|pane on|off | /ui reset' }
    }
    return { text: prefsLine() }
  })
}
