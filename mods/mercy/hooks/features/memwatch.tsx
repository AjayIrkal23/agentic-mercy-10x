// The memory guard's face: polls state/mem-pressure.json (hooks/tools/memwatch.py writes it
// every 5 s) every 15 s, keeps it in the deck for the band, the pane's memory tab and the
// status line, and toasts once per tier change in this pane. Desktop notifications are
// memwatch.py's (one per machine); the flag state/mercy-mod.active.d/<sid>.json only tells
// Python a mod is live for this session. UI only: tiers, kills and restores live in systemd + Python.
// Inert on Windows (no memwatch there) and headless.

import type { EngineInterface, On } from 'claude-code'

import type { MemLevel } from '../../types'
import { gb } from '../lib/deckviews'
import { statePathFrom } from '../lib/paths'
import { parseMemPressure } from '../lib/probes'
import { keepTimer, noteError, rt, ui } from '../lib/runtime'
import { PANE_ID } from '../lib/specs'

const DECK = { plugin: 'mercy', key: 'deck' } as const
const POLL_MS = 15_000

let lastTier: MemLevel | undefined

async function refresh($: EngineInterface, announce: boolean): Promise<void> {
  if (rt.windows || !rt.interactive || !rt.hooksDir) return
  const text = await $.fs.read(statePathFrom(rt.hooksDir, 'mem-pressure.json')).catch(() => undefined)
  const now = await $.clock.now()
  const mem = text === undefined ? undefined : parseMemPressure(text, now)
  if (text !== undefined && mem === undefined) return // corrupt or torn write: keep the last good state
  rt.deck.mem = mem
  await $.state.set(DECK, rt.deck)
  const tier: MemLevel = mem?.level ?? 'ok'
  if (announce && lastTier !== undefined && tier !== lastTier) {
    const free = mem?.memAvailableMb !== undefined ? ` — ${gb(mem.memAvailableMb)} free, swap ${Math.round(mem.swapFreePct ?? 100)}% free` : ''
    const line = `mercy: memory ${tier}${free}${tier === 'crit' ? '; stop fan-out, let the guard shed' : ''}`
    const t = ui().toasts
    if (t === 'all' || (t === 'failures' && tier === 'crit')) $.ui.toast(line, { timeoutMs: tier === 'crit' ? 12_000 : 6_000 })
  }
  lastTier = tier
}

export function registerMemwatch(on: On): void {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    try {
      lastTier = undefined
      await refresh($, false)
      if (!rt.windows) keepTimer('memwatch', $.clock.every(POLL_MS, () => void refresh($, true).catch(err => noteError('memwatch', err))))
    } catch (err) {
      noteError('memwatch start', err)
    }
    return next(e)
  })

  on('ui.press', { requestId: PANE_ID }, async ($, e, next) => {
    const r = await next(e)
    if (e.element === 'tab-memory' || e.element === 'refresh') await refresh($, false).catch(err => noteError('memwatch', err))
    return r
  })
}
