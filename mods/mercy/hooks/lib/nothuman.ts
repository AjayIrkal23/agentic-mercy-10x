// Harness "prompts" that no human typed (task notifications, interrupts, peer messages,
// subagent hand-backs). Same rule as hooks/lib/turns.py `_not_human` and
// hooks/prompt_router/classify.py `is_machine_text`: keep the three in step.

const NOT_HUMAN = ['<task-notification>', '[Request interrupted', '<cross-session-message',
  '[Subagent hand-back]', '<agent-message from=', 'Another Claude session sent a message']
const SYSTEM_REMINDER_OPEN = /^(?:\s*<system-reminder\b[^>]*>)+/
// a hand-back marker that opens a line or follows a closing tag in the first 400 chars is machine
// text; a human sentence quoting it mid-line is not
const NOT_HUMAN_MARKER = /(?:^|\n|>)\s*(?:\[Subagent hand-back\]|<agent-message from=|Another Claude session sent a message)/

export function isNotHuman(prompt: string): boolean {
  const p = prompt.trimStart()
  if (NOT_HUMAN.some(m => p.startsWith(m))) return true
  const body = p.replace(SYSTEM_REMINDER_OPEN, '').trimStart()
  return NOT_HUMAN.some(m => body.startsWith(m)) || NOT_HUMAN_MARKER.test(body.slice(0, 400))
}
