// The end of a turn: drain the background hook lane so the Python Stop gates read
// complete evidence, let them decide first, then the verification gate (evidence before
// "done"), then deliver advisories that arrived after the last tool call.

import type { On } from 'claude-code'

import { bestVerifyCommand, verifyDecision } from '../lib/guard'
import { recordBlock } from '../lib/ledger'
import { busy, idle } from '../lib/queue'
import { noteError, rt, takePending, ui } from '../lib/runtime'

const LEDGER = { plugin: 'mercy', key: 'ledger' } as const

export function registerStop(on: On): void {
  on('classic.Stop', async ($, e, next) => {
    try {
      if (busy('fast')) await Promise.race([idle('fast'), $.clock.sleep(6000, { signal: next.signal })])
    } catch (err) {
      noteError('stop drain', err)
    }
    const r = await next(e)
    try {
      const now = await $.clock.now()
      // one Stop block per human turn across the Python gates and mercy (B2-06)
      const blocked = rt.blockedHumanTurn === rt.humanTurn
      if (r.block) {
        rt.blockedHumanTurn = rt.humanTurn
        recordBlock(rt.ledger, { at: now, source: 'python', reason: r.block.slice(0, 300) })
        await $.state.set(LEDGER, rt.ledger)
        return r
      }
      const backgroundBusy = (e.background_tasks ?? []).some(t => /running|pending/i.test(t.status))
      const decision = verifyDecision(rt.ledger, {
        mode: rt.options.verifyGate,
        stopHookActive: e.stop_hook_active,
        backgroundBusy,
        alreadyBlockedThisTurn: blocked,
        command: bestVerifyCommand(rt.ledger, rt.brain?.commands),
        consent: rt.consent,
      })
      if (decision?.kind === 'block') {
        rt.blockedHumanTurn = rt.humanTurn
        recordBlock(rt.ledger, { at: now, source: 'mercy', reason: decision.text.slice(0, 300) })
        await $.state.set(LEDGER, rt.ledger)
        return { ...r, block: decision.text }
      }
      if (decision?.kind === 'advise' && ui().toasts !== 'none') $.ui.toast(decision.text, { timeoutMs: 8000 })
      // past the budget (or told to stop) the advisories wait for the next prompt instead
      if (e.stop_hook_active || blocked || rt.consent) return r
      // takePending drops a tdd-guard advisory whose file passed a test after the edit: no extra turn for it
      const pending = rt.pending.length ? takePending() : []
      if (pending.length) {
        rt.blockedHumanTurn = rt.humanTurn
        return {
          ...r,
          block: `mercy: hook advisories finished after your last tool call:\n\n${pending.join('\n\n')}\n\nAct on any that apply to this turn's work; if none do, finish.`,
        }
      }
    } catch (err) {
      noteError('stop', err)
    }
    return r
  })
}
