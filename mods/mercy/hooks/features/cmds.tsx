// Command cards: `/wrapup` here, `/ports` `/deps` `/standup` in auto.tsx (their data is kept
// fresh there by itself). Each command prints one short line (the only text the model reads,
// tagged `#n`); the CommandOutput hook below draws the full card from state in its place,
// with Copy and "Open in pane" buttons. A card missing from state, or one tagged for another
// command, falls back to the printed line.

import type { On } from 'claude-code'
import { atom, read, update } from 'claude-code'

import type { Card, PulseView } from '../../types'
import { withCard } from '../lib/auto'
import { recapMarkdown } from '../lib/deckviews'
import { noteError, rt } from '../lib/runtime'
import { snapshot } from '../lib/snap'
import { PANE_ID } from '../lib/specs'

const CARDS = atom({ plugin: 'mercy', key: 'cards' } as const, {} as Record<string, Card>)
const VIEW = atom({ plugin: 'mercy', key: 'view' } as const, 'overview' as PulseView)
const PANE_VIEW: Record<string, PulseView> = { wrapup: 'overview', standup: 'today', ports: 'ports', deps: 'deps' }

export function registerCmds(on: On): void {
  on('command.run', { command: 'wrapup' }, async $ => {
    try {
      const now = await $.clock.now()
      const s = snapshot(now)
      rt.cardSeq = Math.max(now, rt.cardSeq + 1)
      const card: Card = { id: rt.cardSeq, command: 'wrapup', title: 'Session recap', markdown: recapMarkdown(s, rt.deck), at: now }
      await update($, CARDS, all => withCard(all, card))
      return { text: `wrapup #${card.id}: session ${Math.round((now - s.ledger.startedAt) / 60_000)} min, ${Object.keys(s.ledger.files).length} files edited, ${s.ledger.commands.length} commands` }
    } catch (err) {
      noteError('/wrapup', err)
      return { text: `/wrapup failed: ${err instanceof Error ? err.message : String(err)}` }
    }
  })

  on('ui.render', { component: 'CommandOutput', props: { command: ['wrapup', 'standup', 'ports', 'deps'] } }, async ($, e, next) => {
    const id = /#(\d+):/.exec(e.props.text)?.[1]
    const card = id ? (await read($, CARDS))[id] : undefined
    if (!card || card.command !== e.props.command || e.props.isErrored) return next(e)
    const { Box, Text, Markdown, Button } = $.ui.resolve(e)
    const view = PANE_VIEW[card.command] ?? 'overview'
    return (
      <Box flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1}>
        <Text bold color="cyan">{card.title}</Text>
        <Markdown key={`md-${card.id}`} text={card.markdown} />
        <Box flexDirection="row" gap={1}>
          {card.copy ? (
            <Button key={`copy-${card.id}`} label="Copy" onPress={p => void $.ui.copy({ text: card.copy ?? '', surface: p.surface }).then(c => $.ui.toast(c.isCopied ? 'mercy: copied' : `mercy: copy failed (${c.reason})`))} />
          ) : null}
          <Button key={`pane-${card.id}`} label="Open in pane" onPress={() => void update($, VIEW, () => view).then(() => $.ui.open({ id: PANE_ID, title: 'mercy pulse' }))} />
        </Box>
      </Box>
    )
  })
}
