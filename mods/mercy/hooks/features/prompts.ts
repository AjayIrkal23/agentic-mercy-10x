// What the model reads around each prompt: the router governor (dedupe Python router
// output with session knowledge), a live state line, queued advisories, the repo brain's
// stable system section, the focused skill listing, and mercy's own tools up front.

import type { On } from 'claude-code'

import { brainSection } from '../lib/brain'
import { isConsent } from '../lib/consent'
import { prune } from '../lib/dedupe'
import { focusListing } from '../lib/focus'
import { governAll } from '../lib/governor'
import { dropResume, noteError, resumeKey, rt, takePending } from '../lib/runtime'
import { snapshot } from '../lib/snap'
import { stateLine } from '../lib/views'

let brainText: string | undefined
let lastStateLine = ''
// harness "prompts" that no human typed (same list as hooks/lib/turns.py, NEW-10)
const NOT_HUMAN = ['<task-notification>', '[Request interrupted', '<cross-session-message']

export function registerPrompts(on: On): void {
  on('classic.UserPromptSubmit', async ($, e, next) => {
    // a new human turn: the Stop-block budget (one per human turn) and consent start over
    const prompt = (e.prompt ?? '').trimStart()
    if (!NOT_HUMAN.some(p => prompt.startsWith(p))) {
      rt.humanTurn += 1
      rt.consent = isConsent(prompt)
    }
    const r = await next(e)
    try {
      if (rt.options.dedupeWindow <= 0 || !r.additionalContext?.length) return r
      const turn = rt.ledger.turn + 1
      const g = governAll(r.additionalContext, {
        turn,
        window: rt.options.dedupeWindow,
        loadedSkills: new Set([...rt.ledger.skills, ...rt.hiddenSkills]),
        mcpUsed: new Set(Object.keys(rt.ledger.mcp)),
        wroteCode: rt.ledger.lastCodeEditAt > 0,
        onOpus: /opus/i.test(await $.session.model()),
      }, rt.governor)
      rt.governor = { blocks: prune(g.seen.blocks, turn), skills: g.seen.skills }
      rt.governed.prompts += 1
      rt.governed.dropped += g.dropped
      rt.governed.kept += g.entries.length
      return { ...r, additionalContext: g.entries }
    } catch (err) {
      noteError('governor', err)
      return r
    }
  })

  on('prompt.submit', async ($, e, next) => {
    try {
      if ((e.origin.kind === 'composer' || e.origin.kind === 'bridge') && dropResume()) await $.store.delete(resumeKey(rt.sessionId))
      const extra: string[] = []
      const pending = takePending()
      if (pending.length) extra.push(`mercy: hook advisories from background runs since the last turn:\n\n${pending.join('\n\n')}`)
      const line = stateLine(snapshot(await $.clock.now()))
      if (line && line !== lastStateLine) extra.push(line)
      lastStateLine = line ?? ''
      if (extra.length) return next({ ...e, context: [...(e.context ?? []), ...extra] })
    } catch (err) {
      noteError('prompt.submit', err)
    }
    return next(e)
  })

  on('prompt.compose', async (_$, e, next) => {
    const r = await next(e)
    try {
      if (rt.options.brain !== 'on' || e.traits.includes('bare')) return r
      brainText ??= brainSection(rt.brain) ?? ''
      if (!brainText) return r
      return { sections: [...r.sections, { id: 'mercy:brain', text: brainText, scope: 'session' as const }] }
    } catch (err) {
      noteError('prompt.compose', err)
      return r
    }
  })

  on('prompt.attachment', { type: 'skill_listing' }, async (_$, e, next) => {
    const r = await next(e)
    try {
      if (rt.options.focus !== 'on' || !rt.repoRoot || r.text === null) return r
      const f = focusListing(r.text, rt.options.focusHide)
      rt.focusHidden = f.hidden
      return f.hidden ? { text: f.text } : r
    } catch (err) {
      noteError('focus', err)
      return r
    }
  })

  on('tool.describe', { tool: /^mcp__mercy__/ }, async (_$, e, next) => {
    const r = await next(e)
    return { ...r, isDeferred: false }
  })
}
