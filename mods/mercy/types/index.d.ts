// The mercy plugin's $.state contract: every value the plugin keeps for the session,
// in one place. Self-contained (no imports): `claude plugin validate` holds every
// $.state key the hooks name to this file, and the hooks import these types from it.

export type CommandKind =
  | 'test' | 'typecheck' | 'lint' | 'format' | 'build' | 'install'
  | 'server' | 'watch' | 'git-commit' | 'git-push' | 'git' | 'other'

export type VerifyKind = 'test' | 'typecheck' | 'lint' | 'build'

export type FileTouch = { path: string; edits: number; firstAt: number; lastAt: number; lastTurn: number; agents: string[]; code: boolean; test: boolean }
export type CommandRun = { key: string; command: string; kinds: CommandKind[]; verify: VerifyKind[]; ok: boolean; at: number; ms: number; turn: number; agent: string; error?: string }
export type AgentRun = { toolUseId: string; id?: string; type: string; description: string; model?: string; background: boolean; startedAt: number; endedAt?: number; ok?: boolean; tokens?: number; tools?: number }
export type HookStat = { n: number; ms: number; max: number }
export type Failure = { n: number; sig: string; lastAt: number; command: string }
export type Block = { at: number; source: 'python' | 'mercy'; reason: string }

export type Ledger = {
  sessionId: string
  startedAt: number
  turn: number
  turnStartedAt: number
  files: Record<string, FileTouch>
  reads: number
  commands: CommandRun[]
  failures: Record<string, Failure>
  lastPass: Partial<Record<VerifyKind, number>>
  lastFail: Partial<Record<VerifyKind, number>>
  lastCodeEditAt: number
  tools: Record<string, number>
  errors: Record<string, number>
  mcp: Record<string, number>
  skills: string[]
  agents: AgentRun[]
  hooks: Record<string, HookStat>
  blocks: Block[]
  usage: { input: number; output: number; cacheRead: number; cacheWrite: number }
  turnEdits: Record<string, number>
}

/** A command the repo brain saw pass or fail, kept across sessions. */
export type KnownCommand = { command: string; kind: VerifyKind; passes: number; fails: number; lastAt: number; lastOk: boolean; ms: number }

/** A failure that a later passing run of the same command resolved. */
export type FixNote = { command: string; error: string; files: string[]; at: number }

/** What the brain knows about one repo, persisted in $.store under `repo:<root>`. */
export type RepoFacts = {
  root: string
  name: string
  packageManager?: string
  stack: string[]
  commands: Record<string, KnownCommand>
  fixes: FixNote[]
  notes: Array<{ text: string; at: number }>
  sessions: number
  updatedAt: number
}

export type BridgeStats = {
  owned: string[]
  queued: number
  ran: number
  failed: number
  savedMs: number
  delivered: number
  lastError?: string
}

export type Health = {
  features: Record<string, 'on' | 'off' | 'error'>
  errors: number
  lastError?: string
}

export type PulseView = 'overview' | 'usage' | 'git' | 'ci' | 'todo' | 'today' | 'ports' | 'deps' | 'files' | 'commands' | 'agents' | 'hooks' | 'brain'

/** UI loudness: full (everything), focus (no auto pane, failure toasts only), quiet (status line only), off. */
export type UiMode = 'full' | 'focus' | 'quiet' | 'off'
/** `/ui` overrides, kept across sessions in $.store `ui:prefs`; unset fields fall back to userConfig. */
export type UiPrefs = { mode?: UiMode; sound?: boolean; notify?: boolean; pane?: boolean }

export type GitFile = { path: string; state: string; add: number; del: number }
export type GitState = {
  branch: string
  /** HEAD's commit id; a change (a commit, pull or checkout from anywhere) re-probes the indexes. */
  head?: string
  upstream?: string
  ahead: number
  behind: number
  staged: number
  modified: number
  untracked: number
  conflicts: number
  /** Every changed path; `files` keeps the first 40. */
  total: number
  files: GitFile[]
  commits: Array<{ sha: string; subject: string; at: number }>
  at: number
}

export type CheckState = 'pass' | 'fail' | 'pending' | 'skip'
export type CiCheck = { name: string; state: CheckState; url?: string }
export type CiState = {
  source: 'pr' | 'runs' | 'none' | 'error'
  overall: CheckState | 'none'
  pr?: { number: number; title: string; url: string; state: string; draft: boolean; review?: string }
  checks: CiCheck[]
  error?: string
  at: number
}

export type Todo = { id: string; text: string; status: 'pending' | 'in_progress' | 'completed' }
export type TurnStat = { at: number; ms: number; input: number; output: number; costUsd: number; ctxPct: number }
export type Limit = { kind: string; percent: number; resetsAt?: string }

export type PortRow = { port: number; address: string; process?: string; pid?: number; label?: string }
export type DepRow = { name: string; current: string; wanted: string; latest: string; bump: 'major' | 'minor' | 'patch' | 'other' }
/** npm outdated per package folder (the repo root and its first-level packages), checked once a day. */
export type DepsState = { at: number; dirs: Array<{ dir: string; rows: DepRow[] }> }
/** Today's standup, made by itself at the first session of the day in a repo. */
export type Standup = { day: string; markdown: string; at: number }
/** The previous session's recap in this repo, saved after every turn. */
export type LastSession = { at: number; minutes: number; turns: number; files: number; unverified: number; commands: number; failed: number; costUsd: number }

/** What the deck watches for the pane, band, toasts and sound. */
export type Deck = {
  sessionId?: string
  git?: GitState
  ci?: CiState
  ports?: PortRow[]
  deps?: DepsState
  standup?: Standup
  lastSession?: LastSession
  todos: Todo[]
  turns: TurnStat[]
  limits: Limit[]
  prefs: UiPrefs
}

/** A slash command's card, drawn in the transcript by a CommandOutput hook; the model reads only its one-line text. */
export type Card = { id: number; command: string; title: string; markdown: string; copy?: string; at: number }

declare module 'claude-code' {
  interface PluginState {
    mercy: {
      ledger: Ledger
      brain: RepoFacts | null
      bridge: BridgeStats
      health: Health
      view: PulseView
      bandHidden: boolean
      contextPct: number
      costUsd: number
      deck: Deck
      cards: Record<string, Card>
    }
  }
}
