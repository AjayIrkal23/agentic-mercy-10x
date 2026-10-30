// Session lifecycle: one-time init, turn bookkeeping, usage and context, the repo brain's
// persistence, resets on /clear and compaction, and auto-resume after a usage-limit stop.

import type { EngineInterface, On } from 'claude-code'

import type { Ledger, RepoFacts } from '../../types'
import { applyMarkers, emptyFacts, learnCommands, learnFixes, MARKERS, mergeFacts, storeKey } from '../lib/brain'
import { ownedLinks } from '../lib/bridgeplan'
import { parseConfig } from '../lib/dispatch'
import { duration } from '../lib/format'
import { hiddenFrom, hooksDirFrom, pythonFrom } from '../lib/hostconfig'
import { addUsage, beginTurn, emptyLedger, recordAgentEnd } from '../lib/ledger'
import { join, statePathFrom } from '../lib/paths'
import { defaultPython, isWindowsEnv } from '../lib/os'
import { busy, idle } from '../lib/queue'
import { clockLabel, RESUME_PROMPT, resumeAt } from '../lib/resume'
import { decideResumeLock, flagBody, lockBody } from '../lib/resumelock'
import { dropResume, dropTimers, featureHealth, hostOffsetMinutes, keepTimer, noteError, resumeKey, rt, ui, withErrors } from '../lib/runtime'
import { snapshot } from '../lib/snap'
import { COMMAND_SPECS, TOOL_SPECS } from '../lib/specs'
import { isScratchRoot, sweepStore } from '../lib/storekeys'
import { statusText } from '../lib/views'

const LEDGER = { plugin: 'mercy', key: 'ledger' } as const
const BRAIN = { plugin: 'mercy', key: 'brain' } as const
const BRIDGE = { plugin: 'mercy', key: 'bridge' } as const
const HEALTH = { plugin: 'mercy', key: 'health' } as const
const DECK = { plugin: 'mercy', key: 'deck' } as const
const MAX_RESUMES = 12

function copy(f: RepoFacts): RepoFacts {
  return JSON.parse(JSON.stringify(f)) as RepoFacts
}

async function claimLinks($: EngineInterface): Promise<void> {
  const armed = Boolean((await $.env.get('BASH_WRITE_GATE_DENY_SHELL_WRITES')) || (await $.env.get('BASH_WRITE_GATE_HARD_BLOCK')))
  const owned = rt.options.bridge === 'on' && rt.dispatch ? ownedLinks(rt.dispatch, { tddGuard: rt.options.tddGuard, bashWriteDenyArmed: armed }) : []
  rt.bridge.owned = owned
  await $.env.set('MERCY_MOD_OWNED', owned.length ? owned.join(',') : undefined)
  await $.env.set('MERCY_MOD_SESSION', owned.length ? rt.sessionId : undefined)
  await $.env.set('MERCY_MOD_BEAT', owned.length ? String(await $.clock.now()) : undefined)
  await $.state.set(BRIDGE, rt.bridge)
}

/** Writes the brain merged over what other sessions stored since this one read it (H-08). */
async function saveBrain($: EngineInterface): Promise<void> {
  if (!rt.brain || !rt.repoRoot) return
  const key = storeKey(rt.repoRoot)
  const merged = mergeFacts((await $.store.get(key)) as RepoFacts | undefined, rt.brainBase, rt.brain)
  await $.store.set(key, merged)
  rt.brain = merged
  rt.brainBase = copy(merged)
  await $.state.set(BRAIN, rt.brain)
}

async function loadBrain($: EngineInterface, now: number, reload: boolean): Promise<void> {
  // J-10: temp-dir repos (e2e clones, mktemp) are not worth remembering
  if (rt.options.brain !== 'on' || !rt.repoRoot || isScratchRoot(rt.repoRoot)) {
    rt.brain = null
    return
  }
  const stored = (await $.store.get(storeKey(rt.repoRoot))) as RepoFacts | undefined
  const valid = stored && typeof stored === 'object' && typeof stored.root === 'string'
  rt.brainBase = valid ? copy(stored) : null
  const facts = valid ? copy(stored) : emptyFacts(rt.repoRoot, now)
  const present: string[] = []
  for (const [file] of MARKERS) if (await $.fs.exists(join(rt.repoRoot, file))) present.push(file)
  applyMarkers(facts, present)
  if (!reload) {
    facts.sessions += 1
    facts.updatedAt = now
  }
  rt.brainCursor = facts.updatedAt
  rt.brain = facts
  await saveBrain($)
}

function scheduleResume($: EngineInterface, at: number, now: number): void {
  rt.resumeTimer?.cancel()
  rt.resumeAt = at
  rt.resumeTimer = $.clock.after(Math.max(1000, at - now), () => {
    void fireResume($)
  })
}

/**
 * Takes `state/resume-lock/<sid>`, shared with scripts/restore_sessions.py. `$.fs` has no
 * exclusive create, so this is write-then-verify: write our body, wait 250 ms, read it back.
 * Python takes the lock with O_EXCL and only runs when the mod flag is absent, so the race is
 * theoretical. Returns the holder when a fresh foreign lock wins; any fs error → proceed.
 */
async function takeResumeLock($: EngineInterface): Promise<string | undefined> {
  if (!rt.hooksDir || !rt.sessionId) return undefined
  try {
    const path = join(statePathFrom(rt.hooksDir, 'resume-lock'), rt.sessionId)
    const now = await $.clock.now()
    const existing = (await $.fs.exists(path)) ? await $.fs.read(path).catch(() => undefined) : undefined
    const d = decideResumeLock(existing, now)
    if (!d.take) return d.reason.slice('held:'.length)
    const body = lockBody(now)
    await $.fs.write(path, body)
    await $.clock.sleep(250)
    const after = await $.fs.read(path).catch(() => undefined)
    if (after !== undefined && after !== body) {
      const again = decideResumeLock(after, await $.clock.now())
      if (!again.take) return again.reason.slice('held:'.length)
    }
  } catch {
    // fail open: the resume goes ahead as it always did
  }
  return undefined
}

async function fireResume($: EngineInterface): Promise<void> {
  rt.resumeTimer = undefined
  rt.resumeAt = undefined
  rt.resumeAttempts += 1
  await $.store.delete(resumeKey(rt.sessionId))
  const holder = await takeResumeLock($)
  if (holder !== undefined) {
    $.ui.toast(`mercy: auto-resume skipped, resume lock held by ${holder} (restore service is bringing this session back)`, { timeoutMs: 12000 })
    return
  }
  await $.prompt.submit({ text: RESUME_PROMPT })
}

/** `state/mercy-mod.active.d/<sid>.json`, one file per session: while fresh (< 60 s), restore_sessions.py
 * and the compaction nudge leave this session's auto-resume and nudge to the mod, and memwatch.py records
 * that a mod toasts in-pane. `ended` writes ts 0 (stale at once): `$.fs` has no unlink or mkdir, so the
 * Python side creates the directory. Best-effort and silent: a missing state dir is not a hook error. */
async function writeFlag($: EngineInterface, ended = false): Promise<void> {
  if (!rt.hooksDir || !rt.sessionId) return
  try {
    const path = join(statePathFrom(rt.hooksDir, 'mercy-mod.active.d'), rt.sessionId + '.json')
    await $.fs.write(path, flagBody(rt.sessionId, await $.clock.now(), ended))
  } catch {
    // the Python side then keeps notifications and restores, exactly as without the mod
  }
}

/** Drops stale resumes and stale or scratch repo brains; re-arms this session's saved resume (J-10). */
async function sweep($: EngineInterface, now: number): Promise<void> {
  const entries: Array<[string, unknown]> = []
  for (const key of await $.store.keys()) if (key.startsWith('resume') || key.startsWith('repo:')) entries.push([key, await $.store.get(key)])
  const s = sweepStore(entries, { now, resumeKey: resumeKey(rt.sessionId), rearm: rt.options.autoResume === 'on' && rt.interactive })
  for (const key of s.drop) await $.store.delete(key)
  if (s.rearmAt !== undefined) scheduleResume($, s.rearmAt, now)
}

async function init($: EngineInterface, interactive: boolean): Promise<void> {
  const now = await $.clock.now()
  rt.interactive = interactive
  rt.sessionId = await $.session.id()
  rt.repoRoot = (await $.session.repo())?.root
  rt.pluginRoot = $.plugin.root
  rt.hooksDir = hooksDirFrom(rt.pluginRoot)
  rt.windows = isWindowsEnv(await $.env.get('OS'))
  rt.systemRoot = rt.windows ? (await $.env.get('SystemRoot')) || undefined : undefined // system tools by absolute path (SEC1-04)
  rt.python = pythonFrom(await $.settings.read()) ?? defaultPython(rt.windows)
  try {
    rt.dispatch = parseConfig(await $.fs.read(join(rt.hooksDir, 'dispatch.config.json')))
    rt.hiddenSkills = hiddenFrom(await $.fs.read(join(rt.hooksDir, 'skills-index.json')))
  } catch (err) {
    noteError('hook config', err)
  }
  const held = (await $.state.get(LEDGER)).value
  const reload = held !== undefined && held.sessionId === rt.sessionId
  rt.ledger = reload ? (held as Ledger) : emptyLedger(rt.sessionId, now)
  await sweep($, now)
  await loadBrain($, now, reload)
  await $.env.set('MERCY_MOD_LOADED', '1') // Python's "mod off" notice reads it, bridge on or off
  await claimLinks($)
  if (interactive) {
    await writeFlag($)
    keepTimer('mod-flag', $.clock.every(30_000, () => void writeFlag($)))
  }
  for (const spec of TOOL_SPECS) await $.tool.register({ name: spec.name, description: spec.description, inputSchema: JSON.parse(JSON.stringify(spec.inputSchema)) })
  for (const spec of COMMAND_SPECS) await $.command.register({ ...spec }).catch(err => noteError(`/${spec.name}`, err))
  if (rt.repoRoot) {
    const head = await $.process.run(['git', '-c', 'safe.directory=*', 'rev-parse', '--abbrev-ref', 'HEAD'], { cwd: rt.repoRoot, timeoutMs: 3000 })
    rt.branch = head.exitCode === 0 ? head.stdout.trim() : undefined
  }
  rt.health.features = withErrors(rt.health.features, featureHealth(rt.options))
  await $.state.set(HEALTH, rt.health)
  if (ui().status) $.ui.status(statusText(snapshot(now)))
}

export function registerLifecycle(on: On): void {
  on('session.start', async ($, e, next) => {
    try {
      await init($, e.isInteractive)
    } catch (err) {
      noteError('session.start', err)
    }
    return next(e)
  })

  on('classic.SessionStart', async ($, e, next) => {
    const r = await next(e)
    try {
      rt.transcriptPath = e.transcript_path
      if (e.source === 'clear' || e.session_id !== rt.sessionId) {
        // /clear or an in-process /resume: another conversation in this process
        if (dropResume()) await $.store.delete(resumeKey(rt.sessionId))
        if (rt.interactive) await writeFlag($, true) // the old id's flag goes stale at once
        rt.sessionId = e.session_id || (await $.session.id())
        rt.ledger = emptyLedger(rt.sessionId, await $.clock.now())
        rt.governor = { blocks: {}, skills: {} }
        rt.pending = []
        rt.deck = { ...rt.deck, sessionId: rt.sessionId, todos: [], turns: [] }
        await claimLinks($)
        if (rt.interactive) await writeFlag($)
        await $.state.set(LEDGER, rt.ledger)
        await $.state.set(DECK, rt.deck)
      } else if (e.source === 'compact') {
        rt.governor = { blocks: {}, skills: {} }
      }
    } catch (err) {
      noteError('classic.SessionStart', err)
    }
    return r
  })

  on('turn.start', async ($, e, next) => {
    beginTurn(rt.ledger, await $.clock.now())
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    try {
      const now = await $.clock.now()
      if (e.agentId !== undefined) {
        const run = rt.ledger.agents.find(a => a.id === e.agentId)
        if (run) recordAgentEnd(rt.ledger, run.toolUseId, { endedAt: now, ok: e.reason === 'answer', tokens: (run.tokens ?? 0) + (e.usage?.output_tokens ?? 0) })
      } else {
        if (e.reason === 'answer') rt.resumeAttempts = 0
        if (e.reason === 'answer' && dropResume()) await $.store.delete(resumeKey(rt.sessionId))
        if (e.usage) addUsage(rt.ledger, e.usage)
        if (rt.brain && rt.repoRoot) {
          learnCommands(rt.brain, rt.ledger.commands, rt.brainCursor)
          learnFixes(rt.brain, rt.ledger)
          rt.brain.updatedAt = now
          rt.brainCursor = now
          await saveBrain($)
        }
      }
      await $.state.set(LEDGER, rt.ledger)
      await $.state.set(BRIDGE, rt.bridge)
      rt.lastFlush = now
      if (ui().status) $.ui.status(statusText(snapshot(now)))
    } catch (err) {
      noteError('turn.complete', err)
    }
    return r
  })

  on('classic.StopFailure', async ($, e, next) => {
    const r = await next(e)
    try {
      if (rt.options.autoResume === 'on' && rt.interactive && !e.agent_id && rt.resumeAttempts < MAX_RESUMES) {
        const now = await $.clock.now()
        const usage = await $.session.usage()
        const at = resumeAt(now, e.error, usage.rateLimits, e.error_details, hostOffsetMinutes(), rt.resumeAttempts)
        if (at !== undefined) {
          await $.store.set(resumeKey(rt.sessionId), { at, reason: e.error })
          scheduleResume($, at, now)
          $.ui.toast(`mercy: ${e.error === 'rate_limit' ? 'usage limit' : e.error} — auto-resume at ${clockLabel(at, hostOffsetMinutes())} (in ${duration(at - now)})`, { timeoutMs: 12000 })
        }
      }
    } catch (err) {
      noteError('auto-resume', err)
    }
    return r
  })

  on('classic.PreCompact', async ($, e, next) => {
    if (busy('fast')) await Promise.race([idle('fast'), $.clock.sleep(5000, { signal: next.signal })])
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    try {
      // H-11: the last write's post-write runs write state later sessions read; give them up to 3 s
      if (busy('fast')) await Promise.race([idle('fast'), $.clock.sleep(3000, { signal: next.signal })])
      await saveBrain($)
      // /clear and an in-process resume end the conversation, not the process: no session.start
      // follows, so the pollers stay and classic.SessionStart rewrites the flag under the new id
      if (e.reason !== 'clear' && e.reason !== 'resume') {
        dropTimers() // ports, memwatch and mod-flag pollers
        if (rt.interactive) await writeFlag($, true)
      }
    } catch (err) {
      noteError('session.end', err)
    }
    return next(e)
  })
}
