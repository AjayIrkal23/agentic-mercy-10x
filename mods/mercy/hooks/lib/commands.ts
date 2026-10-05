// Pure classification of Bash commands: what each segment does (test, build, server,
// commit, ...). Feeds the ledger (verification evidence), the guard (servers, watchers,
// subagent commits) and the repo brain (verified commands).

import type { CommandKind, VerifyKind } from '../../types'
import { exitOwners } from './evidence'
import { innerScript, realCommand, splitSegments, timeoutSeconds, words } from './shell'
import { frameworkCli, toolchain } from './toolkinds'

export type Segment = {
  head: string
  kind: CommandKind
  background: boolean
  /** Under `timeout N` with N ≤ 60 s: a server or watcher here ends on its own (H-10). */
  bounded: boolean
  /** What a wrapper (`bash -c`, `eval`, `( … )`) runs, analysed in turn. */
  inner?: CommandInfo
}

export type CommandInfo = {
  segments: Segment[]
  kinds: CommandKind[]
  verify: VerifyKind[]
  isServer: boolean
  isWatch: boolean
  isCommit: boolean
  isPush: boolean
}

const VERIFY: ReadonlySet<string> = new Set(['test', 'typecheck', 'lint', 'build'])
const PMS = new Set(['npm', 'pnpm', 'yarn', 'bun'])
const PM_INSTALL = new Set(['install', 'i', 'ci', 'add', 'remove', 'rm', 'uninstall', 'update', 'up', 'upgrade'])
const WATCH_FLAG_TOOLS = new Set(['tsc', 'jest', 'vitest', 'tsup', 'esbuild', 'sass', 'babel', 'rollup', 'webpack', 'vue-tsc'])
const SERVER_TOOLS = new Set(['uvicorn', 'gunicorn', 'hypercorn', 'daphne', 'nodemon', 'ts-node-dev', 'http-server',
  'live-server', 'webpack-dev-server', 'json-server', 'air', 'start-storybook', 'serve', 'http.server'])
const TEST_TOOLS = new Set(['vitest', 'jest', 'mocha', 'ava', 'tap', 'pytest', 'py.test', 'nose2', 'tox', 'nox', 'rspec', 'phpunit', 'ctest', 'karma'])
const TYPECHECK_TOOLS = new Set(['vue-tsc', 'svelte-check', 'mypy', 'pyright', 'basedpyright', 'flow'])
const LINT_TOOLS = new Set(['eslint', 'oxlint', 'stylelint', 'flake8', 'pylint', 'golangci-lint', 'staticcheck', 'revive',
  'shellcheck', 'hadolint', 'markdownlint', 'markdownlint-cli2', 'rubocop'])
const FORMAT_TOOLS = new Set(['prettier', 'black', 'isort', 'gofmt', 'goimports', 'rustfmt', 'clang-format'])
const BUILD_TOOLS = new Set(['rollup', 'esbuild', 'tsup', 'parcel', 'turbo'])
const WATCH_TOOLS = new Set(['watchexec', 'entr', 'chokidar'])
const BOUNDED_S = 60
const MAX_DEPTH = 3

/** What a package.json script name does, by convention. */
export function scriptKind(name: string): CommandKind {
  const s = name.toLowerCase()
  if (/(^|[:_-])watch$|^watch([:_-]|$)/.test(s)) return 'watch'
  if (/^(test|tests|unit|e2e|spec|specs|coverage|cov|ci|verify|validate)$|^test[:_-]|[:_-](test|tests|e2e|spec|unit)$/.test(s)) return 'test'
  if (/^(typecheck|type-check|types|tsc|check-types|check)$|[:_-]types?$/.test(s)) return 'typecheck'
  if (/^(lint|eslint|stylelint)$|^lint[:_-]/.test(s)) return 'lint'
  if (/^(format|fmt|prettier)$|^format[:_-]/.test(s)) return 'format'
  if (/^(build|compile|bundle|dist)$|^build[:_-]/.test(s)) return 'build'
  if (/^(dev|start|serve|server|preview|develop|storybook)$|^(dev|start|serve)[:_-]/.test(s)) return 'server'
  return 'other'
}

const WATCH_FLAG = /^--watch(All)?(=(?!(false|0|no|off)$).*)?$/i
const OFF = /^(false|0|no|off)$/i

/** A `--watch` / `--watchAll` that turns watching on: `--watch=false` and `--watch false` (one-shot runs) do not. */
function watchOn(args: readonly string[]): boolean {
  return args.some((x, i) => WATCH_FLAG.test(x) && (x.includes('=') || !OFF.test(args[i + 1] ?? '')))
}

function hasWatchFlag(tool: string, args: readonly string[]): boolean {
  return watchOn(args) || (WATCH_FLAG_TOOLS.has(tool) && args.includes('-w'))
}

// Options that come before the subcommand and take a value: `npm --prefix server run
// dev-http`, `pnpm -C web dev`, `yarn --cwd web start`, `npm -w api run dev`,
// `pnpm --filter web dev`. Read past them or the script is invisible (audit H-01).
// `-w` / `--workspace` take a value in npm only: in pnpm `-w` is `--workspace-root` (santa P3).
const PM_VALUE_FLAGS = new Set(['--prefix', '-C', '--dir', '--cwd', '--filter', '-F'])
const NPM_VALUE_FLAGS = new Set(['-w', '--workspace'])

function skipPmOptions(a: readonly string[]): string[] {
  let i = 1
  while (i < a.length && (a[i] as string).startsWith('-')) {
    const f = a[i] as string
    const valued = PM_VALUE_FLAGS.has(f) || (a[0] === 'npm' && NPM_VALUE_FLAGS.has(f))
    i += !f.includes('=') && valued ? 2 : 1
  }
  return [a[0] as string, ...a.slice(i)]
}

function packageManager(argv: readonly string[]): CommandKind {
  const a = skipPmOptions(argv)
  const [t0, t1 = '', t2] = a
  if (t0 === 'yarn' && a.length === 1) return 'install'
  if (PM_INSTALL.has(t1)) return 'install'
  if (t0 === 'bun' && t1 === 'test') return hasWatchFlag('vitest', a.slice(2)) ? 'watch' : 'test'
  if (t1 === 'run' || t1 === 'run-script') return t2 ? withWatch(scriptKind(t2), a.slice(3)) : 'other'
  if (t1 === 'test' || t1 === 't' || t1 === 'tst') return withWatch('test', a.slice(2))
  if (t1 === 'start' || t1 === 'restart') return 'server'
  if (t0 !== 'npm' && t1 && !t1.startsWith('-')) return withWatch(scriptKind(t1), a.slice(2))
  return 'other'
}

function withWatch(kind: CommandKind, args: readonly string[]): CommandKind {
  return watchOn(args) ? 'watch' : kind
}

/** vitest watches by default outside CI, even without a TTY (audit H-03); `run` may follow options (santa P2). */
function vitestOnce(argv: readonly string[], rest: readonly string[]): boolean {
  return rest.some((x, i) => x === 'run' || x === '--run' || x === '--no-watch' || /^--watch=(false|0|no|off)$/i.test(x) ||
    (x === '--watch' && OFF.test(rest[i + 1] ?? ''))) || argv.some(w => /^CI=/.test(w))
}

function gitKind(a: readonly string[]): CommandKind {
  let i = 1
  while (i < a.length && (a[i] as string).startsWith('-')) i += a[i] === '-C' || a[i] === '-c' ? 2 : 1
  const sub = a[i] ?? ''
  return sub === 'commit' ? 'git-commit' : sub === 'push' ? 'git-push' : 'git'
}

/** Classifies one segment's argv (as typed; wrappers and runners are dropped here). */
export function classifyArgv(argv: readonly string[]): CommandKind {
  const a = realCommand(argv)
  const t0 = a[0] ?? ''
  const t1 = a[1] ?? ''
  const rest = a.slice(1)
  if (!t0) return 'other'
  if (t0 === 'git') return gitKind(a)
  if (PMS.has(t0)) return packageManager(a)
  if (t0 === 'nodemon') return 'server'
  if (hasWatchFlag(t0, rest) || WATCH_TOOLS.has(t0)) return 'watch'
  if (t0 === 'vitest') return vitestOnce(argv, rest) ? 'test' : 'watch'
  if (TEST_TOOLS.has(t0)) return 'test'
  if (t0 === 'node') return rest.some(x => x === '--watch' || x.startsWith('--watch-path')) ? 'watch' : rest.includes('--test') ? 'test' : 'other'
  if (t0 === 'tsx' && t1 === 'watch') return 'watch'
  if ((t0 === 'playwright' || t0 === 'cypress') && (t1 === 'test' || t1 === 'run')) return 'test'
  const tc = toolchain(t0, t1)
  if (tc !== undefined) return tc
  if (t0 === 'tsc') return rest.includes('--noEmit') ? 'typecheck' : 'build'
  if (TYPECHECK_TOOLS.has(t0)) return 'typecheck'
  if (t0 === 'ruff' || t0 === 'biome') return t1 === 'format' ? 'format' : 'lint'
  if (LINT_TOOLS.has(t0)) return 'lint'
  if (FORMAT_TOOLS.has(t0)) return 'format'
  const fw = frameworkCli(t0, t1, a)
  if (fw !== undefined) return fw
  if (SERVER_TOOLS.has(t0)) return 'server'
  if (BUILD_TOOLS.has(t0)) return 'build'
  if (t0 === 'uv' && (t1 === 'pip' || t1 === 'sync' || t1 === 'add')) return 'install'
  if ((t0 === 'pip' || t0 === 'pip3') && t1 === 'install') return 'install'
  if (['poetry', 'pipenv', 'composer', 'bundle'].includes(t0) && ['install', 'add', 'require'].includes(t1)) return 'install'
  return 'other'
}

/** Full analysis of a Bash tool command; wrappers are unwrapped up to MAX_DEPTH levels. */
export function analyze(command: string, runInBackground = false, depth = 0): CommandInfo {
  const raw = splitSegments(command)
  const segments: Segment[] = raw.map(seg => {
    const argv = words(seg.text)
    const script = depth < MAX_DEPTH ? innerScript(seg.text, argv) : undefined
    const limit = timeoutSeconds(argv)
    return {
      head: realCommand(argv).slice(0, 3).join(' '),
      kind: classifyArgv(argv),
      background: seg.background || runInBackground,
      bounded: limit !== undefined && limit > 0 && limit <= BOUNDED_S, // GNU `timeout 0` = no limit
      inner: script === undefined ? undefined : analyze(script, false, depth + 1),
    }
  })
  const kinds: CommandKind[] = []
  const add = (k: CommandKind): void => {
    if (!kinds.includes(k)) kinds.push(k)
  }
  for (const s of segments) {
    if (s.inner) s.inner.kinds.forEach(add)
    else add(s.kind)
  }
  // a segment's exit status must be the command's: `npm test | tail`, `build; echo done`,
  // `test || true` report someone else's status (audit H-02, santa P1)
  const owns = exitOwners(raw)
  const evidence: VerifyKind[] = []
  segments.forEach((s, i) => {
    if (!owns[i]) return
    for (const k of s.inner ? s.inner.verify : VERIFY.has(s.kind) ? [s.kind as VerifyKind] : []) if (!evidence.includes(k)) evidence.push(k)
  })
  const live = segments.filter(s => !s.bounded)
  return {
    segments,
    kinds,
    // a backgrounded run returns before it passes or fails (`a && b &` backgrounds both): no evidence
    verify: segments.some(s => s.background) ? [] : evidence,
    isServer: live.some(s => (s.inner ? s.inner.isServer : s.kind === 'server')),
    isWatch: live.some(s => (s.inner ? s.inner.isWatch : s.kind === 'watch')),
    isCommit: kinds.includes('git-commit'),
    isPush: kinds.includes('git-push'),
  }
}

/** A stable key for "the same command again": whitespace folded, output plumbing dropped. */
export function commandKey(command: string): string {
  return command
    .replace(/\s+2>&1/g, '')
    .replace(/\s*\|\s*(tail|head)(\s+-n)?\s+-?\d+\s*$/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 300)
}

/** The first line that reads like an error, numbers folded, for grouping repeated failures. */
export function errorSignature(text: string): string {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const hit = lines.find(l => /\b(error|failed|failure|exception|traceback|cannot|not found|undefined|refused|panic|fatal)\b/i.test(l))
  return (hit ?? lines.at(-1) ?? '').replace(/\d+(\.\d+)?(ms|s)\b/g, '#').replace(/0x[0-9a-f]+/gi, '#').slice(0, 160)
}
