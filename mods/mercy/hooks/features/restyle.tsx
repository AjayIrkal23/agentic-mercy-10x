// Small rewrites of the engine's own rows, full mode only: the spinner says what this turn
// has done so far, a background task's notification is one compact line (ctrl+o still shows
// it whole), and the footer's mode labels name the UI mode when it is not `full`.

import type { On } from 'claude-code'

import { duration } from '../lib/format'
import { runningAgents } from '../lib/ledger'
import { rt, ui } from '../lib/runtime'

const TASK_ICON: Record<string, [string, string]> = {
  completed: ['✓', 'green'], failed: ['✗', 'red'], error: ['✗', 'red'], killed: ['■', 'gray'], stopped: ['■', 'gray'],
}

export function registerRestyle(on: On): void {
  on('ui.render', { component: 'Spinner' }, (_$, e, next) => {
    if (!ui().restyle) return next(e)
    const l = rt.ledger
    const files = Object.keys(l.turnEdits).length
    const commands = l.commands.filter(c => c.turn === l.turn && c.agent === '').length
    const agents = runningAgents(l).length
    const tail = [files ? `✎${files}` : '', commands ? `⚒${commands}` : '', agents ? `⚙${agents}` : ''].filter(Boolean).join(' ')
    return tail ? next({ ...e, props: { ...e.props, suffix: `${e.props.suffix} ${tail}` } }) : next(e)
  })

  on('ui.render', { component: 'UserMessage', props: { origin: { kind: 'task-notification' } } }, async ($, e, next) => {
    if (!ui().restyle || e.props.isExpanded) return next(e)
    const task = e.props.task
    const [icon, color] = TASK_ICON[(task?.status ?? '').toLowerCase()] ?? ['⚙', 'cyan']
    const summary = e.props.text.split('\n').map(s => s.trim()).find(Boolean) ?? 'background task'
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="row" gap={1}>
        <Text color={color}>{icon}</Text>
        <Text dimColor wrap="truncate-end">{summary}{task?.durationMs ? ` · ${duration(task.durationMs)}` : ''}</Text>
      </Box>
    )
  })

  on('ui.render', { component: 'SessionMode' }, (_$, e, next) => {
    const mode = rt.deck.prefs.mode ?? rt.options.pulse
    return mode === 'full' ? next(e) : next({ ...e, props: { ...e.props, modes: [...e.props.modes, `ui ${mode}`] } })
  })
}
