// The plugin's in-memory runtime, shared by every feature file. One plugin environment
// holds one copy; a hot reload starts it over, and session.start restores what matters
// from $.state. No `$` here: features own their engine calls.

import type { PluginOptions, Timer } from 'claude-code'

import type { BridgeStats, Deck, Health, Ledger, RepoFacts, UiMode } from '../../types'
import type { Flags } from './deck'
import { flags } from './deck'
import type { DispatchConfig } from './dispatch'
import type { GovernorSeen } from './governor'
import { emptyLedger, verifiedSince } from './ledger'

type OnOff = 'on' | 'off'

export type Options = {
  bridge: OnOff
  tddGuard: 'async' | 'sync' | 'off'
  guard: OnOff
  verifyGate: 'block' | 'advise' | 'off'
  dedupeWindow: number
  brain: OnOff
  focus: OnOff
  focusHide: string[]
  autoResume: OnOff
  pulse: UiMode
  sound: OnOff
  soundAfter: number // seconds a turn runs before its end sounds and toasts
  notify: OnOff
  notifyAfter: number // seconds a turn runs before its end sends a desktop notification
  quietHours: string
  paneAuto: OnOff
  ci: OnOff
  autoCompact: number // context % at which the mod compacts between turns; 0 = never
}

/**
 * Fallbacks for a value missing from `options`. The engine fills each field from the
 * plugin.json `userConfig` default before `register` runs, so the manifest is the source
 * (H-13); `focusHide` keeps no second copy of its list here.
 */
export const DEFAULTS: Options = {
  bridge: 'on',
  tddGuard: 'async',
  guard: 'on',
  verifyGate: 'block',
  dedupeWindow: 6,
  brain: 'on',
  focus: 'on',
  focusHide: [],
  autoResume: 'on',
  pulse: 'full',
  sound: 'on',
  soundAfter: 20,
  notify: 'on',
  notifyAfter: 60,
  quietHours: '',
  paneAuto: 'on',
  ci: 'on',
  autoCompact: 85,
}

function pick<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : fallback
}

function seconds(v: unknown, fallback: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? Math.max(0, Math.min(3600, Math.round(v))) : fallback
}

export function parseOptions(raw: PluginOptions | undefined): Options {
  const o = raw ?? {}
  const window = typeof o['dedupeWindow'] === 'number' ? Math.max(0, Math.min(50, Math.round(o['dedupeWindow']))) : DEFAULTS.dedupeWindow
  const hide = typeof o['focusHide'] === 'string' ? o['focusHide'].split(',').map(s => s.trim()).filter(Boolean) : DEFAULTS.focusHide
  return {
    bridge: pick(o['bridge'], ['on', 'off'], DEFAULTS.bridge),
    tddGuard: pick(o['tddGuard'], ['async', 'sync', 'off'], DEFAULTS.tddGuard),
    guard: pick(o['guard'], ['on', 'off'], DEFAULTS.guard),
    verifyGate: pick(o['verifyGate'], ['block', 'advise', 'off'], DEFAULTS.verifyGate),
    dedupeWindow: window,
    brain: pick(o['brain'], ['on', 'off'], DEFAULTS.brain),
    focus: pick(o['focus'], ['on', 'off'], DEFAULTS.focus),
    focusHide: hide,
    autoResume: pick(o['autoResume'], ['on', 'off'], DEFAULTS.autoResume),
    pulse: pick(o['pulse'], ['full', 'focus', 'quiet', 'off'], DEFAULTS.pulse),
    sound: pick(o['sound'], ['on', 'off'], DEFAULTS.sound),
    soundAfter: seconds(o['soundAfter'], DEFAULTS.soundAfter),
    notify: pick(o['notify'], ['on', 'off'], DEFAULTS.notify),
    notifyAfter: seconds(o['notifyAfter'], DEFAULTS.notifyAfter),
    quietHours: typeof o['quietHours'] === 'string' ? o['quietHours'] : DEFAULTS.quietHours,
    paneAuto: pick(o['paneAuto'], ['on', 'off'], DEFAULTS.paneAuto),
    ci: pick(o['ci'], ['on', 'off'], DEFAULTS.ci),
    autoCompact: typeof o['autoCompact'] === 'number' ? Math.max(0, Math.min(99, Math.round(o['autoCompact']))) : DEFAULTS.autoCompact,
  }
}

export type Runtime = {
  options: Options
  interactive: boolean
  sessionId: string
  transcriptPath: string
  repoRoot: string | undefined
  branch: string | undefined
  pluginRoot: string
  hooksDir: string
  python: string[]
  dispatch: DispatchConfig | undefined
  ledger: Ledger
  brain: RepoFacts | null
  /** The brain as last read from or written to $.store: the base its merge measures deltas against (H-08). */
  brainBase: RepoFacts | null
  /** Command runs after this time are not in the brain yet. */
  brainCursor: number
  bridge: BridgeStats
  health: Health
  governor: GovernorSeen
  /** Router blocks/skill pushes the governor dropped and kept this session. */
  governed: { dropped: number; kept: number; prompts: number }
  /** Skills the focus feature left out of the latest skill listing. */
  focusHidden: number
  hiddenSkills: Set<string>
  /** Advisory text from background Python links, waiting for the next tool result or prompt. */
  pending: string[]
  /** tdd-guard advisories in `pending` → the file each one judged. */
  pendingFiles: Map<string, string>
  /** Root → whether that git root has a CLAUDE.md (for the dox gate predicate). */
  claudeMdRoots: Map<string, boolean>
  /** tool_use_ids of in-flight calls made inside a subagent loop (tool.call knows the loop, classic.PreToolUse does not). */
  subagentCalls: Set<string>
  contextPct: number
  costUsd: number
  /** Real user prompts so far (classic.UserPromptSubmit); a Stop block is allowed once per value. */
  humanTurn: number
  /** The human turn of the last Stop block by anyone (Python gates, verify gate, late advisories). */
  blockedHumanTurn: number
  /** The user's last prompt said stop (lib/consent): no mercy Stop block this human turn. */
  consent: boolean
  lastFlush: number
  resumeTimer: Timer | undefined
  resumeAt: number | undefined
  resumeAttempts: number
  /** What the deck UI watches (git, CI, todos, per-turn usage, limits, /ui prefs). */
  deck: Deck
  cardSeq: number // last command card id (clock-based)
  lastSoundAt: number // 3 s throttle
  /** Session cost when the current main turn started, for its per-turn cost. */
  turnCostBase: number
}

export function freshRuntime(options: Options): Runtime {
  return {
    options,
    interactive: false,
    sessionId: '',
    transcriptPath: '',
    repoRoot: undefined,
    branch: undefined,
    pluginRoot: '',
    hooksDir: '',
    python: ['python3'],
    dispatch: undefined,
    ledger: emptyLedger('', 0),
    brain: null,
    brainBase: null,
    brainCursor: 0,
    bridge: { owned: [], queued: 0, ran: 0, failed: 0, savedMs: 0, delivered: 0 },
    health: { features: {}, errors: 0 },
    governor: { blocks: {}, skills: {} },
    governed: { dropped: 0, kept: 0, prompts: 0 },
    focusHidden: 0,
    hiddenSkills: new Set(),
    pending: [],
    pendingFiles: new Map(),
    claudeMdRoots: new Map(),
    subagentCalls: new Set(),
    contextPct: 0,
    costUsd: 0,
    humanTurn: 0,
    blockedHumanTurn: -1,
    consent: false,
    lastFlush: 0,
    resumeTimer: undefined,
    resumeAt: undefined,
    resumeAttempts: 0,
    deck: { todos: [], turns: [], limits: [], prefs: {} },
    cardSeq: 0,
    lastSoundAt: 0,
    turnCostBase: 0,
  }
}

/** The one runtime of this plugin environment; register() replaces its options. */
export const rt: Runtime = freshRuntime(DEFAULTS)

/** What the current UI mode turns on: `/ui` prefs over the userConfig defaults. */
export function ui(): Flags {
  const o = rt.options
  return flags(rt.deck.prefs.mode ?? o.pulse, rt.deck.prefs, { sound: o.sound === 'on', notify: o.notify === 'on', paneAuto: o.paneAuto === 'on' })
}

export function noteError(where: string, err: unknown): void {
  rt.health.errors += 1
  rt.health.lastError = `${where}: ${err instanceof Error ? err.message : String(err)}`.slice(0, 300)
}

/** Takes the queued advisories (deduped) for delivery. */
export function takePending(): string[] {
  // a tdd-guard advisory is moot once its file passed a test after the edit
  const out = [...new Set(rt.pending)].filter(t => t && !verifiedSince(rt.ledger, rt.pendingFiles.get(t)))
  rt.pending = []
  rt.pendingFiles.clear()
  if (out.length) rt.bridge.delivered += out.length
  return out
}

/** H-06: fresh on/off rows, keeping a feature whose register() threw marked `error`. */
export function withErrors(prev: Health['features'], fresh: Record<string, 'on' | 'off'>): Health['features'] {
  const out: Health['features'] = { ...fresh }
  for (const [k, v] of Object.entries(prev)) if (v === 'error') out[k] = 'error'
  return out
}

/** Feature on/off rows for `/mercy status` and the pulse pane. */
export function featureHealth(o: Options): Record<string, 'on' | 'off'> {
  const on = (v: boolean): 'on' | 'off' => (v ? 'on' : 'off')
  return {
    bridge: on(o.bridge === 'on'), guard: on(o.guard === 'on'), brain: on(o.brain === 'on'), focus: on(o.focus === 'on'),
    verify: on(o.verifyGate !== 'off'), resume: on(o.autoResume === 'on'), pulse: on(o.pulse !== 'off'), governor: on(o.dedupeWindow > 0),
    sound: on(o.sound === 'on'), notify: on(o.notify === 'on'), ci: on(o.ci === 'on'),
  }
}

/** The `$.store` key of one session's scheduled auto-resume. */
export function resumeKey(sessionId: string): string {
  return `resume:${sessionId}`
}

/** Cancels a scheduled auto-resume; true when one was pending (the caller deletes its store key). */
export function dropResume(): boolean {
  const had = rt.resumeTimer !== undefined || rt.resumeAt !== undefined
  rt.resumeTimer?.cancel()
  rt.resumeTimer = undefined
  rt.resumeAt = undefined
  return had
}

/** Minutes east of UTC on this host (the mod environment has no Intl guarantee). */
export function hostOffsetMinutes(): number {
  return -new Date().getTimezoneOffset()
}
