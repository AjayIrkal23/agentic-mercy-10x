// Pure repo brain: what this repo taught earlier sessions (verified commands, fixes,
// notes), kept in $.store per repo root and shown to the model as ONE stable system
// prompt section per session (stable text keeps the prompt cache intact).

import type { CommandRun, FixNote, KnownCommand, Ledger, RepoFacts, VerifyKind } from '../../types'
import { duration } from './format'
import { relativeTo } from './paths'

const MAX_COMMANDS = 14
const MAX_FIXES = 8
const MAX_NOTES = 12
const SECTION_CAP = 1600

export function emptyFacts(root: string, now: number): RepoFacts {
  const name = root.split(/[\\/]/).filter(Boolean).pop() ?? root
  return { root, name, stack: [], commands: {}, fixes: [], notes: [], sessions: 0, updatedAt: now }
}

export function storeKey(root: string): string {
  return `repo:${root.replace(/\\/g, '/').toLowerCase()}`
}

/** A command worth remembering: a real verification, not a one-off with temp paths. */
function memorable(run: CommandRun): VerifyKind | undefined {
  if (run.command.length > 200 || /\/tmp\/|\\Temp\\|mktemp/.test(run.command)) return undefined
  return run.verify.find(k => k === 'test') ?? run.verify.find(k => k === 'typecheck') ?? run.verify.find(k => k === 'build') ?? run.verify[0]
}

/** Folds this session's verification runs into the repo's known commands. */
export function learnCommands(facts: RepoFacts, runs: readonly CommandRun[], sinceAt: number): void {
  for (const run of runs) {
    if (run.at <= sinceAt) continue
    const kind = memorable(run)
    if (!kind) continue
    const prev = facts.commands[run.key]
    facts.commands[run.key] = {
      command: run.command,
      kind,
      passes: (prev?.passes ?? 0) + (run.ok ? 1 : 0),
      fails: (prev?.fails ?? 0) + (run.ok ? 0 : 1),
      lastAt: run.at,
      lastOk: run.ok,
      ms: run.ok ? Math.round(prev && prev.passes > 0 ? (prev.ms + run.ms) / 2 : run.ms) : prev?.ms ?? run.ms,
    }
  }
  facts.commands = capCommands(facts.commands)
}

function capCommands(commands: Record<string, KnownCommand>): Record<string, KnownCommand> {
  const keep = Object.entries(commands)
    .sort(([, a], [, b]) => b.passes + b.fails - (a.passes + a.fails) || b.lastAt - a.lastAt)
    .slice(0, MAX_COMMANDS)
  return Object.fromEntries(keep)
}

/** Union by key, oldest first, the newest `max` kept. */
function unionBy<T extends { at: number }>(a: readonly T[], b: readonly T[], key: (x: T) => string, max: number): T[] {
  const seen = new Map<string, T>()
  for (const x of [...a, ...b]) if (!seen.has(key(x))) seen.set(key(x), x)
  return [...seen.values()].sort((x, y) => x.at - y.at).slice(-max)
}

/**
 * H-08: what to write back when another session may have written `stored` since this one
 * loaded `base`: this session's command counts are added as deltas, notes and fixes unioned.
 */
export function mergeFacts(stored: RepoFacts | undefined, base: RepoFacts | null, mine: RepoFacts): RepoFacts {
  if (!stored || typeof stored !== 'object' || typeof stored.root !== 'string') return mine
  const commands = { ...stored.commands }
  for (const [key, m] of Object.entries(mine.commands)) {
    const b = base?.commands[key]
    const s = commands[key]
    const dp = m.passes - (b?.passes ?? 0)
    const df = m.fails - (b?.fails ?? 0)
    if (!s) commands[key] = m
    else if (dp > 0 || df > 0) {
      const later = m.lastAt >= s.lastAt ? m : s
      commands[key] = { ...later, passes: s.passes + Math.max(0, dp), fails: s.fails + Math.max(0, df) }
    }
  }
  return {
    ...stored,
    packageManager: mine.packageManager ?? stored.packageManager,
    stack: mine.stack.length ? mine.stack : stored.stack,
    commands: capCommands(commands),
    fixes: unionBy(stored.fixes, mine.fixes, f => `${f.command}\u0000${f.error}`, MAX_FIXES),
    notes: unionBy(stored.notes, mine.notes, n => n.text, MAX_NOTES),
    sessions: stored.sessions + Math.max(0, mine.sessions - (base?.sessions ?? 0)),
    updatedAt: Math.max(stored.updatedAt, mine.updatedAt),
  }
}

/** A failure later resolved by a pass of the same command → a fix note naming the files edited between. */
export function learnFixes(facts: RepoFacts, l: Ledger): void {
  const firstFail: Record<string, CommandRun> = {}
  for (const run of l.commands) {
    if (!run.ok) {
      if (!firstFail[run.key] && run.error) firstFail[run.key] = run
      continue
    }
    const fail = firstFail[run.key]
    if (!fail) continue
    delete firstFail[run.key]
    const files = Object.values(l.files)
      .filter(f => f.lastAt > fail.at && f.lastAt <= run.at && f.code)
      .map(f => relativeTo(facts.root, f.path))
      .slice(0, 5)
    if (files.length === 0) continue
    const note: FixNote = { command: run.command, error: fail.error ?? '', files, at: run.at }
    if (facts.fixes.some(x => x.command === note.command && x.error === note.error)) continue
    facts.fixes.push(note)
  }
  facts.fixes = facts.fixes.slice(-MAX_FIXES)
}

export function addNote(facts: RepoFacts, text: string, now: number): boolean {
  const clean = text.replace(/\s+/g, ' ').trim().slice(0, 300)
  if (!clean || facts.notes.some(n => n.text === clean)) return false
  facts.notes.push({ text: clean, at: now })
  facts.notes = facts.notes.slice(-MAX_NOTES)
  return true
}

function day(at: number): string {
  return new Date(at).toISOString().slice(0, 10)
}

function commandLine(k: KnownCommand): string {
  const state = k.lastOk ? `passed ${k.passes}×` : `LAST RUN FAILED (${k.fails} fails)`
  const time = k.ms > 0 && k.lastOk ? `, ~${duration(k.ms)}` : ''
  return `\`${k.command}\` (${k.kind}, ${state}${time}, ${day(k.lastAt)})`
}

/** The system prompt section, or undefined when the repo taught nothing yet. */
export function brainSection(facts: RepoFacts | null): string | undefined {
  if (!facts) return undefined
  const cmds = Object.values(facts.commands).sort((a, b) => Number(b.kind === 'test') - Number(a.kind === 'test') || b.lastAt - a.lastAt)
  if (cmds.length === 0 && facts.fixes.length === 0 && facts.notes.length === 0 && !facts.packageManager) return undefined
  const lines = [`# Repo brain: ${facts.name} (mercy mod, learned across ${facts.sessions} session(s) in this repo)`]
  if (facts.packageManager || facts.stack.length) lines.push(`- Toolchain: ${[facts.packageManager, ...facts.stack].filter(Boolean).join(', ')}.`)
  if (cmds.length) lines.push(`- Verified commands: ${cmds.slice(0, 6).map(commandLine).join(' · ')}`)
  for (const f of facts.fixes.slice(-3)) lines.push(`- Past fix: \`${f.command}\` failing with "${f.error.slice(0, 90)}" was fixed by editing ${f.files.join(', ')} (${day(f.at)}).`)
  for (const n of facts.notes.slice(-5)) lines.push(`- Note: ${n.text}`)
  lines.push('Use these instead of rediscovering how to build and test. To keep a durable repo fact, call mcp__mercy__remember.')
  const text = lines.join('\n')
  return text.length <= SECTION_CAP ? text : `${text.slice(0, SECTION_CAP - 1)}…`
}

/** Lockfile/manifest names → package manager and stack words. */
export const MARKERS: ReadonlyArray<readonly [string, string, 'pm' | 'stack']> = [
  ['pnpm-lock.yaml', 'pnpm', 'pm'],
  ['yarn.lock', 'yarn', 'pm'],
  ['bun.lockb', 'bun', 'pm'],
  ['bun.lock', 'bun', 'pm'],
  ['package-lock.json', 'npm', 'pm'],
  ['go.mod', 'go', 'stack'],
  ['pyproject.toml', 'python', 'stack'],
  ['requirements.txt', 'python', 'stack'],
  ['Cargo.toml', 'rust', 'stack'],
  ['docker-compose.yml', 'docker-compose', 'stack'],
  ['next.config.js', 'next', 'stack'],
  ['next.config.mjs', 'next', 'stack'],
  ['next.config.ts', 'next', 'stack'],
  ['vite.config.ts', 'vite', 'stack'],
  ['vite.config.js', 'vite', 'stack'],
]

export function applyMarkers(facts: RepoFacts, present: readonly string[]): void {
  const pm = MARKERS.find(([file, , kind]) => kind === 'pm' && present.includes(file))
  if (pm) facts.packageManager = pm[1]
  const stack = new Set<string>()
  for (const [file, word, kind] of MARKERS) if (kind === 'stack' && present.includes(file)) stack.add(word)
  facts.stack = [...stack]
}
