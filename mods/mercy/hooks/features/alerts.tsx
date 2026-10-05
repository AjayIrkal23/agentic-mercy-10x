// Alerts: what reaches you when you are not looking. A long turn's end plays the desktop
// "complete" sound, toasts and (past notifyAfter) sends a desktop notification with the
// answer's first line; an error turn plays "dialog-error"; a question or permission wait
// plays "message-new-instant". Quiet hours, the UI mode and a 3 s throttle apply. `/sound`.

import type { EngineInterface, On } from 'claude-code'

import type { SoundKind } from '../lib/deck'
import { inQuietHours, playerArgvs, shouldSound } from '../lib/deck'
import { clip, duration } from '../lib/format'
import { hostOffsetMinutes, noteError, rt, ui } from '../lib/runtime'
import { PREFS_KEY } from '../lib/specs'

const DECK = { plugin: 'mercy', key: 'deck' } as const
const WAITING = /^(?:permission_prompt|elicitation_dialog|agent_needs_input)$/

let player: number | undefined
const asked = new Set<string>()

function quietNow(now: number): boolean {
  const minute = (((Math.floor(now / 60_000) + hostOffsetMinutes()) % 1440) + 1440) % 1440
  return inQuietHours(rt.options.quietHours, minute)
}

/** Tries the players in order (the last one that worked first); a missing binary rejects and the next is tried. */
async function sound($: EngineInterface, kind: SoundKind): Promise<string | undefined> {
  const argvs = playerArgvs(kind)
  const order = player === undefined ? argvs.map((_, i) => i) : [player, ...argvs.map((_, i) => i).filter(i => i !== player)]
  for (const i of order) {
    try {
      const r = await $.process.run(argvs[i] ?? [], { timeoutMs: 8000 })
      if (r.exitCode === 0) {
        player = i
        return argvs[i]?.[0]
      }
    } catch {
      // not installed here: try the next player
    }
  }
  return undefined
}

async function play($: EngineInterface, kind: SoundKind, turnMs?: number): Promise<void> {
  const now = await $.clock.now()
  if (!shouldSound(kind, ui(), { now, lastAt: rt.lastSoundAt, quiet: quietNow(now), afterMs: rt.options.soundAfter * 1000, turnMs })) return
  rt.lastSoundAt = now
  $.clock.after(0, () => void sound($, kind))
}

async function notify($: EngineInterface, title: string, body: string, urgency: 'normal' | 'critical'): Promise<void> {
  if (!ui().notify || quietNow(await $.clock.now())) return
  // `--`: a title or body starting with `-` is text, never an option
  const argv = ['notify-send', '-a', 'Claude Code', '-i', 'utilities-terminal', '-u', urgency, '-t', '10000', '--', title, clip(body, 240)]
  $.clock.after(0, () => void $.process.run(argv, { timeoutMs: 5000 }).catch(() => undefined))
}

function firstLine(text: string): string {
  return text.split('\n').map(l => l.replace(/^[#>*\-\s]+/, '').trim()).find(Boolean) ?? ''
}

export function registerAlerts(on: On): void {
  on('turn.complete', { isAborted: false }, async ($, e, next) => {
    const r = await next(e)
    try {
      const f = ui()
      if (e.agentId !== undefined) {
        const run = rt.ledger.agents.find(a => a.id === e.agentId)
        if (run && f.toasts === 'all') $.ui.toast(`⚙ ${run.type} finished in ${duration(e.durationMs)}${run.description ? `: ${clip(run.description, 50)}` : ''}`, { timeoutMs: 5000 })
        return r
      }
      const now = await $.clock.now()
      // read now: session.measure may land after turn.complete, and the plain call is free
      const cost = (await $.session.usage().catch(() => undefined))?.cost?.usd ?? rt.costUsd
      rt.deck.turns = [...rt.deck.turns, {
        at: now, ms: e.durationMs, input: (e.usage?.input_tokens ?? 0) + (e.usage?.cache_read_input_tokens ?? 0), output: e.usage?.output_tokens ?? 0,
        costUsd: Math.max(0, cost - rt.turnCostBase), ctxPct: rt.contextPct,
      }].slice(-60)
      rt.turnCostBase = cost
      await $.state.set(DECK, rt.deck)
      if (e.reason === 'error') {
        if (f.toasts !== 'none') $.ui.toast('✗ the turn ended with an error', { timeoutMs: 8000 })
        await play($, 'error')
        await notify($, 'Claude Code: the turn failed', firstLine(e.answer) || 'API error', 'critical')
      } else if (e.reason === 'answer') {
        const long = e.durationMs >= rt.options.soundAfter * 1000
        const edited = Object.keys(rt.ledger.turnEdits).length
        if (long && f.toasts === 'all') $.ui.toast(`✓ done in ${duration(e.durationMs)}${edited ? ` · ${edited} file${edited > 1 ? 's' : ''} edited` : ''}`, { timeoutMs: 6000 })
        await play($, 'done', e.durationMs)
        if (e.durationMs >= rt.options.notifyAfter * 1000) await notify($, `Claude Code finished in ${duration(e.durationMs)}`, firstLine(e.answer), 'normal')
      }
    } catch (err) {
      noteError('alerts turn.complete', err)
    }
    return r
  })

  on('classic.Notification', async ($, e, next) => {
    const r = await next(e)
    try {
      if (WAITING.test(e.notification_type)) {
        await play($, 'input')
        await notify($, e.title || 'Claude Code needs you', e.message, 'critical')
      }
    } catch (err) {
      noteError('alerts notification', err)
    }
    return r
  })

  // the model asked a question: once per dialog
  on('ui.render', { component: 'AskUserQuestion' }, async ($, e, next) => {
    if (!asked.has(e.requestId)) {
      asked.add(e.requestId)
      await play($, 'input')
    }
    return next(e)
  })

  on('command.run', { command: 'sound' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    if (arg === 'on' || arg === 'off') {
      rt.deck.prefs = { ...rt.deck.prefs, sound: arg === 'on' }
      await $.store.set(PREFS_KEY, rt.deck.prefs)
      await $.state.set(DECK, rt.deck)
      return { text: `mercy sound ${arg}` }
    }
    if (arg && arg !== 'test') return { text: 'usage: /sound [test|on|off]' }
    const used = await sound($, 'done')
    $.clock.after(1500, () => void sound($, 'input'))
    $.clock.after(3000, () => void sound($, 'error'))
    const state = ui().sound ? 'on' : 'off (mode or /ui sound off)'
    return { text: used ? `mercy sound test: done, input, error via ${used}; alerts are ${state}` : 'mercy sound: no player worked (tried canberra-gtk-play, pw-play, paplay, afplay)' }
  })
}
