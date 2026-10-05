// mercy's own tools for the model: live session state, the repo brain, and remember.
// Registered in session.start (lifecycle); served here by matched tool.call hooks.

import type { On } from 'claude-code'

import type { RepoFacts } from '../../types'
import { addNote, brainSection, mergeFacts, storeKey } from '../lib/brain'
import { rt } from '../lib/runtime'
import { findSecret } from '../lib/secrets'
import { sessionState } from '../lib/snap'

const BRAIN = { plugin: 'mercy', key: 'brain' } as const

export function registerTools(on: On): void {
  on('tool.call', { tool: 'mcp__mercy__session_state' }, async $ => {
    return { result: JSON.stringify(sessionState(await $.clock.now()), null, 1) }
  })

  on('tool.call', { tool: 'mcp__mercy__repo_facts' }, async () => {
    if (!rt.brain) return { result: 'No repo brain: this session is not in a git repo, or the brain feature is off.' }
    return { result: `${brainSection(rt.brain) ?? 'Nothing learned about this repo yet.'}\n\n${JSON.stringify({ commands: rt.brain.commands, fixes: rt.brain.fixes }, null, 1)}` }
  })

  on('tool.call', { tool: 'mcp__mercy__remember' }, async ($, e) => {
    const raw = e['fact']
    const fact = typeof raw === 'string' ? raw : ''
    if (!rt.brain || !rt.repoRoot) return { result: 'Not saved: no repo brain in this session (not a git repo, or brain is off).' }
    if (findSecret(fact)) return { result: 'Not saved: the fact looks like it contains a secret.' }
    const added = addNote(rt.brain, fact, await $.clock.now())
    if (added) {
      // merged over other sessions' writes, as lifecycle saves it (H-08)
      const key = storeKey(rt.repoRoot)
      const merged = mergeFacts((await $.store.get(key)) as RepoFacts | undefined, rt.brainBase, rt.brain)
      await $.store.set(key, merged)
      rt.brain = merged
      rt.brainBase = JSON.parse(JSON.stringify(merged)) as RepoFacts
      await $.state.set(BRAIN, rt.brain)
    }
    return { result: added ? 'Saved for future sessions in this repo.' : 'Not saved: empty, or already known.' }
  })
}
