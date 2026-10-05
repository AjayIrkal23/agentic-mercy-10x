// mercy: workflow intelligence for agentic-mercy-10x as one Claude Code mod.
// Every feature registers here in a fixed order (registration order is nesting order:
// earlier hooks run outside later ones). A feature whose setup throws is skipped and
// recorded; the others still load. Behaviour is gated by userConfig at run time.
// Each registerX(on) is called by name: the validator follows `on` only through direct
// calls to functions it can see.

import type { Register } from 'claude-code'

import { registerAlerts } from './features/alerts'
import { registerAuto } from './features/auto'
import { registerBridge } from './features/bridge'
import { registerCmds } from './features/cmds'
import { registerDeck } from './features/deck'
import { registerLifecycle } from './features/lifecycle'
import { registerTools } from './features/mtools'
import { registerPrompts } from './features/prompts'
import { registerPulse } from './features/pulse'
import { registerRestyle } from './features/restyle'
import { registerStop } from './features/stop'
import { registerToolflow } from './features/toolflow'
import { noteError, parseOptions, rt } from './lib/runtime'

function failed(name: string, err: unknown): void {
  rt.health.features[name] = 'error'
  noteError(`register ${name}`, err)
}

export const register: Register = (on, options) => {
  rt.options = parseOptions(options)
  try {
    registerLifecycle(on)
  } catch (err) {
    failed('lifecycle', err)
  }
  try {
    registerToolflow(on)
  } catch (err) {
    failed('toolflow', err)
  }
  try {
    registerTools(on)
  } catch (err) {
    failed('tools', err)
  }
  try {
    registerBridge(on)
  } catch (err) {
    failed('bridge', err)
  }
  try {
    registerStop(on)
  } catch (err) {
    failed('stop', err)
  }
  try {
    registerPrompts(on)
  } catch (err) {
    failed('prompts', err)
  }
  try {
    registerPulse(on)
  } catch (err) {
    failed('pulse', err)
  }
  try {
    registerDeck(on)
  } catch (err) {
    failed('deck', err)
  }
  try {
    registerAuto(on)
  } catch (err) {
    failed('auto', err)
  }
  try {
    registerAlerts(on)
  } catch (err) {
    failed('alerts', err)
  }
  try {
    registerCmds(on)
  } catch (err) {
    failed('cmds', err)
  }
  try {
    registerRestyle(on)
  } catch (err) {
    failed('restyle', err)
  }
}
