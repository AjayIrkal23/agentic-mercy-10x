// The visible side: a band above the prompt only when there is something to act on,
// the /pulse pane with ten views (letter hotkeys, r refreshes), and the /mercy command
// (status, brain, forget, ...; `release` is answered by the bridge, which owns the one release).

import type { EngineInterface, On } from 'claude-code'
import { atom, read, update } from 'claude-code'

import type { PulseView } from '../../types'
import { depsRows, lastSessionLine, portsRows } from '../lib/auto'
import { brainSection, emptyFacts, storeKey } from '../lib/brain'
import { sparkCells } from '../lib/deck'
import type { Row } from '../lib/deckviews'
import { ciRows, gitRows, todoRows, usageRows } from '../lib/deckviews'
import { duration } from '../lib/format'
import { dropResume, noteError, resumeKey, rt, ui } from '../lib/runtime'
import { snapshot } from '../lib/snap'
import { PANE_ID } from '../lib/specs'
import type { BandAction, Snapshot } from '../lib/views'
import { bandModel, paneRows, VIEW_KEYS, VIEWS } from '../lib/views'

const VIEW = atom({ plugin: 'mercy', key: 'view' } as const, 'overview' as PulseView)
const HIDDEN = atom({ plugin: 'mercy', key: 'bandHidden' } as const, false)
const LEDGER = { plugin: 'mercy', key: 'ledger' } as const
const BRAIN = { plugin: 'mercy', key: 'brain' } as const
const DECK = { plugin: 'mercy', key: 'deck' } as const

async function cancelResume($: EngineInterface): Promise<boolean> {
  if (!dropResume()) return false
  await $.store.delete(resumeKey(rt.sessionId))
  return true
}

async function press($: EngineInterface, a: BandAction): Promise<void> {
  try {
    if (a.prompt) await $.prompt.submit({ text: a.prompt })
    else if (a.command === 'hide') await update($, HIDDEN, () => true)
    else if (a.command === 'open-pane') await $.ui.open({ id: PANE_ID, title: 'mercy pulse' })
    else if (a.command === 'cancel-resume') await cancelResume($)
    else if (a.command === 'compact') await $.session.compact()
    else if (a.command === 'open-ci') {
      await update($, VIEW, () => 'ci')
      await $.ui.open({ id: PANE_ID, title: 'mercy pulse' })
    }
  } catch (err) {
    noteError(`band ${a.key}`, err)
    $.ui.toast(`mercy: ${a.label} failed: ${err instanceof Error ? err.message : String(err)}`)
  }
}

async function forget($: EngineInterface): Promise<string> {
  if (!rt.repoRoot) return 'Not in a git repo: nothing to forget.'
  await $.store.delete(storeKey(rt.repoRoot))
  rt.brain = emptyFacts(rt.repoRoot, await $.clock.now())
  await $.state.set(BRAIN, rt.brain)
  return `Forgot everything mercy learned about ${rt.repoRoot}.`
}

function statusReport(now: number): string {
  const s = snapshot(now)
  const f = rt.health.features
  return [
    `mercy mods — features: ${Object.entries(f).map(([k, v]) => `${k} ${v}`).join(' · ') || 'not initialised'}`,
    `bridge: ${rt.bridge.owned.length} links owned (${rt.bridge.owned.join(', ') || 'none'}); ${rt.bridge.ran} background runs, ${rt.bridge.failed} failed, ${s.queued} queued; blocking time moved off the critical path ≈ ${duration(rt.bridge.savedMs)}`,
    `session: turn ${rt.ledger.turn}, ${Object.keys(rt.ledger.files).length} files edited, ${rt.ledger.commands.length} commands, ${rt.ledger.agents.length} subagents, context ${Math.round(rt.contextPct)}%`,
    `repo: ${rt.repoRoot ?? '(none)'}${rt.branch ? ` @ ${rt.branch}` : ''} · brain: ${rt.brain ? `${Object.keys(rt.brain.commands).length} commands, ${rt.brain.notes.length} notes` : 'off'}`,
    s.resumeLabel ? `auto-resume scheduled for ${s.resumeLabel}` : 'auto-resume: idle',
    `health: ${rt.health.errors} hook errors${rt.health.lastError ? ` (last: ${rt.health.lastError})` : ''}`,
  ].join('\n')
}

function viewRows(view: PulseView, s: Snapshot, width: number): Row[] {
  if (view === 'usage') return usageRows(s, width)
  if (view === 'git') return gitRows(s.deck?.git, s.now, width)
  if (view === 'ci') return ciRows(s.deck?.ci, s.now, width)
  if (view === 'todo') return todoRows(s.deck?.todos ?? [], width)
  if (view === 'ports') return portsRows(s.deck?.ports, width, s.deck?.portsError)
  if (view === 'deps') return depsRows(s.deck?.deps, s.now, width)
  if (view === 'today') return []
  const last = view === 'overview' ? lastSessionLine(s.deck?.lastSession, s.now) : undefined
  return [...paneRows(view, s, width).map(text => ({ text })), ...(last ? [{ text: last, dim: true }] : [])]
}

export function registerPulse(on: On): void {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (!ui().band || e.props.hasSurvey) return next(e)
    await $.state.get(LEDGER)
    await $.state.get(DECK)
    if (await read($, HIDDEN)) return next(e)
    const model = bandModel(snapshot(await $.clock.now()))
    if (!model) return next(e)
    const actions = model.actions.filter(a => !(a.command === 'compact' && e.props.isWorking))
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {model.lines.map(line => (
          <Text color={line.startsWith('✗') ? 'red' : 'yellow'} wrap="truncate-end">{line}</Text>
        ))}
        <Box flexDirection="row" gap={1}>
          {actions.map(a => (
            <Button key={`mercy-${a.key}`} label={a.label} dimColor={a.command === 'hide'} variant={a.key === 'verify' || a.key === 'ci' ? 'primary' : undefined} onPress={() => void press($, a)} />
          ))}
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    const view = await read($, VIEW)
    await $.state.get(LEDGER)
    await $.state.get(DECK)
    const s = snapshot(await $.clock.now())
    const width = e.props.bodyColumns
    const rows = viewRows(view, s, width)
    const els = $.ui.resolve(e)
    const { Box, Text, Button, Link, Markdown } = els
    const Raster = 'Raster' in els ? els.Raster : undefined
    const sparkWidth = Math.max(10, Math.min(60, width - 2))
    const pr = view === 'ci' ? s.deck?.ci?.pr : undefined
    const standup = view === 'today' ? s.deck?.standup : undefined
    return (
      <Box flexDirection="column">
        <Box flexDirection="row" flexWrap="wrap" gap={1}>
          {VIEWS.map(v => (
            <Button key={`tab-${v}`} label={v} hotkey={VIEW_KEYS[v]} variant={v === view ? 'primary' : 'secondary'} onPress={() => void update($, VIEW, () => v)} />
          ))}
          <Button key="refresh" label="refresh" hotkey="r" dimColor onPress={() => $.ui.invalidate('ui.render')} />
          {pr ? <Link href={pr.url} label={`PR #${pr.number}`} /> : null}
          {standup ? <Button key="copy-standup" label="copy" hotkey="y" onPress={p => void $.ui.copy({ text: standup.markdown, surface: p.surface })} /> : null}
        </Box>
        {view === 'today' ? <Markdown key="standup" text={standup?.markdown ?? "Making today's standup (first session of the day, from your commits, this session and open tasks)…"} /> : null}
        {rows.map(row =>
          row.spark && Raster ? (
            <Raster key="spark" columns={sparkWidth} rows={1} cells={sparkCells((s.deck?.turns ?? []).map(t => t.output), sparkWidth)} />
          ) : row.spark ? null : (
            <Text color={row.color} dimColor={row.dim} bold={row.bold} wrap="truncate-end">{row.text || ' '}</Text>
          ),
        )}
        {e.props.isFocused ? <Text dimColor>keys: {VIEWS.map(v => VIEW_KEYS[v]).join(' ')} switch views · r refresh · Esc back to the prompt</Text> : null}
      </Box>
    )
  })

  on('command.run', { command: 'pulse' }, async ($, e) => {
    await update($, HIDDEN, () => false)
    const want = e.args.trim().toLowerCase()
    if ((VIEWS as readonly string[]).includes(want)) await update($, VIEW, () => want as PulseView)
    const opened = await $.ui.open({ id: PANE_ID, title: 'mercy pulse' })
    return { text: opened.isPlaced ? 'mercy pulse opened.' : `mercy pulse is waiting for room: ${opened.reason}` }
  })

  on('command.run', { command: 'mercy' }, async ($, e) => {
    const arg = e.args.trim().split(/\s+/)[0] ?? ''
    const now = await $.clock.now()
    if (arg === 'brain') return { text: brainSection(rt.brain) ?? 'Nothing learned about this repo yet.' }
    if (arg === 'forget') return { text: await forget($) }
    if (arg === 'resume-cancel') return { text: (await cancelResume($)) ? 'Auto-resume cancelled.' : 'No auto-resume was scheduled.' }
    return { text: statusReport(now) }
  })
}
