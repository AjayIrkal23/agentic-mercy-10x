// The Python bridge. dispatch.py stays the truth for every gate; for the links the mod
// owns (MERCY_MOD_OWNED, set at session.start), the mod decides WHEN they run:
// synchronously only when they can fire, or in the background off the critical path,
// their advisories delivered on the next tool result or prompt.

import type { EngineInterface, On } from 'claude-code'

import type { BridgeEvent, HookOutput, PlanFacts } from '../lib/bridgeplan'
import { dispatchArgv, parseHookOutput, planFor, prePayload } from '../lib/bridgeplan'
import { recordHook } from '../lib/ledger'
import { dirname, join, targetPath, WRITE_TOOLS } from '../lib/paths'
import type { Lane } from '../lib/queue'
import { busy, done, enqueue, idle, size, take } from '../lib/queue'
import { noteError, rt } from '../lib/runtime'

const BRIDGE = { plugin: 'mercy', key: 'bridge' } as const
const FAIL_LIMIT = 3
let failures = 0

type RunResult = { ok: boolean; out: HookOutput; ms: number }

async function runDispatch($: EngineInterface, event: BridgeEvent, ids: readonly string[], payload: string): Promise<RunResult> {
  const t0 = await $.clock.now()
  const r = await $.process.run(dispatchArgv(rt.python, rt.hooksDir, event, ids), {
    stdin: payload,
    timeoutMs: 25_000,
    env: { CLAUDE_PROJECT_DIR: await $.session.root() },
  })
  return { ok: r.exitCode === 0, out: parseHookOutput(r.stdout), ms: (await $.clock.now()) - t0 }
}

/** Writes the owned set where dispatch.py reads it (`_mod_owned`): an id gone from MERCY_MOD_OWNED runs in Python. */
async function publish($: EngineInterface): Promise<void> {
  const owned = rt.bridge.owned
  await $.env.set('MERCY_MOD_OWNED', owned.length ? owned.join(',') : undefined)
  await $.env.set('MERCY_MOD_SESSION', owned.length ? rt.sessionId : undefined)
  await $.env.set('MERCY_MOD_BEAT', owned.length ? String(await $.clock.now()) : undefined)
  await $.state.set(BRIDGE, rt.bridge)
}

/**
 * The one release (H-12): every link back to Python. Queued runs still run: they belong
 * to calls Python already skipped (H-11). `why` undefined = `/mercy release` by hand.
 */
async function release($: EngineInterface, why: string | undefined): Promise<number> {
  const had = rt.bridge.owned.length
  rt.bridge.owned = []
  rt.bridge.lastError = why
  failures = 0
  await publish($)
  if (why && had) $.ui.toast('mercy bridge: hook runs through the bridge kept failing — every link is back on the Python chain', { timeoutMs: 10000 })
  return had
}

/**
 * B1-06: links the mod did not run for this call. Set before `next(e)`, so the Python
 * chain beneath runs them now (`_mod_owned` drops them for this tool_use_id only;
 * the value goes stale with the next call). Ownership stays.
 */
async function failedFor($: EngineInterface, toolUseId: string, ids: readonly string[]): Promise<void> {
  if (ids.length) await $.env.set('MERCY_MOD_FAILED', `${toolUseId}:${ids.join(',')}`)
}

/**
 * One dispatch run, counted. A failed sync run (`toolUseId` given) goes to Python for this
 * call; FAIL_LIMIT failures in a row release everything.
 */
async function attempt($: EngineInterface, event: BridgeEvent, ids: readonly string[], payload: string, toolUseId?: string): Promise<RunResult | undefined> {
  const what = ids.join(',')
  let r: RunResult | undefined
  try {
    r = await runDispatch($, event, ids, payload)
  } catch (err) {
    noteError(`bridge ${what}`, err)
  }
  if (r?.ok) {
    failures = 0
    return r
  }
  failures += 1
  rt.bridge.failed += 1
  const why = r ? `${what} exited non-zero` : `${what} did not run`
  rt.bridge.lastError = why
  if (toolUseId !== undefined) await failedFor($, toolUseId, ids)
  if (failures >= FAIL_LIMIT && rt.bridge.owned.length) await release($, why)
  return r
}

async function pump($: EngineInterface, lane: Lane): Promise<void> {
  for (let job = take(lane); job; job = take(lane)) {
    try {
      const r = await attempt($, job.event, job.ids, job.payload)
      if (r) {
        rt.bridge.ran += 1
        rt.bridge.savedMs += r.ms
        // pending advisories surface on the main loop's next tool result: a subagent's would land
        // in the parent, about files it never wrote (NEW-08); the run's state writes still count
        const context = job.agentId === undefined ? r.out.context : undefined
        if (context) rt.pending.push(context)
        if (context && lane === 'slow') rt.pendingFiles.set(context, job.key)
      }
    } finally {
      done(lane)
    }
  }
  rt.bridge.queued = size()
  await $.state.set(BRIDGE, rt.bridge)
}

/** Waits for the fast lane (and the slow one before a write: its tdd-guard advisory rides this call, B1-22), at most 4 s. */
async function drain($: EngineInterface, signal: AbortSignal, write: boolean): Promise<void> {
  const lanes: Lane[] = write ? ['fast', 'slow'] : ['fast']
  if (!lanes.some(busy)) return
  await Promise.race([Promise.all(lanes.map(idle)), $.clock.sleep(4000, { signal })])
}

/** Whether the git root above `path` already has a CLAUDE.md (undefined outside a repo). */
async function rootHasClaudeMd($: EngineInterface, path: string): Promise<boolean | undefined> {
  let dir = dirname(path)
  for (let depth = 0; depth < 30 && dir; depth++) {
    const known = rt.claudeMdRoots.get(dir)
    if (known !== undefined) return known
    if (await $.fs.exists(join(dir, '.git'))) {
      const has = await $.fs.exists(join(dir, 'CLAUDE.md'))
      rt.claudeMdRoots.set(dir, has)
      return has
    }
    dir = dirname(dir)
  }
  return undefined
}

function argsOf(env: Record<string, unknown>): Record<string, unknown> {
  const { tool: _tool, tool_use_id: _id, ...input } = env
  return input
}

export function registerBridge(on: On): void {
  on('classic.PreToolUse', async ($, e, next) => {
    const t0 = await $.clock.now()
    const extra: string[] = []
    let ask: string | undefined
    let later: { ids: string[]; payload: string; key: string } | undefined
    try {
      if (rt.bridge.owned.length) await $.env.set('MERCY_MOD_BEAT', String(t0))
      await drain($, next.signal, WRITE_TOOLS.has(e.tool))
      if (rt.dispatch && rt.bridge.owned.length) {
        const input = argsOf(e as unknown as Record<string, unknown>)
        const path = WRITE_TOOLS.has(e.tool) ? targetPath(input) : undefined
        const facts: PlanFacts = {
          tool: e.tool,
          input,
          jcodemunchUsed: (rt.ledger.mcp['jcodemunch'] ?? 0) > 0,
          rootHasClaudeMd: path ? await rootHasClaudeMd($, path) : undefined,
        }
        const plan = planFor(rt.dispatch, rt.bridge.owned, 'pre-tool-use', facts, rt.options.tddGuard)
        // classic.PreToolUse carries no cwd: read the live one (a shell `cd` moves it)
        const base = { sessionId: rt.sessionId, transcriptPath: rt.transcriptPath, cwd: await $.session.cwd() }
        const payload = prePayload(e as unknown as Record<string, unknown>, base)
        if (plan.sync.length) {
          const r = await attempt($, 'pre-tool-use', plan.sync, payload, e.tool_use_id)
          if (r?.out.decision === 'deny') return { deny: r.out.reason || 'Blocked by a hook gate.' }
          if (r?.out.decision === 'ask') ask = r.out.reason || 'A hook gate asks for confirmation.'
          if (r?.out.context) extra.push(r.out.context)
        }
        later = { ids: plan.async, payload, key: path ?? e.tool_use_id }
      }
    } catch (err) {
      noteError('bridge pre', err)
      // B1-06: planning broke, so no owned link ran or queued for this call; Python runs them instead
      later = undefined
      await failedFor($, e.tool_use_id, rt.bridge.owned).catch(() => undefined)
    }
    // an owned gate's ask still lets the rest of the Python chain run; a deny there wins
    const r = await next(e)
    recordHook(rt.ledger, `PreToolUse ${e.tool}`, (await $.clock.now()) - t0)
    // H-07: background links only for a call that will run (a failed sync run may also have released them)
    const queue = later && r.deny === undefined ? later.ids.filter(id => rt.bridge.owned.includes(id)) : []
    for (const lane of ['slow', 'fast'] as const) {
      const ids = queue.filter(id => (id === 'tdd-guard-launcher-pre') === (lane === 'slow'))
      if (!ids.length || !later) continue
      const agentId = rt.subagentCalls.has(e.tool_use_id) ? 'subagent' : undefined
      enqueue({ lane, event: 'pre-tool-use', ids, payload: later.payload, key: lane === 'slow' ? later.key : e.tool_use_id, queuedAt: t0, agentId })
      void pump($, lane)
    }
    const context = [...(r.additionalContext ?? []), ...extra]
    if (ask !== undefined && r.deny === undefined) {
      return { ask: r.ask ? `${ask}\n\n${r.ask}` : ask, updatedInput: r.updatedInput, additionalContext: context }
    }
    return extra.length ? { ...r, additionalContext: context } : r
  })

  on('classic.PostToolUse', async ($, e, next) => {
    const t0 = await $.clock.now()
    const extra: string[] = []
    try {
      if (rt.bridge.owned.length) await $.env.set('MERCY_MOD_BEAT', String(t0))
      if (e.transcript_path) rt.transcriptPath = e.transcript_path
      await drain($, next.signal, false)
      if (rt.dispatch && rt.bridge.owned.length) {
        const input = (e.tool_input && typeof e.tool_input === 'object' ? e.tool_input : {}) as Record<string, unknown>
        const facts: PlanFacts = { tool: e.tool_name, input, jcodemunchUsed: (rt.ledger.mcp['jcodemunch'] ?? 0) > 0, rootHasClaudeMd: undefined }
        const plan = planFor(rt.dispatch, rt.bridge.owned, 'post-tool-use', facts, rt.options.tddGuard)
        const payload = JSON.stringify(e)
        if (plan.sync.length) {
          const r = await attempt($, 'post-tool-use', plan.sync, payload, e.tool_use_id)
          if (r?.out.context) extra.push(r.out.context)
        }
        const queue = plan.async.filter(id => rt.bridge.owned.includes(id))
        if (queue.length) {
          enqueue({ lane: 'fast', event: 'post-tool-use', ids: queue, payload, key: e.tool_use_id, queuedAt: t0, agentId: e.agent_id })
          void pump($, 'fast')
        }
      }
    } catch (err) {
      noteError('bridge post', err)
      // B1-06: nothing owned ran or queued for this call (enqueue is the try's last step); Python runs them
      await failedFor($, e.tool_use_id, rt.bridge.owned).catch(() => undefined)
    }
    const r = await next(e)
    recordHook(rt.ledger, `PostToolUse ${e.tool_name}`, (await $.clock.now()) - t0)
    return extra.length ? { ...r, additionalContext: [...(r.additionalContext ?? []), ...extra] } : r
  })

  // `/mercy release` lives here so there is one release (H-12); every other /mercy arg goes on to pulse
  on('command.run', { command: 'mercy' }, async ($, e, next) => {
    if ((e.args.trim().split(/\s+/)[0] ?? '') !== 'release') return next(e)
    const had = await release($, undefined)
    return { text: had ? `Released ${had} hook links: dispatch.py runs every link again for this session.` : 'The bridge owned no links.' }
  })
}
